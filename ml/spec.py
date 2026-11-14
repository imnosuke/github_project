"""Executable ML-01 calendar/label contract, independent of serving and training."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
from numbers import Integral
from typing import Mapping

SPEC_VERSION = "ml-stars-30d-v1"
LOOKBACK_DAYS = 30
HORIZON_DAYS = 30


@dataclass(frozen=True)
class SampleWindow:
    feature_start: date
    feature_end: date
    label_start: date
    label_end: date

    @property
    def feature_cutoff_exclusive(self) -> datetime:
        """Events/metadata must precede next midnight UTC, not the run time."""
        return datetime.combine(self.label_start, time.min, tzinfo=timezone.utc)


def sample_window(anchor: date) -> SampleWindow:
    return SampleWindow(
        anchor - timedelta(days=LOOKBACK_DAYS - 1), anchor,
        anchor + timedelta(days=1), anchor + timedelta(days=HORIZON_DAYS),
    )


@dataclass(frozen=True)
class TemporalSplit:
    """Global anchor boundaries for all repositories; no random row splitting."""
    train_start: date
    validation_start: date
    test_start: date
    test_end: date

    def __post_init__(self):
        if not (
            self.train_start < self.validation_start
            < self.test_start <= self.test_end
        ):
            raise ValueError(
                "Require train_start < validation_start < test_start <= test_end"
            )
        # Each fit/tuning block must retain at least one matured label.
        if (self.validation_start - self.train_start).days <= HORIZON_DAYS:
            raise ValueError("Training block is too short after label purge")
        if (self.test_start - self.validation_start).days <= HORIZON_DAYS:
            raise ValueError("Validation block is too short after label purge")

    def partition(self, anchor: date) -> str:
        if anchor < self.train_start or anchor > self.test_end:
            return "outside"
        label_end = sample_window(anchor).label_end
        if anchor < self.validation_start:
            return "train" if label_end < self.validation_start else "purged"
        if anchor < self.test_start:
            return "validation" if label_end < self.test_start else "purged"
        return "test"


def star_label(anchor: date, counts: Mapping[date, int | None],
               statuses: Mapping[date, str]) -> int:
    """One repo's already validated dense contract rows; no filling missing days.

    Registry scope, publication consistency and actual availability are upstream
    gates. Future label availability must NEVER gate production inference.
    """
    window = sample_window(anchor)
    total = 0
    for offset in range(HORIZON_DAYS):
        day = window.label_start + timedelta(days=offset)
        if statuses.get(day) != "complete":
            raise ValueError(f"Label day is not complete: {day}")
        value = counts.get(day)
        if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
            raise ValueError(f"Label count must be a nonnegative integer: {day}")
        total += int(value)
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "anchor", "train-start", "validation-start", "test-start", "test-end"
    ]:
        parser.add_argument("--" + name, type=date.fromisoformat, required=True)
    args = parser.parse_args()
    split = TemporalSplit(
        args.train_start, args.validation_start, args.test_start, args.test_end
    )
    window = sample_window(args.anchor)
    print(json.dumps({"spec_version": SPEC_VERSION, "window": asdict(window),
                      "feature_cutoff_exclusive": window.feature_cutoff_exclusive,
                      "partition": split.partition(args.anchor)}, default=str, indent=2))


if __name__ == "__main__":
    main()
