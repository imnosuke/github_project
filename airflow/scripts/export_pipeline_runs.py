"""Export local GH Archive DAG run evidence from Airflow's SQLite metadata."""

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


def xcom_hours(connection, run_id, task_id, key):
    row = connection.execute(
        "SELECT value FROM xcom WHERE dag_id = ? AND run_id = ? "
        "AND task_id = ? AND map_index = -1 AND key = ?",
        (DAG_ID, run_id, task_id, key),
    ).fetchone()
    if row is None:
        return None
    items = json.loads(row["value"])
    return {(date.fromisoformat(item["date_str"]), int(item["hour"])) for item in items}


def format_hour(target):
    day, hour = target
    return f"{day} {hour:02d}:00Z"


def read_runs(database, limit=100):
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        rows = connection.execute(
            "SELECT run_id, state, start_date AS started_at, end_date AS ended_at "
            "FROM dag_run WHERE dag_id = ? ORDER BY execution_date DESC, run_id DESC LIMIT ?",
            (DAG_ID, limit),
        ).fetchall()
        runs = []
        for row in rows:
            run_id = row["run_id"]
            targets = xcom_hours(connection, run_id, TARGET_TASK, "targets")
            uploads = xcom_hours(connection, run_id, UPLOAD_TASK, "items")
            matched = targets & uploads if targets is not None and uploads is not None else None
            states = connection.execute(
                "SELECT task_id, state FROM task_instance WHERE dag_id = ? AND run_id = ? "
                "AND (state IN ('failed', 'upstream_failed', 'up_for_retry') OR task_id = ?) "
                "ORDER BY task_id, map_index",
                (DAG_ID, run_id, UPLOAD_TASK),
            ).fetchall()
            failures = connection.execute(
                "SELECT count(*) FROM task_fail WHERE dag_id = ? AND run_id = ?", (DAG_ID, run_id)
            ).fetchone()[0]
            pending = targets - matched if matched is not None else None
            start, end = row["started_at"], row["ended_at"]
            runs.append({
                **dict(row),
                "target_start": format_hour(min(targets)) if targets else None,
                "target_end": format_hour(max(targets)) if targets else None,
                "expected_hours": len(targets) if targets is not None else None,
                "uploaded_hours": len(matched) if matched is not None else None,
                "missing_hours": len(pending) if pending is not None else None,
                "missing_target_hours": [format_hour(target) for target in sorted(pending)]
                if pending is not None else None,
                "duration_seconds": (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
                if start and end else None,
                "failed_attempts": failures,
                "task_states": [dict(task) for task in states],
            })
    return runs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    database = args.database.resolve()
    database_files = {database.with_name(database.name + suffix) for suffix in ("", "-wal", "-shm", "-journal")}
    if args.output.resolve() in database_files:
        parser.error("--output must be separate from the Airflow database and its sidecar files")
    runs = read_runs(database)
    report = {
        "source": "airflow-local",
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
