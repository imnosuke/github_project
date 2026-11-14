from apps.streamlit.data import FixtureAdapter
from apps.streamlit.data.generate_fixture import generate
from apps.streamlit.explorer import prepared_series, summary


def test_complete_summary_and_incomplete_gap(tmp_path):
    generate(tmp_path)
    adapter = FixtureAdapter(tmp_path)
    rows = prepared_series(adapter, 1001, "2026-10-26", "2026-11-01")
    assert summary(rows, "2026-10-26", "2026-11-01")["star_events"] == 59
    rows = prepared_series(adapter, 1001, "2026-11-01", "2026-11-03")
    assert rows.loc[rows.date == "2026-11-03", "star_events"].isna().all()
    assert summary(rows, "2026-11-01", "2026-11-03") is None
    rows = prepared_series(adapter, 1005, "2026-10-01", "2026-11-01")
    assert summary(rows, "2026-10-01", "2026-11-01") is None
