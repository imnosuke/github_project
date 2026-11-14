import pandas as pd
import pytest

from apps.streamlit.data.adapter import FixtureAdapter
from apps.streamlit.data.generate_fixture import generate


@pytest.fixture
def adapter(tmp_path):
    generate(tmp_path)
    return FixtureAdapter(tmp_path)


def test_growth_expected_values(adapter):
    result = adapter.growth_ranking("2026-11-01", 30).set_index("repository_id")
    assert result.loc[1003, "state"] == "no_activity"
    assert result.loc[1003, "growth_pct"] == 0
    assert result.loc[1004, "state"] == "new_activity"
    assert pd.isna(result.loc[1004, "growth_pct"])
    assert result.loc[1005, "state"] == "insufficient_history"
    assert result.loc[1001, "absolute_delta"] > 0
    assert result.loc[1002, "absolute_delta"] < 0
    # Inclusive windows: Oct 26–Nov 1 versus Oct 19–25.
    result = adapter.growth_ranking("2026-11-01", 7).set_index("repository_id")
    assert result.loc[1001, "current"] == 59
    assert result.loc[1001, "previous"] == 55
    assert result.loc[1001, "growth_pct"] == pytest.approx(100 * 4 / 55)


def test_missing_and_provisional_are_not_zero(adapter):
    assert adapter.growth_ranking("2026-08-20", 7).iloc[0].state == "incomplete_data"
    rows = adapter.time_series(1001, "2026-08-15", "2026-08-15")
    assert rows.star_events.isna().all()
    result = adapter.growth_ranking("2026-11-03", 7)
    assert set(result.state) == {"incomplete_data"}


def test_detail_search_and_bounds(adapter):
    assert adapter.repository_detail(1006)["metadata"] is None
    assert len(adapter.list_repositories("RISING")) == 1
    assert len(adapter.list_repositories(offset=1, limit=2)) == 2
    with pytest.raises(KeyError): adapter.repository_detail(999)
    with pytest.raises(ValueError): adapter.time_series(1001, "2026-11-02", "2026-11-01")


def test_reject_duplicate_and_invalid_quality(adapter):
    original = adapter.tables["repository_daily_metrics"].copy()
    adapter.tables["repository_daily_metrics"] = pd.concat([original, original.iloc[:1]])
    with pytest.raises(ValueError, match="duplicate key"): adapter.validate()
    adapter.tables["repository_daily_metrics"] = original
    adapter.tables["daily_data_status"].loc[0, "processed_files"] = 23
    with pytest.raises(ValueError, match="quality gates"): adapter.validate()
