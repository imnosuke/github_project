"""Read a bounded, immutable APP-02 publication from ClickHouse."""
from datetime import date
import json
import re

import pandas as pd

from .adapter import COUNTS, KEYS, FixtureAdapter
from .clickhouse_http import read_rows
from .clickhouse_snapshot import _is_loopback


MAX_DAYS = 366
MAX_ROWS = 50_000
MANIFEST_QUERY = """
SELECT publication_id, contract_version, published_at, expected_complete_through, start_date, end_date,
       registry_rows, metadata_rows, status_rows, metric_rows
FROM {database:Identifier}.app_publications
WHERE publication_id = (
    SELECT publication_id
    FROM {database:Identifier}.app_publications
    ORDER BY published_at DESC, publication_id DESC
    LIMIT 1
)
ORDER BY published_at DESC, publication_id DESC
LIMIT 2
FORMAT JSONEachRow
"""
DATASETS = {
    "repository_registry": ("repository_id", "repository_name", "tracking_start_date",
                            "tracking_end_date", "category", "ecosystem"),
    "repository_metadata": ("repository_id", "snapshot_date", "observed_at", "repository_name",
                            "description", "primary_language", "topics", "license", "archived",
                            "is_fork", "created_at", "current_stars", "current_forks"),
    "daily_data_status": ("date", "status", "expected_files", "processed_files", "quality_passed",
                          "published_at", "reason"),
    "repository_daily_metrics": ("repository_id", "date", *COUNTS),
}
DATE_COLUMNS = {"date", "tracking_start_date", "tracking_end_date", "snapshot_date"}
ROW_COUNTS = dict(zip(DATASETS, ("registry_rows", "metadata_rows", "status_rows", "metric_rows")))
COUNT_COLUMNS = set(COUNTS) | set(ROW_COUNTS.values()) | {"repository_id", "expected_files", "processed_files",
                              "current_stars", "current_forks"}


