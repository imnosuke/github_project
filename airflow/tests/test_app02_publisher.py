from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import app02_publisher as publisher


DAY = date(2025, 1, 15)
STAMP = "2026-11-26T10:00:00Z"
REGISTRY = [{"repository_id": rid, "repository_name": f"repo/{rid}", "tracking_start_date": DAY.isoformat(),
             "tracking_end_date": None, "category": None, "ecosystem": None} for rid in (1, 2)]
GOLD = {"repository_id": 1, "date": DAY.isoformat(), **dict.fromkeys(publisher.METRIC_SOURCES, 0), "total_events": 1}
QUALITY = {"repository_id": 1, "date": DAY.isoformat(), "silver_events": 1, "unique_actors": 1,
           "unique_human_actors": 1, "missing_pr_actions": 0, "missing_issue_actions": 0, "commits_pushed": None, "pushes": 0}


def receipts(n):
    return [{"date": DAY.isoformat(), "hour": hour, "processed_at": STAMP} for hour in range(n)]


@pytest.mark.parametrize("hours,pr_count,status,empty_total", [
    (0, 0, "missing", None), (23, 0, "provisional", None), (24, 0, "complete", 0),
    (24, None, "provisional", None),
])
def test_status_requires_scoped_hours_and_required_metrics(hours, pr_count, status, empty_total):
    gold = {**GOLD, "prs_merged": pr_count}
    days, rows = publisher.render_rows(REGISTRY, DAY, DAY, [gold], [QUALITY], receipts(hours))
    assert days[0]["status"] == status
    assert days[0]["processed_files"] == hours
    assert rows[1]["total_events"] == empty_total
    if hours:
        assert rows[0]["prs_merged"] == pr_count
        assert rows[0]["commits_pushed"] is None


def test_refuses_fabricated_zero_when_gold_omits_repo_day():
    with pytest.raises(ValueError, match="differ from Silver"):
        publisher.render_rows(REGISTRY, DAY, DAY, [], [QUALITY], receipts(24))


def test_publication_manifest_written_last_and_only_after_row_checks(monkeypatch):
    writes = []
    monkeypatch.setattr(publisher, "initialize", lambda _: None)
    monkeypatch.setattr(publisher, "query_rows", lambda query: receipts(24) if "GROUP BY" in query else [])
    monkeypatch.setattr(publisher, "select_gold", lambda *_: ([GOLD], [QUALITY]))
    monkeypatch.setattr(publisher, "insert_rows", lambda table, rows: writes.append((table, len(rows))))

    def stored(sql):
        table = sql.split("app_serving.")[1].split()[0]
        return str(dict(writes).get(table, 0))

    monkeypatch.setattr(publisher, "execute_clickhouse_sql", stored)
    item = {"date_str": DAY.isoformat(), "hour": 0, "records": 1}
    marker = publisher.publish(REGISTRY, [item], "run-test", "schema")
    assert writes[-1] == ("app_publications", 1)
    assert marker["metric_rows"] == 2 and marker["status_rows"] == 1
    writes.clear()
    monkeypatch.setattr(publisher, "execute_clickhouse_sql", lambda _: "0")
    with pytest.raises(ValueError, match="Staged APP-02 row count differs"):
        publisher.publish(REGISTRY, [item], "failed-run", "schema")
    assert all(table != "app_publications" for table, _ in writes)
