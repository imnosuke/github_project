"""Validated, retrospective inputs via the public serving interface."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from numbers import Real

import pandas as pd

from apps.streamlit.data.adapter import COUNTS, DataAdapter


def iso_day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Dates must be YYYY-MM-DD strings")
    return value


def utc_timestamp(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("Publication timestamps must be explicit UTC")
    return stamp


class Inputs:
    """Copy and validate inputs once; no mutation of the adapter or densification.

    Missing status/metric rows remain unknown and exclude affected samples.
    Malformed rows, duplicates and complete-day null counts fail validation.
    """
    def __init__(self, registry, daily, statuses, publication):
        registry, daily, statuses = (frame.copy(deep=True) for frame in
                                     (registry, daily, statuses))
        self.publication = dict(publication)
        if (publication.get("contract_version") != "1.0.0-draft"
                or publication.get("data_source") not in {"fixture", "live"}
                or not isinstance(publication.get("publication_id"), str)
                or not publication["publication_id"].strip()):
            raise ValueError("Unsupported or missing publication contract")
        publication_time = utc_timestamp(publication.get("published_at"))
        required = [
            (registry, ["repository_id", "tracking_start_date", "tracking_end_date"]),
            (daily, ["repository_id", "date", *COUNTS]),
            (statuses, ["date", "status", "expected_files", "processed_files",
                        "quality_passed", "published_at"]),
        ]
        for frame, columns in required:
            if set(columns) - set(frame.columns):
                raise ValueError(f"Missing columns: {sorted(set(columns) - set(frame.columns))}")
        for frame, keys in [(registry, ["repository_id", "tracking_start_date"]),
                            (daily, ["repository_id", "date"]), (statuses, ["date"])]:
            if frame[keys].isna().any().any() or frame.duplicated(keys).any():
                raise ValueError("Null or duplicate input keys")
        for frame in (registry, daily):
            for value in frame.repository_id:
                if (isinstance(value, bool) or not isinstance(value, Real)
                        or not 0 < value <= 2**63 - 1 or int(value) != value):
                    raise ValueError("Repository IDs must be positive int64")
        for values in (registry.tracking_start_date, daily.date, statuses.date):
            for value in values:
                iso_day(value)
        self.scope = {}
        for rid, intervals in registry.groupby("repository_id", sort=True):
            previous_end = None
            self.scope[int(rid)] = []
            for row in intervals.sort_values("tracking_start_date").itertuples():
                start = iso_day(row.tracking_start_date)
                end = "9999-12-31" if pd.isna(row.tracking_end_date) else iso_day(row.tracking_end_date)
                if end < start or (previous_end is not None and start <= previous_end):
                    raise ValueError("Invalid or overlapping registry intervals")
                self.scope[int(rid)].append((start, end))
                previous_end = end
        self.statuses = {}
        for row in statuses.to_dict("records"):
            if row["status"] not in {"complete", "provisional", "missing"}:
                raise ValueError("Invalid day status")
            for key in ("expected_files", "processed_files"):
                value = row[key]
                if (isinstance(value, bool) or not isinstance(value, Real)
                        or not math.isfinite(value) or int(value) != value):
                    raise ValueError("Invalid file counts")
            if row["expected_files"] != 24 or not 0 <= row["processed_files"] <= 24:
                raise ValueError("Invalid file counts")
            if not isinstance(row["quality_passed"], bool):
                raise ValueError("quality_passed must be boolean")
            if not pd.isna(row["published_at"]):
                if utc_timestamp(row["published_at"]) > publication_time:
                    raise ValueError("Day publication is newer than input publication")
            if row["status"] == "complete":
                if row["processed_files"] != 24 or not row["quality_passed"]:
                    raise ValueError("Complete day failed quality gates")
                utc_timestamp(row["published_at"])
            self.statuses[row["date"]] = row["status"]
        self.daily = {}
        optional = {"commits_pushed", "active_contributors"}
        for row in daily.to_dict("records"):
            rid, day = int(row["repository_id"]), row["date"]
            if not self.in_scope(rid, day):
                raise ValueError("Daily row outside registry scope")
            status = self.statuses.get(day)
            for metric in COUNTS:
                value = row[metric]
                if pd.isna(value):
                    if status == "complete" and metric not in optional:
                        raise ValueError("Null required complete-day metric")
                    row[metric] = None
                else:
                    if (isinstance(value, bool) or not isinstance(value, Real)
                            or not 0 <= value <= 2**63 - 1 or int(value) != value):
                        raise ValueError("Counts must be nonnegative int64")
                    if status == "missing":
                        raise ValueError("Missing day must have null metrics")
                    row[metric] = int(value)
            if all(row[c] is not None for c in ("unique_actors", "unique_human_actors", "total_events")):
                if not row["unique_human_actors"] <= row["unique_actors"] <= row["total_events"]:
                    raise ValueError("Invalid actor counts")
            event_parts = ["star_events", "fork_events", "push_events", "prs_opened",
                           "prs_merged", "prs_closed_unmerged", "issues_opened",
                           "issues_closed", "issue_comments"]
            if row["total_events"] is not None and sum(row[c] or 0 for c in event_parts) > row["total_events"]:
                raise ValueError("Event components exceed total")
            self.daily[rid, day] = row
        all_days = set(self.statuses) | {day for _, day in self.daily}
        if not all_days:
            raise ValueError("No input dates")
        self.lower, self.upper = min(all_days), max(all_days)
        canonical = {
            "publication": self.publication, "scope": self.scope,
            "statuses": statuses.sort_values("date").to_json(orient="records"),
            "daily": daily.sort_values(["repository_id", "date"]).to_json(orient="records"),
        }
        self.fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()

    def in_scope(self, rid, day):
        return any(start <= day <= end for start, end in self.scope.get(rid, []))

    @classmethod
    def from_adapter(cls, adapter: DataAdapter):
        before = adapter.publication()
        bounds = adapter.date_bounds()
        if bounds is None:
            raise ValueError("No input dates")
        registry = adapter.registry_history()
        columns = ["repository_id", "date", *COUNTS]
        frames = []
        for rid in sorted(registry.repository_id.unique()):
            frame = adapter.time_series(int(rid), *bounds)
            missing = set(columns) - set(frame.columns)
            if missing:
                raise ValueError(f"Missing time-series columns: {sorted(missing)}")
            # Nullable metrics are still required fields in contract v1.
            frames.append(frame.loc[:, columns])
        daily = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
        statuses = adapter.day_status(*bounds)
        if before != adapter.publication():
            raise ValueError("Publication changed while reading inputs")
        return cls(registry, daily, statuses, before)
