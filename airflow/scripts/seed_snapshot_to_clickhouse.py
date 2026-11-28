"""Seed a committed APP-02 Parquet snapshot into ClickHouse Gold and app_serving tables."""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from time import sleep

import pyarrow.parquet as pq

from clickhouse_loader import execute_clickhouse_sql

logger = logging.getLogger("seed_snapshot_to_clickhouse")

MAX_APP02_DAYS = 366
DEFAULT_SNAPSHOT_DIR = Path("/opt/airflow/datasets/gharchive-2026-07-21/snapshot")
DEFAULT_SCHEMA_PATH = Path("/opt/airflow/app-02-serving-schema.sql")

GOLD_DDL = """
CREATE TABLE IF NOT EXISTS gold.gold_repo_daily_activity
(
    event_date Date,
    repo_id Int64,
    repo_full_name String,
    repo_owner String,
    repo_short_name String,
    org_login String,
    total_events UInt64,
    unique_contributors UInt64,
    unique_human_contributors UInt64,
    stars_gained UInt64,
    forks_count UInt64,
    push_events_count UInt64,
    total_commits_pushed Int64,
    prs_opened UInt64,
    prs_merged Nullable(UInt64),
    prs_closed_unmerged Nullable(UInt64),
    issues_opened UInt64,
    issues_closed UInt64,
    issue_comments_count UInt64,
    first_event_at DateTime,
    last_event_at DateTime
)
ENGINE = MergeTree()
ORDER BY (event_date, total_events, repo_id)
"""


def _normalize_utc(value):
    if value is None:
        return None
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert_json_chunks(table: str, rows: list[dict], chunk_size: int = 1000, database: str = "default") -> int:
    inserted = 0
    for idx in range(0, len(rows), chunk_size):
        chunk = rows[idx : idx + chunk_size]
        payload = "\n".join(json.dumps(row, ensure_ascii=False, allow_nan=False) for row in chunk)
        execute_clickhouse_sql(f"INSERT INTO {table} FORMAT JSONEachRow\n{payload}", database=database)
        inserted += len(chunk)
    return inserted


def _wait_for_clickhouse(attempts: int = 30, delay_seconds: float = 2.0) -> None:
    for attempt in range(attempts):
        try:
            execute_clickhouse_sql("SELECT 1")
            return
        except Exception:
            if attempt == attempts - 1:
                raise
            sleep(delay_seconds)


def build_gold_rows(registry_rows: list[dict], metric_rows: list[dict], existing_dates: set[str]) -> list[dict]:
    repo_names = {int(r["repository_id"]): str(r["repository_name"]) for r in registry_rows}
    gold_rows = []
    for row in metric_rows:
        day = str(row["date"])
        if day in existing_dates or row.get("total_events") is None:
            continue
        rid = int(row["repository_id"])
        full_name = repo_names.get(rid, str(rid))
        owner, short_name = full_name.split("/", 1) if "/" in full_name else ("", full_name)
        gold_rows.append(
            {
                "event_date": day,
                "repo_id": rid,
                "repo_full_name": full_name,
                "repo_owner": owner,
                "repo_short_name": short_name,
                "org_login": owner,
                "total_events": int(row["total_events"]),
                "unique_contributors": int(row["unique_actors"] or 0),
                "unique_human_contributors": int(row["unique_human_actors"] or 0),
                "stars_gained": int(row["star_events"] or 0),
                "forks_count": int(row["fork_events"] or 0),
                "push_events_count": int(row["push_events"] or 0),
                "total_commits_pushed": int(row["commits_pushed"] or 0),
                "prs_opened": int(row["prs_opened"] or 0),
                "prs_merged": None if row.get("prs_merged") is None else int(row["prs_merged"]),
                "prs_closed_unmerged": None
                if row.get("prs_closed_unmerged") is None
                else int(row["prs_closed_unmerged"]),
                "issues_opened": int(row["issues_opened"] or 0),
                "issues_closed": int(row["issues_closed"] or 0),
                "issue_comments_count": int(row["issue_comments"] or 0),
                "first_event_at": f"{day} 00:00:00",
                "last_event_at": f"{day} 23:59:59",
            }
        )
    return gold_rows


