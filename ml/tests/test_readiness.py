import json
from pathlib import Path

import pandas as pd
import pytest

from apps.streamlit.data import get_adapter
from ml.cli import main, read_config
from ml.data import Inputs
from ml.generate_fixture import generate
from ml.readiness import MIN_CALENDAR_DAYS, label_summary, readiness_report

ROOT = Path(__file__).parents[1]
APP_CONFIG = str(ROOT / "configs/app_fixture.json")
SMOKE_CONFIG = str(ROOT / "configs/smoke.json")


def audit(data, config_path=SMOKE_CONFIG):
    config, days, split = read_config(config_path)
    return readiness_report(data, config, days, split)


def test_app_fixture_reports_true_shortfalls_and_does_not_count_repo_rows_as_dates():
    report, frames = audit(Inputs.from_adapter(get_adapter()), APP_CONFIG)
    assert MIN_CALENDAR_DAYS == 239
    assert report["input_coverage"]["calendar_days"] == 95
    assert report["input_coverage"]["status_days"] == {"complete": 93, "missing": 1, "provisional": 1}
    assert report["input_coverage"]["longest_complete_run_days"] == 79
    assert report["input_coverage"]["missing_repo_rows"] == 0
    assert report["splits"]["validation"]["rows"] == 5
    assert report["splits"]["validation"]["distinct_anchor_dates"] == 1
    assert report["splits"]["validation"]["missing_anchor_dates_to_minimum"] == 29
    assert report["splits"]["train"]["labels"]["zero_fraction"] is None
    assert report["eligibility"]["candidates"] == 570
    assert sum(report["eligibility"]["reason_counts"].values()) == 570
    assert report["eligibility"]["kept"] == 5
    assert len(frames["coverage"]) == 95
    assert len(frames["eligibility"]) == 570
    assert report["status"] == "blocked" and report["ready_for_ml03"] is False


def test_long_data_can_pass_data_gates_but_never_certifies_de_or_real_source(input_frames):
    registry, daily, statuses, publication = input_frames
    # The shared 300-day fixture ends October 27. This split requires labels
    # through October 30, so supply those three real complete days explicitly.
    for day in pd.date_range("2025-10-28", "2025-10-30").strftime("%Y-%m-%d"):
        daily = pd.concat([daily, daily.iloc[-1:].assign(date=day)], ignore_index=True)
        statuses = pd.concat([statuses, statuses.iloc[-1:].assign(
            date=day, published_at=f"{day}T23:59:59Z")], ignore_index=True)
    data = Inputs(registry, daily, statuses, publication)
    report, _ = audit(data)
    assert report["data_status"] == "passed"
    assert all(gate["status"] == "passed" for gate in report["data_gates"].values())
    assert report["real_data_source"]["status"] == "blocked"
    assert report["blockers"] == ["real_data_source", "contract_confirmation", "gold_reconciliation", "historical_availability"]
    assert report["ready_for_ml03"] is False
    live = Inputs(registry, daily, statuses, {**publication, "data_source": "live"})
    live_report, _ = audit(live)
    assert live_report["data_status"] == "passed"
    assert live_report["real_data_source"]["status"] == "passed"
    assert live_report["status"] == "blocked"
    assert live_report["blockers"] == ["contract_confirmation", "gold_reconciliation", "historical_availability"]


def test_unknown_status_missing_rows_and_zero_are_separate(input_frames):
    registry, daily, statuses, publication = input_frames
    missing_day = "2025-04-01"
    daily = daily[~daily.date.isin([missing_day, "2025-04-02"])]
    statuses = statuses[statuses.date != missing_day]
    daily.loc[daily.date == "2025-04-03", list(daily.columns.difference(["repository_id", "date"]))] = 0
    report, frames = audit(Inputs(registry, daily, statuses, publication))
    coverage = report["input_coverage"]
    assert coverage["status_days"]["unknown"] == 1
    assert coverage["missing_repo_rows"] == 2
    assert coverage["complete_zero_activity_repo_days"] == 1
    unknown = frames["coverage"].set_index("date").loc[missing_day]
    assert unknown.status == "unknown" and unknown.missing_repo_rows == 1
    assert coverage["noncomplete_ranges"] == [{"start": missing_day, "end": missing_day, "status": "unknown", "days": 1}]