def require_date(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Invalid APP-02 ISO date")
    return value


def require_utc(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("Invalid APP-02 UTC publication timestamp")
    return pd.Timestamp(value)


def validate_row(record, columns):
    if type(record) is not dict or set(record) != set(columns):
        raise ValueError("Unexpected APP-02 row schema")
    for name, value in record.items():
        if value is None:
            continue
        if name in COUNT_COLUMNS:
            if type(value) is str and re.fullmatch(r"[0-9]{1,19}", value):
                value = int(value)
            if type(value) is not int or not 0 <= value <= 2**63 - 1:
                raise ValueError(f"Invalid APP-02 integer: {name}")
            record[name] = value
        elif name in DATE_COLUMNS:
            require_date(value)
        elif name in {"published_at", "observed_at", "created_at"}:
            require_utc(value)
        elif name in {"quality_passed", "archived", "is_fork"}:
            if type(value) is not bool:
                raise ValueError(f"Invalid APP-02 boolean: {name}")
        elif name == "topics":
            value = json.loads(value) if type(value) is str else value
            if type(value) is not list or any(type(topic) is not str for topic in value):
                raise ValueError("Invalid APP-02 topics")
            record[name] = value
        elif type(value) is not str:
            raise ValueError(f"Invalid APP-02 string: {name}")


class ClickHousePublicationAdapter(FixtureAdapter):
    source = "live"

    def __init__(self, config):
        if not config.secure and config.host != "localhost" and not _is_loopback(config.host):
            raise ValueError("Remote APP-02 ClickHouse requires HTTPS")
        params = {"database": config.database}
        manifests = read_rows(config, MANIFEST_QUERY, params, row_limit=2)
        if not manifests:
            raise OSError("ClickHouse has no committed APP-02 publication")
        manifest_columns = ("publication_id", "contract_version", "published_at",
                            "expected_complete_through", "start_date", "end_date", *ROW_COUNTS.values())
        for manifest in manifests:
            validate_row(manifest, manifest_columns)
        manifest = manifests[0]
        if len(manifests) > 1 and manifests[1]["publication_id"] == manifest["publication_id"]:
            raise ValueError("Duplicate APP-02 publication marker")
        publication_id = manifest["publication_id"]
        if type(publication_id) is not str or not publication_id.strip() or len(publication_id) > 200:
            raise ValueError("Invalid APP-02 publication ID")
        if manifest["contract_version"] != "1.0.0-draft":
            raise ValueError("Unsupported APP-02 contract version")
        published = require_utc(manifest["published_at"])
        start, end = (require_date(manifest[key]) for key in ("start_date", "end_date"))
        dates = set(pd.date_range(start, end).strftime("%Y-%m-%d")) if (
            0 <= (date.fromisoformat(end) - date.fromisoformat(start)).days < MAX_DAYS) else set()
        if not dates:
            raise ValueError("APP-02 publication outside supported date span")
        if manifest["expected_complete_through"] is not None:
            require_date(manifest["expected_complete_through"])
        self.envelope = {**manifest, "data_source": self.source}
        self.tables = {}
        for name, columns in DATASETS.items():
            limit = len(dates) if name == "daily_data_status" else MAX_ROWS
            query = (
                "SELECT publication_id, " + ", ".join(columns) + " FROM {database:Identifier}." + name
                + " WHERE publication_id = {publication:String}"
                + " ORDER BY " + ", ".join(KEYS[name])
                + " LIMIT {limit:UInt64} FORMAT JSONEachRow"
            )
            query_params = {**params, "publication": publication_id, "limit": limit + 1}
            rows = read_rows(config, query, query_params, row_limit=limit)
            if manifest[ROW_COUNTS[name]] is None or len(rows) != manifest[ROW_COUNTS[name]]:
                raise ValueError(f"APP-02 row count differs from manifest: {name}")
            for row in rows:
                validate_row(row, ("publication_id", *columns))
                if row.pop("publication_id") != publication_id:
                    raise ValueError("APP-02 row belongs to a different publication")
                if "date" in columns and row["date"] not in dates:
                    raise ValueError("APP-02 row outside publication date span")
                if "repository_name" in columns and not (row["repository_name"] or "").strip():
                    raise ValueError("APP-02 repository name is required")
                if name == "daily_data_status":
                    if any(row[key] is None for key in ("expected_files", "processed_files", "quality_passed")):
                        raise ValueError("APP-02 status fields are required")
                    if row["status"] == "missing" and row["quality_passed"]:
                        raise ValueError("APP-02 missing day cannot pass quality checks")
                    if row["published_at"] is not None and require_utc(row["published_at"]) > published:
                        raise ValueError("APP-02 day newer than its publication")
                if name == "repository_metadata" and (
                    row["observed_at"] is None or require_utc(row["observed_at"]) > published
                    or row["snapshot_date"] is None or row["snapshot_date"] > row["observed_at"][:10]
                ):
                    raise ValueError("APP-02 metadata newer than its publication")
                if name == "repository_registry" and (
                    not row["repository_name"] or row["tracking_start_date"] is None
                    or row["tracking_end_date"] is not None and row["tracking_end_date"] < row["tracking_start_date"]
                ):
                    raise ValueError("APP-02 registry interval is invalid")
                if name == "repository_daily_metrics":
                    total = row["total_events"]
                    if total is None and any(row[metric] is not None for metric in COUNTS if metric != "total_events"):
                        raise ValueError("APP-02 metrics supplied without total_events")
                    human = row["unique_human_actors"]
                    if human is not None and total is not None and human > total:
                        raise ValueError("APP-02 human actor count exceeds total events")
            frame = pd.DataFrame.from_records(rows, columns=columns)
            for column in COUNT_COLUMNS.intersection(columns):
                frame[column] = pd.array([row[column] for row in rows], dtype="Int64")
            self.tables[name] = frame
        if self.tables["repository_daily_metrics"].empty or set(self.tables["daily_data_status"].date) != dates:
            raise ValueError("APP-02 publication has missing registry or daily status coverage")
        self.validate()
