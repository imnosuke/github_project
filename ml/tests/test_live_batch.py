from datetime import datetime, timezone
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from apps.streamlit.data.config import ClickHouseConfig
from apps.streamlit.data.prediction_publication import validate_predictions
from ml import live_batch
from ml.cli import ARTIFACT_VERSION
from ml.features import FEATURES
from ml.spec import SPEC_VERSION


def test_rejects_fixture_training_release(tmp_path):
    model = tmp_path / "model.json"
    model.write_text(json.dumps({"model": {"kind": "persistence"}, "feature_schema": FEATURES,
                                 "artifact_version": ARTIFACT_VERSION, "spec_version": SPEC_VERSION}))
    model_id = sha256(model.read_bytes()).hexdigest()
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"status": "completed", "model_sha256": model_id, "publication": {"data_source": "fixture"}}))
    r = {"status": "approved", "release_id": "qa", "approved_at": "2026-01-01T00:00:00Z", "model_sha256": model_id,
         "repository_ids": list(range(1, 21)), "ml03_acceptance": {"gold_reconciliation": "qa",
         "contract_confirmation": "qa", "prospective_evaluation": "qa", "gold_training_run_sha256": sha256(run.read_bytes()).hexdigest()}}
    release = tmp_path / "release.json"
    release.write_text(json.dumps(r))
    with pytest.raises(ValueError, match="Gold approval"):
        live_batch.load_release(release, model, datetime.now(timezone.utc))


def test_prediction_manifest_commits_after_verification_and_reuses_id(monkeypatch):
    scope = list(range(1, 21))
    data = SimpleNamespace(fingerprint="source-hash", publication={"data_source": "live", "publication_id": "input",
                                                                  "published_at": "2026-01-01T00:00:00Z"})
    observed = {"publication_id": "input", "input_fingerprint": data.fingerprint, "observed_at": "2026-01-01T00:00:01Z"}
    monkeypatch.setattr(live_batch, "prediction_rows", lambda *_: [
        {"repository_id": rid, "status": "ready", "predicted_star_events": 0} for rid in scope])
    writes = {}

    def read(_config, query, _params, row_limit):
        if "prediction_publications" in query:
            return writes.get("prediction_publications", [])
        return writes.get("repository_predictions", [])

    monkeypatch.setattr(live_batch, "read_rows", read)
    monkeypatch.setattr(live_batch, "insert", lambda _config, table, rows: writes.update({table: rows}))
    config = ClickHouseConfig("127.0.0.1", secure=False)
    release = {"release_id": "qa", "repository_ids": scope}
    first = live_batch.publish(data, config, release, "model", {}, observed)
    assert list(writes) == ["repository_predictions", "prediction_publications"]
    assert live_batch.publish(data, config, release, "model", {}, observed) == first
    writes.clear()
    monkeypatch.setattr(live_batch, "read_rows", lambda *_args, **_kwargs: [])
    with pytest.raises(ValueError, match="scope"):
        live_batch.publish(data, config, release, "model", {}, observed)
    assert "prediction_publications" not in writes


def test_invalid_prediction_rows_fail_closed():
    row = {"publication_id": "p", "repository_id": 1, "status": "ready", "predicted_star_events": 0}
    assert validate_predictions([row], [1], "p")[0]["predicted_star_events"] == 0
    with pytest.raises(ValueError, match="Invalid prediction"):
        validate_predictions([dict(row, predicted_star_events=float("inf"))], [1], "p")
    with pytest.raises(ValueError, match="scope"):
        validate_predictions([row, row], [1, 2], "p")
