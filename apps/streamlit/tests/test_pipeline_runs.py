from contextlib import closing
import json
from pathlib import Path
import runpy
import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"
EXPORTER = APP.parents[2] / "airflow/scripts/export_pipeline_runs.py"


def test_exported_pipeline_runs_remain_visible_during_gold_error(monkeypatch, tmp_path):
    database = tmp_path / "airflow.db"
    output = tmp_path / "runs.json"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript("""
            CREATE TABLE dag_run(dag_id, run_id, state, execution_date, start_date, end_date);
            CREATE TABLE xcom(dag_id, run_id, task_id, map_index, key, value);
            CREATE TABLE task_instance(dag_id, run_id, task_id, map_index, state);
            CREATE TABLE task_fail(dag_id, run_id);
            INSERT INTO dag_run VALUES
                ('gharchive_to_minio_hourly', 'first', 'failed', '2025-01-16 00:00:00', NULL, NULL),
                ('gharchive_to_minio_hourly', 'replay', 'success', '2025-01-16 01:00:00',
                 '2025-01-16 01:00:00', '2025-01-16 01:02:00');
            INSERT INTO task_fail VALUES ('gharchive_to_minio_hourly', 'first');
            INSERT INTO task_instance VALUES
                ('gharchive_to_minio_hourly', 'first', 'stream_gharchive_to_minio_s3', -1, 'failed');
        """)
        targets = [{"date_str": "2025-01-15", "hour": hour} for hour in (0, 1)]
        connection.executemany("INSERT INTO xcom VALUES ('gharchive_to_minio_hourly', ?, ?, -1, ?, ?)", [
            ("first", "resolve_target_datetime", "targets", json.dumps(targets)),
            ("replay", "resolve_target_datetime", "targets", json.dumps(targets)),
            ("replay", "stream_gharchive_to_minio_s3", "items", json.dumps(targets[:1])),
        ])
        connection.commit()

    export = runpy.run_path(str(EXPORTER))["main"]
    assert export(["--database", str(database), "--output", str(output)]) == 0
    monkeypatch.setenv("APP_DATA_SOURCE", "unavailable-source")
    monkeypatch.setenv("APP_PIPELINE_RUNS_FILE", str(output))
    app = AppTest.from_file(str(APP)).run()
    assert app.error
    app.sidebar.radio(key="page").set_value("Pipeline Health").run()
    assert not app.error and not app.exception
    summary, hours, tasks = (table.value for table in app.dataframe)
    assert list(summary["Airflow run ID"]) == ["replay", "first"]
    assert pd.isna(summary.loc[1, "Giờ đã upload"])
    assert pd.isna(summary.loc[1, "Giờ thiếu"])
    assert summary.loc[1, "Lần thử lỗi"] == 1
    assert summary.loc[0, "Thời lượng (giây)"] == 120
    assert list(hours.iloc[0]["Giờ thiếu (UTC)"]) == ["2025-01-15 01:00Z"]
    assert list(tasks["Trạng thái"]) == ["failed"]


@pytest.mark.parametrize("suffix", ["", "-wal"])
def test_export_rejects_output_pointing_at_database(tmp_path, suffix):
    database = tmp_path / "airflow.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE sentinel(id INTEGER)")
    before = database.read_bytes()
    export = runpy.run_path(str(EXPORTER))["main"]
    with pytest.raises(SystemExit) as exc:
        export(["--database", str(database), "--output", str(database) + suffix])
    assert exc.value.code == 2
    assert database.read_bytes() == before


def test_pipeline_shows_error_for_invalid_hour_count(monkeypatch, tmp_path):
    output = tmp_path / "invalid-runs.json"
    output.write_text(json.dumps({
        "source": "airflow-local", "exported_at": "2026-11-26T00:00:00Z",
        "runs": [{"run_id": "bad-run", "missing_hours": "invalid", "task_states": []}],
    }), encoding="utf8")
    monkeypatch.setenv("APP_DATA_SOURCE", "fixture")
    monkeypatch.setenv("APP_PIPELINE_RUNS_FILE", str(output))
    app = AppTest.from_file(str(APP)).run()
    app.sidebar.radio(key="page").set_value("Pipeline Health").run()
    assert not app.exception
    assert any("Không đọc được bản xuất Airflow" in item.value for item in app.error)
