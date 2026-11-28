from hashlib import sha256
import json
from pathlib import Path
import sys

import pyarrow.parquet as pq
from streamlit.testing.v1 import AppTest

from apps.streamlit.data import get_adapter


ROOT = Path(__file__).resolve().parents[3]
UNIFIED_DIR = ROOT / "ml/datasets/gharchive-2026-07-21"
SNAPSHOT_DIR = UNIFIED_DIR / "snapshot"
RUNS_FILE = UNIFIED_DIR / "de-evidence/app10-airflow-runs.json"
APP = ROOT / "apps/streamlit/app.py"


def test_unified_snapshot_contract_and_checksums():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["from"] == "2025-01-01"
    assert manifest["through"] == "2026-07-21"
    for filename, expected_sha in manifest["files"].items():
        actual_sha = sha256((SNAPSHOT_DIR / filename).read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"Checksum mismatch for {filename}"

    adapter = get_adapter("snapshot", SNAPSHOT_DIR)
    assert adapter.date_bounds() == ("2025-01-01", "2026-07-21")
    assert len(adapter.repository_catalog()) == 20
    growth = adapter.growth_ranking("2025-08-17", window=30)
    assert len(growth) == 20
    assert growth["state"].isin({"valid", "new_activity", "no_activity"}).all()


def test_unified_snapshot_and_pipeline_runs_render_in_reposcope(monkeypatch):
    monkeypatch.setenv("APP_DATA_SOURCE", "snapshot")
    monkeypatch.setenv("APP_SNAPSHOT_DIR", str(SNAPSHOT_DIR))
    monkeypatch.setenv("APP_PIPELINE_RUNS_FILE", str(RUNS_FILE))
    app = AppTest.from_file(str(APP)).run(timeout=30)
    assert not app.error and not app.exception

    app.sidebar.radio(key="page").set_value("Pipeline Health").run(timeout=30)
    assert not app.error and not app.exception
    assert app.dataframe and len(app.dataframe[0].value) > 100


def test_seed_snapshot_builders_produce_valid_gold_and_app02_window():
    scripts_dir = str(ROOT / "airflow/scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import seed_snapshot_to_clickhouse as seeder

    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))
    registry = pq.read_table(SNAPSHOT_DIR / "repository_registry.parquet").to_pylist()
    metadata = pq.read_table(SNAPSHOT_DIR / "repository_metadata.parquet").to_pylist()
    statuses = pq.read_table(SNAPSHOT_DIR / "daily_data_status.parquet").to_pylist()
    metrics = pq.read_table(SNAPSHOT_DIR / "repository_daily_metrics.parquet").to_pylist()

    gold_rows = seeder.build_gold_rows(registry, metrics, existing_dates={"2025-01-15"})
    assert gold_rows
    assert all(row["event_date"] != "2025-01-15" for row in gold_rows)
    assert any(row["event_date"] == "2026-07-21" for row in gold_rows)

    marker, tables = seeder.build_app02_publication(manifest, registry, metadata, statuses, metrics)
    assert marker["start_date"] == "2025-07-21"
    assert marker["end_date"] == "2026-07-21"
    assert marker["status_rows"] == 366
    assert marker["metric_rows"] == 366 * 20
    assert marker["registry_rows"] == 20
    assert len(tables["daily_data_status"]) == 366
    assert len(tables["repository_daily_metrics"]) == 366 * 20