def build_app02_publication(
    manifest: dict,
    registry_rows: list[dict],
    metadata_rows: list[dict],
    status_rows: list[dict],
    metric_rows: list[dict],
    window_days: int = MAX_APP02_DAYS,
) -> tuple[dict, dict[str, list[dict]]]:
    if not 1 <= window_days <= MAX_APP02_DAYS:
        raise ValueError(f"window_days must be between 1 and {MAX_APP02_DAYS}")
    all_dates = sorted({str(r["date"]) for r in status_rows})
    if not all_dates:
        raise ValueError("Snapshot contains no daily_data_status rows")
    end = date.fromisoformat(all_dates[-1])
    earliest = date.fromisoformat(all_dates[0])
    start = max(earliest, end - timedelta(days=window_days - 1))
    start_str, end_str = start.isoformat(), end.isoformat()

    pub_id = f"seed-{manifest['publication_id']}"
    published_at = _normalize_utc(manifest.get("published_at")) or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

    def clamp_ts(ts):
        norm = _normalize_utc(ts)
        if norm is None:
            return None
        dt = datetime.fromisoformat(norm.replace("Z", "+00:00"))
        return published_at if dt > pub_dt else norm

    staged_registry = [
        {
            "publication_id": pub_id,
            "repository_id": int(r["repository_id"]),
            "repository_name": str(r["repository_name"]),
            "tracking_start_date": str(r["tracking_start_date"]),
            "tracking_end_date": None if r.get("tracking_end_date") is None else str(r["tracking_end_date"]),
            "category": r.get("category"),
            "ecosystem": r.get("ecosystem"),
        }
        for r in registry_rows
    ]
    staged_metadata = [
        {
            "publication_id": pub_id,
            **r,
            "observed_at": clamp_ts(r.get("observed_at")),
            "created_at": clamp_ts(r.get("created_at")),
        }
        for r in metadata_rows
    ]
    staged_status = [
        {
            "publication_id": pub_id,
            "date": str(r["date"]),
            "status": str(r["status"]),
            "expected_files": int(r["expected_files"]),
            "processed_files": int(r["processed_files"]),
            "quality_passed": bool(r["quality_passed"]),
            "published_at": clamp_ts(r.get("published_at")),
            "reason": r.get("reason"),
        }
        for r in status_rows
        if start_str <= str(r["date"]) <= end_str
    ]
    staged_metrics = [
        {"publication_id": pub_id, **r}
        for r in metric_rows
        if start_str <= str(r["date"]) <= end_str
    ]

    marker = {
        "publication_id": pub_id,
        "contract_version": str(manifest.get("contract_version", "1.0.0-draft")),
        "published_at": published_at,
        "expected_complete_through": manifest.get("expected_complete_through"),
        "start_date": start_str,
        "end_date": end_str,
        "registry_rows": len(staged_registry),
        "metadata_rows": len(staged_metadata),
        "status_rows": len(staged_status),
        "metric_rows": len(staged_metrics),
    }
    tables = {
        "repository_registry": staged_registry,
        "repository_metadata": staged_metadata,
        "daily_data_status": staged_status,
        "repository_daily_metrics": staged_metrics,
    }
    return marker, tables


def seed_snapshot(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    window_days: int = MAX_APP02_DAYS,
) -> dict:
    snapshot_dir = Path(snapshot_dir)
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    registry_rows = pq.read_table(snapshot_dir / "repository_registry.parquet").to_pylist()
    metadata_rows = pq.read_table(snapshot_dir / "repository_metadata.parquet").to_pylist()
    status_rows = pq.read_table(snapshot_dir / "daily_data_status.parquet").to_pylist()
    metric_rows = pq.read_table(snapshot_dir / "repository_daily_metrics.parquet").to_pylist()

    _wait_for_clickhouse()

    # 1. Seed gold.gold_repo_daily_activity for Superset (only missing dates)
    execute_clickhouse_sql("CREATE DATABASE IF NOT EXISTS gold")
    execute_clickhouse_sql(GOLD_DDL, database="gold")
    existing_raw = execute_clickhouse_sql(
        "SELECT DISTINCT toString(event_date) FROM gold.gold_repo_daily_activity",
        database="gold",
    )
    existing_dates = {line.strip() for line in existing_raw.splitlines() if line.strip()}
    gold_rows = build_gold_rows(registry_rows, metric_rows, existing_dates)
    gold_inserted = _insert_json_chunks("gold.gold_repo_daily_activity", gold_rows, database="gold") if gold_rows else 0

    # 2. Seed app_serving.* APP-02 publication (idempotent by publication_id)
    for statement in Path(schema_path).read_text(encoding="utf-8").split(";"):
        if statement.strip():
            execute_clickhouse_sql(statement)

    marker, tables = build_app02_publication(
        manifest=manifest,
        registry_rows=registry_rows,
        metadata_rows=metadata_rows,
        status_rows=status_rows,
        metric_rows=metric_rows,
        window_days=window_days,
    )
    pub_id = marker["publication_id"]
    already = int(
        execute_clickhouse_sql(
            f"SELECT count() FROM app_serving.app_publications WHERE publication_id = '{pub_id}'"
        )
        or 0
    )
    app_serving_seeded = False
    if not already:
        for table_name, rows in tables.items():
            if rows:
                _insert_json_chunks(f"app_serving.{table_name}", rows)
        _insert_json_chunks("app_serving.app_publications", [marker])
        app_serving_seeded = True

    result = {
        "snapshot_publication_id": manifest["publication_id"],
        "gold_rows_inserted": gold_inserted,
        "gold_dates_skipped": len(existing_dates),
        "app_serving_publication_id": pub_id,
        "app_serving_seeded": app_serving_seeded,
        "app_serving_window": [marker["start_date"], marker["end_date"]],
    }
    logger.info("ClickHouse snapshot seed result: %s", json.dumps(result))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(os.getenv("APP_SNAPSHOT_DIR", str(DEFAULT_SNAPSHOT_DIR))),
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(os.getenv("APP02_SCHEMA_PATH", str(DEFAULT_SCHEMA_PATH))),
    )
    parser.add_argument("--window-days", type=int, default=MAX_APP02_DAYS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    result = seed_snapshot(args.snapshot, args.schema, args.window_days)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
