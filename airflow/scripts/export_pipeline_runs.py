"""Export GH Archive DAG run evidence from Airflow metadata with read-only queries."""

import argparse
from contextlib import closing
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile


DAG_ID = "gharchive_to_minio_hourly"
TARGET_TASK = "resolve_target_datetime"
UPLOAD_TASK = "stream_gharchive_to_minio_s3"
DBT_TASK = "dbt_transform_silver_gold"
PUBLISH_TASK = "publish_app02_gold"


def read_xcom(query, run_id, task_id, key):
    rows = query(
        "SELECT value FROM xcom WHERE dag_id = ? AND run_id = ? "
        "AND task_id = ? AND map_index = -1 AND key = ?",
        (DAG_ID, run_id, task_id, key),
    )
    if not rows:
        return None
    value = rows[0]["value"]
    return json.loads(bytes(value) if isinstance(value, memoryview) else value)


def xcom_hours(query, run_id, task_id, key):
    items = read_xcom(query, run_id, task_id, key)
    return {(date.fromisoformat(item["date_str"]), int(item["hour"])) for item in items} if items is not None else None


def format_hour(target):
    day, hour = target
    return f"{day} {hour:02d}:00Z"


def parse_timestamp(value):
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    if stamp is None:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def collect_runs(query, limit):
    rows = query(
        "SELECT run_id, state, start_date AS started_at, end_date AS ended_at "
        "FROM dag_run WHERE dag_id = ? ORDER BY execution_date DESC, run_id DESC LIMIT ?",
        (DAG_ID, limit),
    )
    runs = []
    for row in rows:
        run_id = row["run_id"]
        targets = xcom_hours(query, run_id, TARGET_TASK, "targets")
        uploads = xcom_hours(query, run_id, UPLOAD_TASK, "items")
        matched = targets & uploads if targets is not None and uploads is not None else None
        states = query(
            "SELECT task_id, state FROM task_instance WHERE dag_id = ? AND run_id = ? "
            "AND (state IN ('failed', 'upstream_failed', 'up_for_retry') OR task_id IN (?, ?, ?)) "
            "ORDER BY task_id, map_index",
            (DAG_ID, run_id, UPLOAD_TASK, DBT_TASK, PUBLISH_TASK),
        )
        failures = query("SELECT task_id, start_date, end_date FROM task_fail WHERE dag_id = ? AND run_id = ? "
                         "ORDER BY start_date, task_id", (DAG_ID, run_id))
        pending = targets - matched if matched is not None else None
        start, end = map(parse_timestamp, (row["started_at"], row["ended_at"]))
        dbt_state = next((task["state"] for task in states if task["task_id"] == DBT_TASK), None)
        publication = read_xcom(query, run_id, PUBLISH_TASK, "publication_id")
        failure_details = []
        for task in failures:
            failure_start, failure_end = map(parse_timestamp, (task["start_date"], task["end_date"]))
            failure_details.append({"task_id": task["task_id"], "started_at": failure_start.isoformat() if failure_start else None,
                                    "ended_at": failure_end.isoformat() if failure_end else None})
        runs.append({
            **dict(row),
            "started_at": start.isoformat() if start else None,
            "ended_at": end.isoformat() if end else None,
            "target_start": format_hour(min(targets)) if targets else None,
            "target_end": format_hour(max(targets)) if targets else None,
            "expected_hours": len(targets) if targets is not None else None,
            "uploaded_hours": len(matched) if matched is not None else None,
            "missing_hours": len(pending) if pending is not None else None,
            "missing_target_hours": [format_hour(target) for target in sorted(pending)]
            if pending is not None else None,
            "duration_seconds": (end - start).total_seconds() if start and end else None,
            "failed_attempts": len(failures),
            "failure_details": failure_details,
            "dbt_state": dbt_state,
            "publication_id": publication,
            "task_states": [dict(task) for task in states],
        })
    return runs


def read_runs(database, limit=100):
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        return collect_runs(lambda sql, args: connection.execute(sql, args).fetchall(), limit)


def read_postgres_metadata(limit=100):
    from airflow import settings

    if settings.engine.dialect.name != "postgresql":
        raise ValueError("--airflow-metadata requires an Airflow PostgreSQL metadata database")
    with settings.engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        return collect_runs(lambda sql, args: connection.exec_driver_sql(sql.replace("?", "%s"), args).mappings().all(), limit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path)
    source.add_argument("--airflow-metadata", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.database:
        database = args.database.resolve()
        database_files = {database.with_name(database.name + suffix) for suffix in ("", "-wal", "-shm", "-journal")}
        if args.output.resolve() in database_files:
            parser.error("--output must be separate from the Airflow database and its sidecar files")
        runs = read_runs(database)
    else:
        runs = read_postgres_metadata()
    report = {
        "source": "airflow-local" if args.database else "airflow-metadata",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf8", dir=args.output.parent, delete=False) as handle:
            staged = Path(handle.name)
            json.dump(report, handle, indent=2)
            handle.write("\n")
        os.replace(staged, args.output)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    print(f"Exported {len(runs)} {DAG_ID} runs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
