"""Publish the dbt Gold read model and coverage receipts for an explicit repository scope."""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from clickhouse_loader import execute_clickhouse_sql


METRIC_SOURCES = {
    "total_events": "total_events", "star_events": "stars_gained", "fork_events": "forks_count",
    "push_events": "push_events_count", "prs_opened": "prs_opened", "prs_merged": "prs_merged",
    "prs_closed_unmerged": "prs_closed_unmerged", "issues_opened": "issues_opened", "issues_closed": "issues_closed",
    "issue_comments": "issue_comments_count",
}
METRICS = (*METRIC_SOURCES, "commits_pushed", "unique_actors", "unique_human_actors", "active_contributors")
OPTIONAL = {"commits_pushed", "active_contributors"}
MAX_ROWS = 50_000
MAX_DAYS = 366


def read_registry(path):
    rows = json.loads(Path(path).read_text(encoding="utf8"))
    registry = []
    for row in rows:
        rid = row["repository_id"]
        name = row["repository_name"]
        first = date.fromisoformat(row["tracking_start_date"])
        last = date.fromisoformat(row["tracking_end_date"]) if row.get("tracking_end_date") else None
        if type(rid) is not int or not 0 < rid <= 2**63 - 1 or not name.strip() or (last and last < first):
            raise ValueError("Invalid APP-02 repository registry entry")
        registry.append({"repository_id": rid, "repository_name": name,
                         "tracking_start_date": first.isoformat(), "tracking_end_date": last.isoformat() if last else None,
                         "category": row.get("category"), "ecosystem": row.get("ecosystem")})
    if not registry or len({row["repository_id"] for row in registry}) != len(registry):
        raise ValueError("APP-02 pilot registry requires one interval per unique repository ID")
    return sorted(registry, key=lambda row: row["repository_id"])


