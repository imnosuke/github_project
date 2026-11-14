"""Build, train and evaluate local ML-02 artifacts (fixture smoke tests only)."""
from datetime import date
import argparse
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from apps.streamlit.data import get_adapter
from ml.data import Inputs, iso_day
from ml.features import FEATURES, build_dataset
from ml.spec import SPEC_VERSION, TemporalSplit
from ml.training import evaluate, matrix, train_and_evaluate

ARTIFACT_VERSION = 1
WARNING = "SYNTHETIC FIXTURE — smoke test only; metrics do not measure real model quality. Retrospective event-time, not historical availability."


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_config(path):
    config = json.loads(Path(path).read_text())
    keys = {"anchor_start", "anchor_end", "train_start", "validation_start", "test_start", "test_end", "ridge_alpha"}
    if not isinstance(config, dict) or set(config) != keys:
        raise ValueError(f"Config must contain exactly {sorted(keys)}")
    days = {key: date.fromisoformat(iso_day(config[key])) for key in keys - {"ridge_alpha"}}
    if days["anchor_start"] > days["anchor_end"]:
        raise ValueError("Anchor range is reversed")
    if days["train_start"] < days["anchor_start"] or days["test_end"] > days["anchor_end"]:
        raise ValueError("Anchor range must contain the configured splits")
    split = TemporalSplit(*(days[key] for key in ("train_start", "validation_start", "test_start", "test_end")))
    alpha = config["ridge_alpha"]
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not math.isfinite(alpha) or alpha <= 0:
        raise ValueError("ridge_alpha must be finite and positive")
    return config, days, split


def new_output(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def build(args):
    config, days, split = read_config(args.config)
    data = Inputs.from_adapter(get_adapter(directory=args.fixture_dir))
    samples, audit = build_dataset(data, days["anchor_start"], days["anchor_end"], split, args.features_only)
    output = new_output(args.output)
    samples.to_parquet(output / "samples.parquet", index=False)
    audit.to_parquet(output / "audit.parquet", index=False)
    manifest = {"artifact_version": ARTIFACT_VERSION, "spec_version": SPEC_VERSION,
                "feature_schema": list(FEATURES), "config": config,
                "mode": "features" if args.features_only else "supervised",
                "publication": data.publication, "input_fingerprint": data.fingerprint,
                "input_date_bounds": [data.lower, data.upper],
                "warning": WARNING, "rows": len(samples), "candidates": len(audit),
                "audit_counts": {str(k): int(v) for k, v in audit.reason.value_counts().items()},
                "split_rows": {str(k): int(v) for k, v in samples.split.value_counts().items()},
                "files": {name: digest(output / name) for name in ("samples.parquet", "audit.parquet")}}
    dump(output / "manifest.json", manifest)
    print(json.dumps({"output": str(output), "rows": len(samples), "audit_counts": manifest["audit_counts"], "warning": WARNING}))


def load_dataset(path):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text())
    if (manifest.get("artifact_version") != ARTIFACT_VERSION
            or manifest.get("spec_version") != SPEC_VERSION
            or manifest.get("feature_schema") != list(FEATURES)
            or manifest.get("mode") != "supervised"):
        raise ValueError("Incompatible dataset artifact or features-only dataset")
    for name in ("samples.parquet", "audit.parquet"):
        if digest(path / name) != manifest["files"].get(name):
            raise ValueError("Dataset checksum mismatch")
    samples = pd.read_parquet(path / "samples.parquet")
    if set(samples.columns) != {"repository_id", "anchor_date", "split", "target", *FEATURES}:
        raise ValueError("Dataset columns do not match feature schema")
    if samples.duplicated(["repository_id", "anchor_date"]).any():
        raise ValueError("Duplicate dataset samples")
    matrix(samples)
    if samples.target.isna().any() or (samples.target < 0).any() or not np.isfinite(samples.target.to_numpy(dtype=float)).all():
        raise ValueError("Invalid dataset targets")
    split = TemporalSplit(*(date.fromisoformat(manifest["config"][key])
                            for key in ("train_start", "validation_start", "test_start", "test_end")))
    for row in samples.itertuples():
        if row.split not in {"train", "validation", "test"} or split.partition(date.fromisoformat(row.anchor_date)) != row.split:
            raise ValueError("Dataset split does not match calendar contract")
    return samples, manifest


def train(args):
    config, _, _ = read_config(args.config)
    samples, manifest = load_dataset(args.dataset)
    if config != manifest["config"]:
        raise ValueError("Training config must match the dataset config")
    report, model, predictions = train_and_evaluate(samples, config["ridge_alpha"])
    output = new_output(args.output)
    report.update({"warning": WARNING, "dataset_sha256": digest(Path(args.dataset) / "manifest.json"),
                   "spec_version": SPEC_VERSION, "config": config,
                   "input_fingerprint": manifest["input_fingerprint"],
                   "publication": manifest["publication"], "feature_schema": list(FEATURES),
                   "audit_counts": manifest["audit_counts"],
                   "versions": {"python": platform.python_version(), "numpy": np.__version__,
                                "pandas": pd.__version__, "pyarrow": version("pyarrow")}})
    if model is not None:
        dump(output / "model.json", {"artifact_version": ARTIFACT_VERSION,
                                     "spec_version": SPEC_VERSION, "feature_schema": list(FEATURES), "model": model})
        predictions.to_parquet(output / "test_predictions.parquet", index=False)
        report["model_sha256"] = digest(output / "model.json")
    dump(output / "run.json", report)
    print(json.dumps({"status": report["status"], "output": str(output), "warning": WARNING}))
    return 0 if report["status"] == "completed" else 2


def evaluate_saved(args):
    samples, _ = load_dataset(args.dataset)
    run_path = Path(args.run)
    report = json.loads((run_path / "run.json").read_text())
    if report["status"] != "completed":
        raise ValueError("Run is blocked; no model is available")
    if digest(Path(args.dataset) / "manifest.json") != report["dataset_sha256"]:
        raise ValueError("Evaluation dataset differs from the recorded run")
    if digest(run_path / "model.json") != report["model_sha256"]:
        raise ValueError("Model checksum mismatch")
    artifact = json.loads((run_path / "model.json").read_text())
    if (artifact.get("artifact_version") != ARTIFACT_VERSION
            or artifact.get("spec_version") != SPEC_VERSION
            or artifact.get("feature_schema") != list(FEATURES)):
        raise ValueError("Incompatible model schema")
    metrics = evaluate(artifact["model"], samples[samples.split == "test"], report["train_repository_ids"])
    output = new_output(args.output)
    dump(output / "evaluation.json", {"warning": WARNING, "metrics": metrics,
                                       "dataset_sha256": report["dataset_sha256"], "model_sha256": report["model_sha256"]})
    print(json.dumps({"output": str(output), "mae": metrics["mae"], "warning": WARNING}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("--config", required=True)
    builder.add_argument("--fixture-dir")
    builder.add_argument("--features-only", action="store_true")
    trainer = commands.add_parser("train")
    trainer.add_argument("--config", required=True)
    trainer.add_argument("--dataset", required=True)
    evaluator = commands.add_parser("evaluate")
    evaluator.add_argument("--dataset", required=True)
    evaluator.add_argument("--run", required=True)
    for command in (builder, trainer, evaluator):
        command.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return build(args) or 0
        if args.command == "train":
            return train(args)
        return evaluate_saved(args) or 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"ML-02 error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
