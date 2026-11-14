from datetime import date

import pandas as pd
import pytest

from apps.streamlit.data import get_adapter
from ml.data import Inputs
from ml.features import FEATURES, Ineligible, build_dataset, feature_row, label
from ml.spec import TemporalSplit


def test_exact_feature_windows_and_actor_mean(input_frames):
    data = Inputs(*input_frames)
    features = feature_row(data, 1, date(2025, 1, 30))
    assert tuple(features) == FEATURES and len(FEATURES) == 28
    assert features["star_events_sum_30d"] == 465
    assert features["star_events_sum_7d"] == 189
    assert features["active_days_30d"] == 30
    assert features["unique_actors_daily_mean_30d"] == 3
    assert features["unique_human_actors_daily_max_7d"] == 2
    assert "repository_id" not in FEATURES
    assert "active_contributors" not in FEATURES
    assert label(data, 1, date(2025, 1, 30)) == sum(range(31, 61))


def test_future_activity_changes_label_but_not_features(input_frames):
    original = Inputs(*input_frames)
    registry, daily, statuses, publication = input_frames
    future = daily.date > "2025-03-01"
    daily.loc[future, "star_events"] *= 10
    daily.loc[future, "total_events"] *= 10
    changed = Inputs(registry, daily, statuses, publication)
    anchor = date(2025, 3, 1)
    assert feature_row(original, 1, anchor) == feature_row(changed, 1, anchor)
    assert label(original, 1, anchor) != label(changed, 1, anchor)


def test_features_work_without_future_labels(input_frames):
    registry, daily, statuses, publication = input_frames
    truncated = Inputs(registry, daily[daily.date <= "2025-03-01"],
                       statuses[statuses.date <= "2025-03-01"], publication)
    anchor = date(2025, 3, 1)
    assert feature_row(truncated, 1, anchor) == feature_row(Inputs(*input_frames), 1, anchor)
    with pytest.raises(Ineligible, match="unmatured_label"):
        label(truncated, 1, anchor)


@pytest.mark.parametrize("case", ["status_absent", "metric_row_absent", "provisional", "missing"])
def test_missing_and_incomplete_days_are_not_zero(input_frames, case):
    registry, daily, statuses, publication = input_frames
    day = "2025-02-20"
    if case == "status_absent":
        statuses = statuses[statuses.date != day]
    elif case == "metric_row_absent":
        daily = daily[daily.date != day]
    else:
        statuses.loc[statuses.date == day, "status"] = case
        if case == "missing":
            from apps.streamlit.data.adapter import COUNTS
            daily = daily.astype({column: "object" for column in COUNTS})
            daily.loc[daily.date == day, COUNTS] = None
    data = Inputs(registry, daily, statuses, publication)
    with pytest.raises(Ineligible, match="incomplete_features"):
        feature_row(data, 1, date(2025, 3, 1))
    with pytest.raises(Ineligible, match="incomplete_label"):
        label(data, 1, date(2025, 2, 1))


def test_tracking_gap_and_ended_scope_are_respected(input_frames):
    registry, daily, statuses, publication = input_frames
    registry.loc[0, "tracking_end_date"] = "2025-02-15"
    registry = pd.concat([registry, pd.DataFrame([{"repository_id": 1,
        "tracking_start_date": "2025-03-01", "tracking_end_date": "2025-04-30"}])])
    daily = daily[((daily.date <= "2025-02-15") | (daily.date >= "2025-03-01")) & (daily.date <= "2025-04-30")]
    data = Inputs(registry, daily, statuses, publication)
    with pytest.raises(Ineligible, match="out_of_scope"):
        feature_row(data, 1, date(2025, 3, 10))
    assert feature_row(data, 1, date(2025, 3, 30))
    with pytest.raises(Ineligible, match="out_of_scope"):
        label(data, 1, date(2025, 4, 15))


def test_app_fixture_audit_and_features_only_mode():
    data = Inputs.from_adapter(get_adapter())
    split = TemporalSplit(date(2026, 8, 30), date(2026, 10, 1), date(2026, 11, 1), date(2026, 11, 3))
    samples, audit = build_dataset(data, date(2026, 8, 1), date(2026, 11, 3), split)
    assert len(audit) == 570 and len(samples) == 5
    assert audit.reason.value_counts()["purged"] == 95
    assert set(samples.split) == {"validation"}
    assert 1006 in set(samples.repository_id)  # No metadata needed.
    features, _ = build_dataset(data, date(2026, 11, 2), date(2026, 11, 2), split, features_only=True)
    assert len(features) == 5 and "target" not in features


@pytest.mark.parametrize("invalid", ["duplicate", "negative", "null_complete", "boolean", "fraction", "null_key", "bad_quality", "overlap", "reversed_interval", "future_publication"])
def test_invalid_input_fails_before_sample_filtering(input_frames, invalid):
    registry, daily, statuses, publication = input_frames
    daily = daily.astype({"star_events": "object"})
    if invalid == "duplicate":
        daily = pd.concat([daily, daily.iloc[:1]])
    elif invalid == "null_key":
        daily.loc[0, "date"] = None
    elif invalid == "bad_quality":
        statuses.loc[0, "quality_passed"] = False
    elif invalid == "overlap":
        registry = pd.concat([registry, registry.assign(tracking_start_date="2025-02-01")])
    elif invalid == "reversed_interval":
        registry.loc[0, "tracking_end_date"] = "2024-12-31"
    elif invalid == "future_publication":
        statuses.loc[0, "published_at"] = "2026-01-01T00:00:00Z"
    else:
        daily.loc[0, "star_events"] = {"negative": -1, "null_complete": None, "boolean": True, "fraction": 1.5}[invalid]
    with pytest.raises(ValueError):
        Inputs(registry, daily, statuses, publication)


def test_publication_change_while_reading_is_rejected():
    fixture = get_adapter()
    class ChangingPublication:
        def __init__(self):
            self.calls = 0
        def publication(self):
            self.calls += 1
            return {**fixture.publication(), "publication_id": str(self.calls)}
        date_bounds = fixture.date_bounds
        registry_history = fixture.registry_history
        time_series = fixture.time_series
        day_status = fixture.day_status
    with pytest.raises(ValueError, match="Publication changed"):
        Inputs.from_adapter(ChangingPublication())


@pytest.mark.parametrize("column", ["commits_pushed", "active_contributors", "star_events"])
def test_adapter_cannot_omit_nullable_or_required_metric_columns(column):
    fixture = get_adapter()

    class MissingColumnAdapter:
        publication = fixture.publication
        date_bounds = fixture.date_bounds
        registry_history = fixture.registry_history
        day_status = fixture.day_status

        def time_series(self, *args):
            return fixture.time_series(*args).drop(columns=[column])

    with pytest.raises(ValueError, match=f"Missing time-series columns.*{column}"):
        Inputs.from_adapter(MissingColumnAdapter())
