from datetime import date
import hashlib
import json

import pytest

from ml.batch_fixture import load_fixture_model, publish_fixture
from ml.cli import ARTIFACT_VERSION
from ml.data import Inputs
from ml.features import FEATURES
from ml.holdout_plan import plan_holdout
from ml.spec import SPEC_VERSION


def test_holdout_starts_after_the_previous_evaluation_inputs():
    earliest = plan_holdout(date(2025, 11, 9), date(2025, 11, 16), "current")
    assert earliest["status"] == "blocked"
    assert earliest["first_anchor"] == "2025-12-08"
    assert earliest["required_complete_through"] == "2026-02-05"
    assert plan_holdout(date(2025, 11, 9), date(2026, 2, 5), "new")["status"] == "ready"


def test_fixture_batch_is_idempotent_and_reports_ineligible_repos(input_frames, tmp_path):
    registry, daily, statuses, publication = input_frames
    decision = "2025-11-01T04:00:00Z"
    data = Inputs(registry, daily, statuses, publication)
    model = {"kind": "persistence"}
    out = tmp_path / "publish"
    anchor = date(2025, 9, 1)
    first = publish_fixture(data, "baseline", model, anchor, decision, out)
    assert first == publish_fixture(data, "baseline", model, anchor, decision, out)
    assert first["rows"][0]["status"] == "ready"
    statuses.loc[statuses.date.eq(anchor.isoformat()), "status"] = "provisional"
    limited = Inputs(registry, daily, statuses, {**publication, "publication_id": "test-gap"})
    gap = publish_fixture(limited, "baseline", model, anchor, decision, out)
    assert gap["rows"][0]["status"] == "incomplete_features"
    assert gap["rows"][0]["predicted_star_events"] is None
    early = publish_fixture(data, "baseline", model, date(2025, 1, 1), decision, out)
    assert early["rows"][0]["status"] == "insufficient_history"


def test_failed_commit_leaves_previous_batch_visible(input_frames, tmp_path, monkeypatch):
    data = Inputs(*input_frames)
    args = (data, "baseline", {"kind": "persistence"})
    decision = "2025-11-01T04:00:00Z"
    live = publish_fixture(*args, date(2025, 9, 1), decision, tmp_path)
    def fail(_source, _target):
        raise OSError("publish failed")
    monkeypatch.setattr("ml.batch_fixture.os.link", fail)
    with pytest.raises(OSError, match="publish failed"):
        publish_fixture(*args, date(2025, 9, 2), decision, tmp_path)
    files = list(tmp_path.iterdir())
    assert len(files) == 1 and json.loads(files[0].read_text()) == live


def test_fixture_model_checksum(tmp_path):
    model = {"model": {"kind": "persistence"}, "artifact_version": ARTIFACT_VERSION,
             "spec_version": SPEC_VERSION, "feature_schema": FEATURES}
    raw = json.dumps(model).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (tmp_path / "model.json").write_bytes(raw)
    (tmp_path / "run.json").write_text(json.dumps({
        "status": "completed", "publication": {"data_source": "fixture"}, "model_sha256": sha,
    }))
    assert load_fixture_model(tmp_path) == (sha, model["model"])
    (tmp_path / "model.json").write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="valid completed fixture"):
        load_fixture_model(tmp_path)
