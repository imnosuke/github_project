from copy import deepcopy
import re

import pytest

from apps.streamlit.data import clickhouse_publication as module
from apps.streamlit.data.adapter import COUNTS
from apps.streamlit.data.config import ClickHouseConfig


DAY = "2025-01-15"
STAMP = "2025-01-16T06:00:00Z"


@pytest.fixture
def publication(monkeypatch):
    rows = {
        "app_publications": [{
            "publication_id": "qa-one", "contract_version": "1.0.0-draft",
            "published_at": STAMP, "start_date": DAY, "end_date": DAY,
            "expected_complete_through": DAY,
        }],
        "repository_registry": [{
            "repository_id": "1", "repository_name": "test/one",
            "tracking_start_date": DAY, "tracking_end_date": None,
            "category": None, "ecosystem": None,
        }],
        "repository_metadata": [],
        "daily_data_status": [{
            "date": DAY, "status": "complete", "expected_files": "24",
            "processed_files": "24", "quality_passed": True, "published_at": STAMP, "reason": None,
        }],
        "repository_daily_metrics": [{
            "repository_id": "1", "date": DAY, **dict.fromkeys(COUNTS, "0"),
            "total_events": "42", "star_events": "5",
            "commits_pushed": None, "active_contributors": None,
        }],
    }
    reads = []

    def read(_config, query, params, row_limit):
        name = re.search(r"FROM \{database:Identifier\}\.(\w+)", query)[1]
        reads.append(name)
        if name != "app_publications":
            assert params["publication"] == "qa-one"
            assert params["limit"] == row_limit + 1
            if name in {"daily_data_status", "repository_daily_metrics"}:
                assert params["start"] == params["end"] == DAY
        return deepcopy(rows[name])

    monkeypatch.setattr(module, "read_rows", read)
    return rows, reads


def test_publication_is_pinned_and_preserves_counts(publication):
    adapter = module.ClickHousePublicationAdapter(ClickHouseConfig("localhost"))
    _, reads = publication
    assert reads == ["app_publications", *module.DATASETS]
    assert adapter.publication()["data_source"] == "live"
    assert adapter.overview(DAY, DAY)["totals"]["star_events"] == 5
    assert adapter.repository_detail(1)["metadata"] is None


@pytest.mark.parametrize("change,message", [
    (lambda rows: rows["daily_data_status"].clear(), "daily status coverage"),
    (lambda rows: rows["repository_daily_metrics"].clear(), "not dense"),
    (lambda rows: rows["repository_daily_metrics"][0].update(prs_merged=None), "Null required"),
    (lambda rows: rows["repository_daily_metrics"][0].update(star_events=True), "Invalid APP-02 integer"),
    (lambda rows: rows["daily_data_status"][0].update(published_at="2025-01-17T06:00:00Z"), "newer"),
    (lambda rows: rows["app_publications"][0].update(start_date="2020-01-01"), "date span"),
])
def test_publication_fails_closed(publication, change, message):
    rows, _ = publication
    change(rows)
    with pytest.raises(ValueError, match=message):
        module.ClickHousePublicationAdapter(ClickHouseConfig("localhost"))


def test_remote_requires_https():
    with pytest.raises(ValueError, match="requires HTTPS"):
        module.ClickHousePublicationAdapter(ClickHouseConfig("clickhouse.internal", secure=False))