def scope_key(registry):
    keys = [(row["repository_id"], row["tracking_start_date"], row["tracking_end_date"]) for row in registry]
    return sha256(json.dumps(sorted(keys)).encode()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def query_rows(sql):
    return [json.loads(line) for line in execute_clickhouse_sql(sql + " FORMAT JSONEachRow").splitlines()]


def insert_rows(table, rows):
    if rows:
        payload = "\n".join(json.dumps(row, ensure_ascii=False, allow_nan=False) for row in rows)
        execute_clickhouse_sql(f"INSERT INTO app_serving.{table} FORMAT JSONEachRow\n{payload}")


def select_gold(start, end, registry):
    ids = ",".join(str(row["repository_id"]) for row in registry)
    where = f"event_date BETWEEN '{start}' AND '{end}' AND repo_id IN ({ids})"
    columns = ", ".join(f"{column} AS {name}" for name, column in METRIC_SOURCES.items())
    gold = query_rows(f"SELECT event_date AS date, repo_id AS repository_id, {columns} "
                      f"FROM gold.gold_repo_daily_activity WHERE {where}")
    quality = query_rows(f"""
        SELECT event_date AS date, repo_id AS repository_id, count() AS silver_events,
            uniqExactIf(actor_id, actor_id > 0) AS unique_actors,
            uniqExactIf(actor_id, actor_id > 0 AND NOT is_bot) AS unique_human_actors,
            countIf(event_type = 'PullRequestEvent' AND isNull(action)) AS missing_pr_actions,
            countIf(event_type = 'IssuesEvent' AND isNull(action)) AS missing_issue_actions
        FROM silver.stg_gharchive_events FINAL WHERE {where} GROUP BY event_date, repo_id
    """)
    pushes = keyed(query_rows(f"""
        SELECT event_date AS date, repo_id AS repository_id, count() AS pushes,
            if(countIf(isNull(size) OR size < 0) = 0, sum(size), NULL) AS commits_pushed
        FROM (
            SELECT event_id,
                   toDate(parseDateTimeBestEffortOrZero(created_at, 'UTC')) AS event_date, repo_id,
                   toInt64OrNull(JSONExtractRaw(payload_json, 'size')) AS size
            FROM bronze.gharchive_events
            WHERE event_type = 'PushEvent' AND event_id != '' AND ifNull(repo_name, '') != '' AND {where}
            ORDER BY _ingested_at DESC
            LIMIT 1 BY event_id
        ) GROUP BY event_date, repo_id
    """))
    for row in quality:
        push = pushes.get((row["date"], int(row["repository_id"])))
        row["commits_pushed"] = push["commits_pushed"] if push else 0
        row["pushes"] = push["pushes"] if push else 0
    return gold, quality


def keyed(rows):
    result = {(row["date"], int(row["repository_id"])): row for row in rows}
    if len(result) != len(rows):
        raise ValueError("Duplicate Gold or Silver repo/day row")
    return result


def render_rows(registry, start, end, gold, quality, receipts):
    observed, silver = keyed(gold), keyed(quality)
    if observed.keys() != silver.keys() or any(int(row["total_events"]) != int(silver[key]["silver_events"])
                                              for key, row in observed.items()):
        raise ValueError("Gold repo/day coverage or event counts differ from Silver")
    hours = defaultdict(dict)
    for row in receipts:
        hours[row["date"]][int(row["hour"])] = row["processed_at"]

    statuses, daily = [], []
    for offset in range((end - start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        day_hours = hours[day]
        day_rows = []
        for registry_row in registry:
            if not registry_row["tracking_start_date"] <= day <= (registry_row["tracking_end_date"] or "9999-12-31"):
                continue
            rid = registry_row["repository_id"]
            source = observed.get((day, rid))
            values = dict.fromkeys(METRICS)
            if day_hours and source is not None:
                check = silver[day, rid]
                fields = {**source, **{key: check[key] for key in ("unique_actors", "unique_human_actors", "commits_pushed")}}
                values = {key: int(fields[key]) if fields.get(key) is not None else None for key in METRICS}
                if int(check["pushes"]) != values["push_events"]:
                    raise ValueError(f"Gold push count differs from Bronze for {rid} on {day}")
                if int(check["missing_pr_actions"]):
                    values.update(prs_opened=None, prs_merged=None, prs_closed_unmerged=None)
                if int(check["missing_issue_actions"]):
                    values.update(issues_opened=None, issues_closed=None)
                if (any(value is not None and not 0 <= value <= 2**63 - 1 for value in values.values())
                        or not values["unique_human_actors"] <= values["unique_actors"] <= values["total_events"]
                        or sum(values[key] or 0 for key in METRIC_SOURCES if key != "total_events") > values["total_events"]):
                    raise ValueError(f"Invalid APP-02 Gold counts for {rid} on {day}")
            day_rows.append({"repository_id": rid, "date": day, **values})
        complete_hours = set(day_hours) == set(range(24))
        quality_ok = not any(row["total_events"] is not None and any(row[key] is None for key in METRICS if key not in OPTIONAL)
                             for row in day_rows)
        complete = bool(day_rows and complete_hours and quality_ok)
        if complete:
            for row in day_rows:
                if row["total_events"] is None:
                    row.update(dict.fromkeys((key for key in METRICS if key != "active_contributors"), 0))
        status = "complete" if complete else "provisional" if day_hours else "missing"
        reason = "Incomplete hourly coverage" if not complete_hours else "Required metrics or scope unavailable"
        statuses.append({"date": day, "status": status, "expected_files": 24, "processed_files": len(day_hours),
                         "quality_passed": complete, "published_at": max(day_hours.values(), default=None),
                         "reason": None if complete else reason})
        daily.extend(day_rows)
    return statuses, daily


def initialize(schema):
    for statement in Path(schema).read_text(encoding="utf8").split(";"):
        if statement.strip():
            execute_clickhouse_sql(statement)
    execute_clickhouse_sql("""
        CREATE TABLE IF NOT EXISTS app_serving.gold_hour_receipts (
            scope_id String, run_id String, date Date, hour UInt8, rows UInt64, processed_at String
        ) ENGINE = MergeTree ORDER BY (scope_id, date, hour, run_id)
    """)


def publish(registry, items, run_id, schema, window_days=61):
    if not 1 <= window_days <= MAX_DAYS or not items or not run_id:
        raise ValueError("APP-02 needs a bounded window, processed hours and run ID")
    scope = scope_key(registry)
    key = sha256((scope + "\n" + run_id).encode()).hexdigest()
    receipts, stamp = [], utc_now()
    for item in items:
        day, hour, rows = date.fromisoformat(item["date_str"]).isoformat(), item["hour"], item["records"]
        if not 0 <= hour <= 23 or rows < 0:
            raise ValueError("Invalid successful hour receipt")
        receipts.append({"date": day, "hour": hour, "rows": rows, "scope_id": scope, "run_id": run_id, "processed_at": stamp})
    if len({(row["date"], row["hour"]) for row in receipts}) != len(receipts):
        raise ValueError("Duplicate receipt in a single dbt run")

    initialize(schema)
    run_token = f"-{key}-"
    previous = query_rows(f"SELECT publication_id, published_at FROM app_serving.app_publications "
                          f"WHERE startsWith(publication_id, 'zz-de-') AND position(publication_id, '{run_token}') > 0 LIMIT 2")
    if previous:
        if len(previous) != 1:
            raise ValueError("More than one publication committed for the same run")
        return previous[0]

    latest = query_rows("SELECT end_date FROM app_serving.app_publications ORDER BY published_at DESC, publication_id DESC LIMIT 1")
    end = date.fromisoformat(max([row["date"] for row in receipts] + [row["end_date"] for row in latest]))
    start = max(end - timedelta(days=window_days - 1), min(date.fromisoformat(row["tracking_start_date"]) for row in registry))
    if start > end or ((end - start).days + 1) * len(registry) > MAX_ROWS:
        raise ValueError("APP-02 publication window exceeds reader limits")

    insert_rows("gold_hour_receipts", receipts)
    coverage = query_rows(f"SELECT date, hour, min(processed_at) AS processed_at FROM app_serving.gold_hour_receipts "
                          f"WHERE scope_id = '{scope}' AND date BETWEEN '{start}' AND '{end}' GROUP BY date, hour")
    statuses, daily = render_rows(registry, start, end, *select_gold(start, end, registry), coverage)
    if not daily or len(daily) > MAX_ROWS or len(registry) > MAX_ROWS:
        raise ValueError("APP-02 publication has no rows or exceeds reader limits")
    generation = 1 + int(execute_clickhouse_sql("SELECT count() FROM app_serving.app_publications"))
    publication_id = f"zz-de-{generation:020d}{run_token}{uuid4().hex}"
    counts = {}
    for table, count_key, rows in (("repository_registry", "registry_rows", registry), ("repository_metadata", "metadata_rows", []),
                                   ("daily_data_status", "status_rows", statuses), ("repository_daily_metrics", "metric_rows", daily)):
        insert_rows(table, [{"publication_id": publication_id, **row} for row in rows])
        stored = execute_clickhouse_sql(f"SELECT count() FROM app_serving.{table} WHERE publication_id = '{publication_id}'")
        if int(stored) != len(rows):
            raise ValueError(f"Staged APP-02 row count differs for {table}")
        counts[count_key] = len(rows)
    marker = {"publication_id": publication_id, "start_date": start.isoformat(), "end_date": end.isoformat(),
              "contract_version": "1.0.0-draft", "expected_complete_through": None, "published_at": utc_now(), **counts}
    insert_rows("app_publications", [marker])
    return marker
