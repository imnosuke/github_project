from datetime import date, timedelta

import pandas as pd
import pytest

from apps.streamlit.data.adapter import COUNTS


@pytest.fixture
def input_frames():
    registry = pd.DataFrame([{"repository_id": 1, "tracking_start_date": "2025-01-01",
                              "tracking_end_date": None}])
    daily, statuses = [], []
    for offset in range(300):
        day = (date(2025, 1, 1) + timedelta(days=offset)).isoformat()
        counts = dict.fromkeys(COUNTS, 0)
        counts.update(star_events=offset + 1, total_events=offset + 6,
                      fork_events=3, push_events=2, unique_actors=3,
                      unique_human_actors=2, active_contributors=None)
        daily.append({"repository_id": 1, "date": day, **counts})
        statuses.append({"date": day, "status": "complete", "expected_files": 24,
                         "processed_files": 24, "quality_passed": True,
                         "published_at": f"{day}T23:59:59Z"})
    publication = {"contract_version": "1.0.0-draft", "data_source": "fixture",
                   "publication_id": "test-001", "published_at": "2025-11-01T03:00:00Z"}
    return registry, pd.DataFrame(daily), pd.DataFrame(statuses), publication
