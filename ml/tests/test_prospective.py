from datetime import date, timedelta

import pytest

from ml.data import Inputs
from ml.prospective import COHORT_ANCHORS, capture, evaluate


def live_at(input_frames, coverage_end, published_at, publication_id):
    registry, daily, statuses, envelope = input_frames
    return Inputs(registry, daily.loc[daily.date <= coverage_end], statuses.loc[statuses.date <= coverage_end],
                  {**envelope, "data_source": "live", "published_at": published_at, "publication_id": publication_id})


def test_captures_without_future_labels_and_scores_only_after_maturity(input_frames, tmp_path):
    first = date(2025, 2, 5)
    for offset in range(COHORT_ANCHORS):
        anchor = first + timedelta(days=offset)
        next_day = anchor + timedelta(days=1)
        proof = live_at(input_frames, anchor.isoformat(), f"{next_day}T01:00:00Z", f"input-{anchor}")
        recorded = capture(proof, "local", tmp_path, f"{next_day}T02:00:00Z")
        assert recorded["status"] == "captured" and recorded["anchor"] == anchor.isoformat()
        assert "target" not in recorded["rows"][0]
        if offset == 0:
            assert capture(proof, "local", tmp_path, f"{next_day}T03:00:00Z") == recorded
    early = evaluate(proof, "local", tmp_path)
    assert early["status"] == "blocked" and early["required_through"] == "2025-04-05"
    mature = live_at(input_frames, "2025-04-05", "2025-04-06T01:00:00Z", "labels")
    result = evaluate(mature, "local", tmp_path)
    assert result["status"] == "completed" and result["anchor_count"] == COHORT_ANCHORS
    assert result["score"]["persistence_30d"]["rows"] == COHORT_ANCHORS
    assert result["score"]["persistence_30d"]["mae"] == 900
    assert result["release_approved"] is False
    assert evaluate(mature, "local", tmp_path) == result


def test_capture_refuses_fixture_and_replay_window(input_frames, tmp_path):
    fixture = Inputs(*input_frames)
    with pytest.raises(ValueError, match="ClickHouse"):
        capture(fixture, "local", tmp_path, "2025-11-02T02:00:00Z")
    historical = live_at(input_frames, "2025-02-05", "2025-02-06T01:00:00Z", "historical")
    blocked = capture(historical, "local", tmp_path, "2025-03-08T02:00:00Z")
    assert blocked["status"] == "blocked"
    assert not (tmp_path / "predictions").exists()
