from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from apps.streamlit.analytics import overview_data
from apps.streamlit.data import FixtureAdapter
from apps.streamlit.data.generate_fixture import generate


@pytest.fixture
def adapter(tmp_path):
    generate(tmp_path)
    return FixtureAdapter(tmp_path)


def test_overview_counts_and_gap(adapter):
    tracked, totals, trend = overview_data(adapter, "2026-10-26", "2026-11-01")
    assert tracked == 6
    assert totals["active_repositories"] == 5
    assert totals["star_events"] == 119  # 59 rising + 11 falling + 21 new + 14 short + 14 other
    assert totals["total_events"] == 119
    assert totals["fork_events"] == 0
    _, totals, trend = overview_data(adapter, "2026-08-14", "2026-08-16")
    assert totals is None
    assert trend.loc[trend.date == "2026-08-15", "star_events"].isna().all()


def test_ranking_order_and_zero_states(adapter):
    result = adapter.growth_ranking("2026-11-01", 30)
    valid = result[result.state.isin(["valid", "new_activity", "no_activity"])]
    assert valid.current.tolist() == sorted(valid.current.tolist(), reverse=True)
    assert result[result.repository_id == 1005].iloc[0].state == "insufficient_history"


def test_growth_ui_exclusions_and_incomplete():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    app.sidebar.radio[0].set_value("Growth Analytics").run()
    assert not app.exception
    app.sidebar.date_input[0].set_value((date(2026,11,1), date(2026,11,3))).run()
    assert not app.exception
    assert any("Chưa có repository đủ" in item.value for item in app.info)