def test_many_repositories_do_not_replace_missing_anchor_dates(input_frames):
    registry, daily, statuses, publication = input_frames
    # Only 20 matured anchors survive in the test window, despite 200 rows.
    daily = daily[daily.date <= "2025-10-20"]
    statuses = statuses[statuses.date <= "2025-10-20"]
    registry = pd.concat([registry.assign(repository_id=rid) for rid in range(1, 11)], ignore_index=True)
    daily = pd.concat([daily.assign(repository_id=rid) for rid in range(1, 11)], ignore_index=True)
    report, _ = audit(Inputs(registry, daily, statuses, publication))
    summary = report["splits"]["test"]
    assert summary["rows"] == 200 and summary["distinct_anchor_dates"] == 20
    assert summary["missing_anchor_dates_to_minimum"] == 10
    assert report["data_gates"]["test_anchors"]["status"] == "blocked"


def test_cli_generates_reports_diagnostics_and_never_trains(tmp_path, monkeypatch):
    import ml.cli as cli
    def forbidden(*args, **kwargs):
        pytest.fail("Readiness audit must never train")
    monkeypatch.setattr(cli, "train_and_evaluate", forbidden)
    output = tmp_path / "audit"
    assert main(["audit", "--config", APP_CONFIG, "--output", str(output)]) == 2
    report = json.loads((output / "readiness.json").read_text())
    assert report["requested_source"] == "fixture"
    assert report["data_status"] == "blocked"
    assert "SYNTHETIC FIXTURE" in (output / "readiness.md").read_text()
    assert set(report["diagnostic_files"]) == {"coverage.parquet", "repository_coverage.parquet", "eligibility.parquet"}
    assert not (output / "model.json").exists()
    assert not (output / "test_predictions.parquet").exists()
    assert pd.read_parquet(output / "repository_coverage.parquet").set_index("repository_id").loc[1005, "kept_rows"] == 0
    with pytest.raises(SystemExit) as exc:
        main(["audit", "--config", APP_CONFIG, "--output", str(output)])
    assert exc.value.code == 2


def test_invalid_input_creates_error_report_without_fabricated_coverage(tmp_path):
    fixture, output = tmp_path / "fixture", tmp_path / "audit"
    generate(fixture)
    path = fixture / "repository_daily_metrics.parquet"
    daily = pd.read_parquet(path)
    pd.concat([daily, daily.iloc[:1]], ignore_index=True).to_parquet(path, index=False)
    assert main(["audit", "--config", SMOKE_CONFIG, "--fixture-dir", str(fixture), "--output", str(output)]) == 2
    report = json.loads((output / "readiness.json").read_text())
    assert report["data_status"] == "invalid"
    assert report["input_error"]["category"] == "input_validation_failed"
    assert "duplicate" in report["input_error"]["message"].lower()
    assert "input_coverage" not in report and report["diagnostic_files"] == {}
    assert not (output / "coverage.parquet").exists()


def test_clickhouse_unavailable_does_not_fall_back_to_fixture(tmp_path, monkeypatch):
    from apps.streamlit.data import clickhouse_publication
    monkeypatch.setattr(clickhouse_publication, "read_rows", lambda *_, **__: [])
    monkeypatch.setenv("APP_CLICKHOUSE_HOST", "localhost")
    output = tmp_path / "audit"
    assert main(["audit", "--config", APP_CONFIG, "--source", "clickhouse", "--output", str(output)]) == 2
    report = json.loads((output / "readiness.json").read_text())
    assert report["requested_source"] == "clickhouse"
    assert report["data_status"] == "unavailable"
    assert report["input_error"]["category"] == "source_unavailable"
    assert "no committed APP-02 publication" in report["input_error"]["message"]
    assert "input_coverage" not in report


def test_audit_does_not_change_config_and_is_reproducible(input_frames):
    data = Inputs(*input_frames)
    first, frames = audit(data)
    second, repeated = audit(data)
    assert first == second
    assert first["config"] == json.loads(Path(SMOKE_CONFIG).read_text())
    for name in frames:
        pd.testing.assert_frame_equal(frames[name], repeated[name])


def test_label_distribution_preserves_zero_and_empty_is_unknown():
    summary = label_summary(pd.DataFrame({"target": [0, 0, 10]}))
    assert summary["zero_fraction"] == pytest.approx(2 / 3)
    assert summary["min"] == summary["median"] == 0
    assert summary["p90"] == pytest.approx(8)
    assert summary["max"] == 10
    assert label_summary(pd.DataFrame({"target": []}))["zero_fraction"] is None


def test_empty_registry_cannot_pass_from_calendar_span_alone(input_frames):
    registry, daily, statuses, publication = input_frames
    report, frames = audit(Inputs(registry.iloc[:0], daily.iloc[:0], statuses, publication))
    assert report["data_status"] == "blocked"
    assert report["data_gates"]["calendar_span"]["status"] == "passed"
    assert report["eligibility"] == {"candidates": 0, "kept": 0, "excluded": 0, "reason_counts": {}}
    assert frames["repository_coverage"].empty
    assert all(summary["distinct_anchor_dates"] == 0 for summary in report["splits"].values())
