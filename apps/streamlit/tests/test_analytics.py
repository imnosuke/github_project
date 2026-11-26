from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from apps.streamlit.analytics import default_date_range, overview_data
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


def test_default_window_finds_latest_two_complete_periods_across_a_gap():
    lower, upper = date(2025, 1, 1), date(2025, 3, 12)
    complete = pd.date_range(lower, upper).strftime("%Y-%m-%d").drop("2025-03-02")
    adapter = SimpleNamespace(day_status=lambda start, end: pd.DataFrame({"date": complete, "status": "complete"}))
    assert default_date_range(adapter, lower, upper, upper.isoformat()) == (date(2025, 1, 31), date(2025, 3, 1))


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


def test_growth_sorting_options():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    app.sidebar.date_input[0].set_value((date(2026, 10, 4), date(2026, 11, 2))).run()
    app.sidebar.radio[0].set_value("Growth Analytics").run()
    assert not app.exception
    app.selectbox[1].set_value("Absolute delta").run()
    assert not app.exception
    app.selectbox[1].set_value("Growth % (baseline > 0)").run()
    assert not app.exception


def test_growth_shows_completeness_for_both_periods():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    app.sidebar.date_input(key="date_range").set_value((date(2026, 8, 21), date(2026, 8, 24))).run()
    app.sidebar.radio(key="page").set_value("Growth Analytics").run()
    app.selectbox[0].set_value(7).run()
    assert not app.exception
    assert any("Hai kỳ so sánh · 1 ngày chưa complete" == item.value for item in app.warning)
    status = app.dataframe[-1].value
    assert len(status) == 14
    assert status.date.min() == "2026-08-11"

