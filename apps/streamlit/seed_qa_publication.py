"""Seed an isolated loopback ClickHouse database for the APP-11 rehearsal."""

import argparse
from datetime import date, datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
import json
from pathlib import Path

import pandas as pd

from apps.streamlit.data import get_adapter
from apps.streamlit.data.clickhouse_publication import DATASETS, MAX_DAYS, MAX_ROWS, ROW_COUNTS
from apps.streamlit.data.config import ClickHouseConfig


QA_DATABASE = "app11_qa"
DDL = Path(__file__).resolve().parents[2] / "docs/app-ml/app-02-serving-schema.sql"


def post(config, query):
    connect = HTTPSConnection if config.secure else HTTPConnection
    connection = connect(config.host, config.port, timeout=config.connect_timeout)
    try:
        connection.connect()
        connection.sock.settimeout(config.query_timeout)
        connection.request("POST", "/?wait_end_of_query=1", query.encode("utf8"), headers={
            "X-ClickHouse-User": config.username,
            "X-ClickHouse-Key": config.password,
        })
        with connection.getresponse() as response:
            if response.status != 200:
                raise OSError(f"ClickHouse QA seed returned HTTP {response.status}; use a fresh disposable instance")
    finally:
        connection.close()


def seed(config, reference, start, end):
    if config.host not in {"127.0.0.1", "::1"} or config.database != QA_DATABASE:
        raise ValueError("Use a loopback IP and APP_CLICKHOUSE_DATABASE=app11_qa on a disposable instance")
    if not 0 <= (end - start).days < MAX_DAYS:
        raise ValueError(f"The QA window must span 1 to {MAX_DAYS} days")

    snapshot = get_adapter("snapshot", reference)
    first, last = start.isoformat(), end.isoformat()
    bounds = snapshot.date_bounds()
    if bounds is None or not bounds[0] <= first <= last <= bounds[1]:
        raise ValueError("The QA window must fall within the snapshot")

    publication_id = f"app11-local-{first}-{last}"
    marker = {
        "publication_id": publication_id,
        "contract_version": snapshot.publication()["contract_version"],
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expected_complete_through": None,
        "start_date": first,
        "end_date": last,
    }
    inserts = {}
    for table, columns in DATASETS.items():
        frame = snapshot.tables[table]
        if frame.empty:
            marker[ROW_COUNTS[table]] = 0
            continue
        frame = frame.loc[:, list(columns)]
        if "date" in frame:
            frame = frame.loc[frame.date.between(first, last)]
        if len(frame) > MAX_ROWS:
            raise ValueError(f"{table} exceeds the APP-02 reader row limit")
        frame = frame.assign(publication_id=publication_id)
        for column in ("published_at", "created_at", "observed_at"):
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], format="mixed", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        if "topics" in frame:
            frame["topics"] = frame["topics"].map(lambda value: json.dumps(list(value))
                                                   if hasattr(value, "__iter__") and not isinstance(value, str) else value)
        marker[ROW_COUNTS[table]] = len(frame)
        if len(frame):
            inserts[table] = frame.to_json(orient="records", lines=True)

    post(config, f"CREATE DATABASE {QA_DATABASE}")
    for statement in DDL.read_text(encoding="utf8").split(";"):
        if statement.strip().startswith("CREATE TABLE"):
            post(config, statement.replace("app_serving.", f"{QA_DATABASE}."))
    for table, rows in inserts.items():
        post(config, f"INSERT INTO {QA_DATABASE}.{table} FORMAT JSONEachRow\n{rows}")
    post(config, f"INSERT INTO {QA_DATABASE}.app_publications FORMAT JSONEachRow\n{json.dumps(marker)}")
    return {**marker, "snapshot_id": snapshot.publication()["publication_id"], "database": QA_DATABASE}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    try:
        result = seed(ClickHouseConfig.from_env(), args.snapshot, args.start, args.end)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
