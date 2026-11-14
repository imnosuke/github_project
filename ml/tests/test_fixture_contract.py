"""Fixture calendar audit, not a model quality evaluation."""
from datetime import date, timedelta
from numbers import Integral

from apps.streamlit.data import get_adapter
from ml.spec import sample_window, star_label


def test_fixture_has_label_examples_but_not_an_evaluation_timeline():
    adapter = get_adapter()
    lower, upper = map(date.fromisoformat, adapter.date_bounds())
    statuses = {date.fromisoformat(row.date): row.status
                for row in adapter.day_status(str(lower), str(upper)).itertuples()}
    eligible = {}
    for repo in adapter.repository_catalog().itertuples():
        counts = {date.fromisoformat(row.date): row.star_events for row in
                  adapter.time_series(repo.repository_id, str(lower), str(upper)).itertuples()}
        anchors = []
        for offset in range((upper - lower).days + 1):
            anchor = lower + timedelta(days=offset)
            window = sample_window(anchor)
            days = [window.feature_start + timedelta(days=i) for i in range(30)]
            if any(statuses.get(day) != "complete" or not isinstance(counts.get(day), Integral)
                   for day in days):
                continue
            try:
                value = star_label(anchor, counts, statuses)
            except ValueError:
                continue
            assert isinstance(value, int) and value >= 0
            anchors.append(anchor)
        eligible[repo.repository_id] = anchors

    assert eligible.pop(1005) == []
    for anchors in eligible.values():
        assert len(anchors) == 20
        assert anchors[0] == date(2026, 9, 14)
        assert anchors[-1] == date(2026, 10, 3)
    assert sum(map(len, eligible.values())) == 100
