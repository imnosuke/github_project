from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_pipeline_health_fixture_shows_missing_retry_and_stale(monkeypatch):
    monkeypatch.setenv("APP_DATA_SOURCE", "fixture")
    monkeypatch.delenv("APP_ENABLE_PIPELINE_FIXTURE", raising=False)
    app = AppTest.from_file(str(APP)).run()
    assert "Pipeline Health" not in app.sidebar.radio(key="page").options
    monkeypatch.setenv("APP_ENABLE_PIPELINE_FIXTURE", "1")
    app.run().sidebar.radio(key="page").set_value("Pipeline Health").run()
    assert not app.exception
    assert any("fixture" in item.value for item in app.warning)
    latest, history = (table.value for table in app.dataframe)
    assert latest.loc[latest.status.eq("provisional"), "missing_hours"].item() == 2
    assert latest.loc[latest.day_utc.eq("2025-01-14"), "attempt"].item() == 2
    assert {1, 2} == set(history.loc[history.day_utc.eq("2025-01-14"), "attempt"])


def test_pipeline_fixture_hidden_for_snapshot(monkeypatch):
    monkeypatch.setenv("APP_ENABLE_PIPELINE_FIXTURE", "1")
    monkeypatch.setenv("APP_DATA_SOURCE", "snapshot")
    monkeypatch.setenv("APP_SNAPSHOT_DIR", str(APP.parent / "data/snapshots/gharchive-2025-01-15"))
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception and not app.error
    assert "Pipeline Health" not in app.sidebar.radio(key="page").options
