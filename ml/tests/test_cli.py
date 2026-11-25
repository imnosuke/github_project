import json
from pathlib import Path

import pandas as pd
import pytest

from ml.cli import digest, load_dataset, main, read_config
from ml.generate_fixture import generate

ROOT = Path(__file__).parents[1]
SMOKE = str(ROOT / "configs/smoke.json")
APP = str(ROOT / "configs/app_fixture.json")


def test_app_fixture_training_blocks_and_features_only_cannot_train(tmp_path):
    dataset, run = tmp_path / "dataset", tmp_path / "run"
    assert main(["build", "--config", APP, "--output", str(dataset)]) == 0
    assert main(["train", "--config", APP, "--dataset", str(dataset), "--output", str(run)]) == 2
    report = json.loads((run / "run.json").read_text())
    assert report["status"] == "blocked" and report["empty_splits"] == ["train", "test"]
    assert not (run / "model.json").exists()
    assert report["warning"].startswith("SYNTHETIC FIXTURE")
    features = tmp_path / "features"
    main(["build", "--config", APP, "--features-only", "--output", str(features)])
    with pytest.raises(ValueError, match="features-only"):
        load_dataset(features)


def test_real_snapshot_training_blocks_on_coverage(tmp_path):
    snapshot = ROOT.parent / "apps/streamlit/data/snapshots/gharchive-2025-01-15"
    dataset, run = tmp_path / "dataset", tmp_path / "run"
    assert main(["build", "--snapshot-dir", str(snapshot), "--config", SMOKE, "--output", str(dataset)]) == 0
    assert main(["train", "--config", SMOKE, "--dataset", str(dataset), "--output", str(run)]) == 2
    report = json.loads((run / "run.json").read_text())
    assert report["reason"] == "snapshot_data_gates"
    assert "calendar_span" in report["blockers"]
    assert report["publication"]["data_source"] == "snapshot"
    assert report["warning"].startswith("RETROSPECTIVE SNAPSHOT")
    assert not (run / "model.json").exists()


def test_smoke_end_to_end_artifacts_are_reproducible_and_reloadable(tmp_path):
    fixture = tmp_path / "fixture"
    generate(fixture)
    datasets, runs = [], []
    for index in range(2):
        dataset = tmp_path / f"dataset-{index}"
        run = tmp_path / f"run-{index}"
        assert main(["build", "--fixture-dir", str(fixture), "--config", SMOKE, "--output", str(dataset)]) == 0
        assert main(["train", "--config", SMOKE, "--dataset", str(dataset), "--output", str(run)]) == 0
        datasets.append(dataset)
        runs.append(run)
    for name in ("samples.parquet", "audit.parquet", "manifest.json"):
        assert digest(datasets[0] / name) == digest(datasets[1] / name)
    for name in ("model.json", "run.json", "test_predictions.parquet"):
        assert digest(runs[0] / name) == digest(runs[1] / name)
    report = json.loads((runs[0] / "run.json").read_text())
    # Five established repos: 76 train / 32 validation / 30 test anchors.
    # The short-history repo adds 18 test anchors, starting September 13.
    assert report["split_rows"] == {"train": 380, "validation": 160, "test": 168}
    assert report["spec_version"] == "ml-stars-30d-v1"
    assert 2106 not in report["train_repository_ids"]
    evaluation = tmp_path / "evaluation"
    assert main(["evaluate", "--dataset", str(datasets[0]), "--run", str(runs[0]), "--output", str(evaluation)]) == 0
    metrics = json.loads((evaluation / "evaluation.json").read_text())["metrics"]
    expected = report["test"][report["selected"]]
    assert metrics["mae"] == expected["mae"]
    assert metrics["by_seen_repository"]["unseen"]["repositories"] == 1
    # No accidental overwrites of completed runs/datasets.
    with pytest.raises(SystemExit) as exc:
        main(["build", "--fixture-dir", str(fixture), "--config", SMOKE, "--output", str(datasets[0])])
    assert exc.value.code == 2
    # Edited files cannot silently be used with the old manifest.
    samples_path = datasets[0] / "samples.parquet"
    samples = pd.read_parquet(samples_path)
    samples.loc[0, "target"] += 1
    samples.to_parquet(samples_path, index=False)
    with pytest.raises(ValueError, match="checksum"):
        load_dataset(datasets[0])


@pytest.mark.parametrize("alpha", [0, -1, True, "1", float("nan")])
def test_invalid_config_rejected(tmp_path, alpha):
    config = json.loads(Path(SMOKE).read_text())
    config["ridge_alpha"] = alpha
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="ridge_alpha"):
        read_config(path)
