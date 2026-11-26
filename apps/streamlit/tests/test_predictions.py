from datetime import datetime, timedelta, timezone

import pytest
from streamlit.testing.v1 import AppTest

from apps.streamlit import predictions


@pytest.mark.parametrize("condition", ["ready", "stale", "missing", "incomplete", "source_error"])
def test_prediction_detail_states(monkeypatch, condition):
    monkeypatch.setenv("APP_CLICKHOUSE_HOST", "127.0.0.1")
    monkeypatch.setenv("APP_PREDICTION_RELEASE_ID", "qa")
    monkeypatch.setenv("APP_PREDICTION_MAX_AGE_HOURS", "2")
    stamp = datetime.now(timezone.utc) - timedelta(hours=72 if condition == "stale" else 1)

    def get_batch(_config, anchor, release):
        assert anchor == "2026-01-01" and release == "qa"
        if condition == "source_error":
            raise OSError("temporary test failure")
        if condition == "missing":
            return None
        return {"generated_at": stamp.isoformat(), "rows": [{"repository_id": 1,
                "status": "insufficient_history" if condition == "incomplete" else "ready",
                "predicted_star_events": None if condition == "incomplete" else 0}]}

    monkeypatch.setattr(predictions, "read_prediction_publication", get_batch)
    app = AppTest.from_string("""
from apps.streamlit.predictions import render_predictions
render_predictions(None, '2026-01-01', repository_id=1)
""").run()
    assert not app.exception
    if condition == "ready":
        assert app.metric[0].value == "0.00"
    else:
        assert not app.metric
        assert app.warning or app.info
