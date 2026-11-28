"""Seed the committed historical snapshot into ClickHouse and queue one live GH Archive hour."""

import os
from pathlib import Path
import sys
from time import sleep

from airflow.api.common.trigger_dag import trigger_dag
from airflow.exceptions import DagNotFound, DagRunAlreadyExists


SCRIPTS_DIR = "/opt/airflow/scripts"
if SCRIPTS_DIR not in sys.path:
    sys.path.append(SCRIPTS_DIR)


def seed_committed_snapshot():
    snapshot_dir = Path(os.getenv("APP_SNAPSHOT_DIR", "/opt/airflow/datasets/gharchive-2026-07-21/snapshot"))
    if not (snapshot_dir / "manifest.json").exists():
        print(f"Committed snapshot not found at {snapshot_dir}; skipping ClickHouse seed.")
        return
    from seed_snapshot_to_clickhouse import seed_snapshot

    schema_path = Path(os.getenv("APP02_SCHEMA_PATH", "/opt/airflow/app-02-serving-schema.sql"))
    result = seed_snapshot(snapshot_dir=snapshot_dir, schema_path=schema_path)
    print(
        f"Seeded ClickHouse from {result['snapshot_publication_id']}: "
        f"{result['gold_rows_inserted']} gold rows inserted, "
        f"app_serving_seeded={result['app_serving_seeded']} ({result['app_serving_window'][0]}..{result['app_serving_window'][1]})."
    )


def main():
    seed_committed_snapshot()
    for _ in range(60):
        try:
            run = trigger_dag(
                dag_id="gharchive_to_minio_hourly",
                run_id="reposcope-demo__2025-01-15T14",
                conf={"custom_date": "2025-01-15", "custom_hour": 14},
                replace_microseconds=False,
            )
        except DagRunAlreadyExists:
            print("Demo ingestion run already exists.")
            return
        except DagNotFound:
            sleep(2)
        else:
            if run is None:
                raise RuntimeError("Airflow did not create the demo run.")
            print(f"Queued Airflow run {run.run_id}.")
            return
    raise RuntimeError("Airflow did not register gharchive_to_minio_hourly within 120 seconds.")


if __name__ == "__main__":
    main()
