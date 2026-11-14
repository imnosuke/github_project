from datetime import date, timedelta

import pytest

from ml.spec import HORIZON_DAYS, TemporalSplit, sample_window, star_label


def test_windows_cross_leap_day_without_overlap():
    window = sample_window(date(2024, 2, 29))
    assert window.feature_start == date(2024, 1, 31)
    assert window.label_start == date(2024, 3, 1)
    assert window.label_end == date(2024, 3, 30)
    assert str(window.feature_cutoff_exclusive) == "2024-03-01 00:00:00+00:00"


def split():
    return TemporalSplit(date(2026, 1, 30), date(2026, 5, 1),
                         date(2026, 7, 1), date(2026, 7, 30))


@pytest.mark.parametrize("anchor,expected", [
    ("2026-01-29", "outside"), ("2026-01-30", "train"),
    ("2026-03-31", "train"), ("2026-04-01", "purged"),
    ("2026-04-30", "purged"), ("2026-05-01", "validation"),
    ("2026-05-31", "validation"), ("2026-06-01", "purged"),
    ("2026-06-30", "purged"), ("2026-07-01", "test"),
    ("2026-07-30", "test"), ("2026-07-31", "outside"),
])
def test_split_boundaries(anchor, expected):
    assert split().partition(date.fromisoformat(anchor)) == expected


def test_all_training_and_validation_labels_mature_before_next_block():
    config = split()
    for offset in range((config.test_end - config.train_start).days + 1):
        anchor = config.train_start + timedelta(days=offset)
        block = config.partition(anchor)
        end = sample_window(anchor).label_end
        if block == "train":
            assert end < config.validation_start
        elif block == "validation":
            assert end < config.test_start


@pytest.mark.parametrize("validation,test", [
    ("2026-01-30", "2026-07-01"),
    ("2026-03-01", "2026-07-01"),
    ("2026-05-01", "2026-05-31"),
])
def test_invalid_or_empty_after_purge_splits(validation, test):
    with pytest.raises(ValueError):
        TemporalSplit(date(2026, 1, 30), date.fromisoformat(validation),
                      date.fromisoformat(test), date(2026, 7, 30))


def label_inputs():
    anchor = date(2026, 1, 30)
    counts = {anchor + timedelta(days=i): i for i in range(1, HORIZON_DAYS + 1)}
    return anchor, counts, dict.fromkeys(counts, "complete")


def test_label_excludes_anchor_and_day_31():
    anchor, counts, statuses = label_inputs()
    counts[anchor] = counts[anchor + timedelta(days=31)] = 999999
    assert star_label(anchor, counts, statuses) == 465
    assert star_label(anchor, dict.fromkeys(counts, 0), statuses) == 0


@pytest.mark.parametrize("status", [None, "missing", "provisional"])
def test_label_rejects_incomplete_day(status):
    anchor, counts, statuses = label_inputs()
    day = anchor + timedelta(days=10)
    if status is None:
        del statuses[day]
    else:
        statuses[day] = status
    with pytest.raises(ValueError, match="not complete"):
        star_label(anchor, counts, statuses)


@pytest.mark.parametrize("value", [None, -1, 1.5, True])
def test_label_rejects_unknown_or_invalid_count(value):
    anchor, counts, statuses = label_inputs()
    counts[anchor + timedelta(days=10)] = value
    with pytest.raises(ValueError, match="nonnegative integer"):
        star_label(anchor, counts, statuses)


def test_label_rejects_absent_count():
    anchor, counts, statuses = label_inputs()
    del counts[anchor + timedelta(days=10)]
    with pytest.raises(ValueError, match="nonnegative integer"):
        star_label(anchor, counts, statuses)
