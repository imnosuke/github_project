"""Features and eligibility at event-time T; no future label dependency."""
from datetime import date, timedelta

import pandas as pd

from ml.data import Inputs
from ml.spec import sample_window, star_label, TemporalSplit

EVENTS = ("star_events", "fork_events", "total_events", "push_events", "prs_opened",
          "prs_merged", "issues_opened", "issues_closed", "issue_comments")
ACTORS = ("unique_actors", "unique_human_actors")
FEATURES = tuple(
    [f"{metric}_sum_{window}d" for window in (7, 30) for metric in EVENTS]
    + [f"active_days_{window}d" for window in (7, 30)]
    + [f"{metric}_daily_{stat}_{window}d" for window in (7, 30)
       for metric in ACTORS for stat in ("mean", "max")]
)


class Ineligible(ValueError):
    pass


def days_between(start, end):
    return [(start + timedelta(days=i)).isoformat()
            for i in range((end - start).days + 1)]


def feature_row(data: Inputs, repository_id: int, anchor: date) -> dict:
    window = sample_window(anchor)
    days = days_between(window.feature_start, window.feature_end)
    if not data.in_scope(repository_id, anchor.isoformat()):
        raise Ineligible("out_of_scope")
    first_scope = data.scope[repository_id][0][0]
    if days[0] < data.lower or days[0] < first_scope:
        raise Ineligible("insufficient_history")
    if any(not data.in_scope(repository_id, day) for day in days):
        raise Ineligible("out_of_scope")
    rows = [data.daily.get((repository_id, day)) for day in days]
    if any(data.statuses.get(day) != "complete" or row is None
           or any(row[c] is None for c in (*EVENTS, *ACTORS))
           for day, row in zip(days, rows)):
        raise Ineligible("incomplete_features")
    features = {}
    for length in (7, 30):
        recent = rows[-length:]
        for metric in EVENTS:
            features[f"{metric}_sum_{length}d"] = sum(row[metric] for row in recent)
        features[f"active_days_{length}d"] = sum(row["total_events"] > 0 for row in recent)
        for metric in ACTORS:
            values = [row[metric] for row in recent]
            features[f"{metric}_daily_mean_{length}d"] = sum(values) / length
            features[f"{metric}_daily_max_{length}d"] = max(values)
    return {name: features[name] for name in FEATURES}


def label(data: Inputs, repository_id: int, anchor: date) -> int:
    window = sample_window(anchor)
    if window.label_end.isoformat() > data.upper:
        raise Ineligible("unmatured_label")
    days = days_between(window.label_start, window.label_end)
    if any(not data.in_scope(repository_id, day) for day in days):
        raise Ineligible("out_of_scope")
    rows = [data.daily.get((repository_id, day)) for day in days]
    if any(data.statuses.get(day) != "complete" or row is None or row["star_events"] is None
           for day, row in zip(days, rows)):
        raise Ineligible("incomplete_label")
    return star_label(anchor, {date.fromisoformat(day): row["star_events"]
                              for day, row in zip(days, rows)},
                      dict.fromkeys(map(date.fromisoformat, days), "complete"))


def build_dataset(data: Inputs, start: date, end: date, split: TemporalSplit,
                  features_only=False):
    if start > end:
        raise ValueError("Anchor start must not follow end")
    samples, audit = [], []
    for rid in sorted(data.scope):
        for day in days_between(start, end):
            anchor = date.fromisoformat(day)
            block = "features" if features_only else split.partition(anchor)
            record = {"repository_id": rid, "anchor_date": day, "split": block}
            try:
                features = feature_row(data, rid, anchor)
                target = None if features_only else label(data, rid, anchor)
                if block in {"purged", "outside"}:
                    raise Ineligible(block)
            except Ineligible as exc:
                audit.append({**record, "reason": str(exc)})
                continue
            samples.append({**record, **features, **({} if features_only else {"target": target})})
            audit.append({**record, "reason": "kept"})
    columns = ["repository_id", "anchor_date", "split", *FEATURES]
    if not features_only:
        columns += ["target"]
    return pd.DataFrame(samples, columns=columns), pd.DataFrame(
        audit, columns=["repository_id", "anchor_date", "split", "reason"]
    )
