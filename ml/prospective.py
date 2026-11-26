"""Capture point-in-time shadow predictions and score them when labels mature."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pandas as pd

from apps.streamlit.data import get_adapter
from ml.data import Inputs, utc_timestamp
from ml.features import Ineligible, feature_row, label
from ml.observe_publication import record_observation
from ml.publication_files import commit_exclusive
from ml.spec import HORIZON_DAYS, SPEC_VERSION, sample_window
from ml.training import score


COHORT_ANCHORS = 30


def read_json(path):
    return json.loads(path.read_text(encoding="utf8"))


def write_once(path, value):
    commit_exclusive(path, json.dumps(value, indent=2, allow_nan=False) + "\n")


def capture(data, source_name, output, now):
    decision_at = utc_timestamp(now)
    anchor = decision_at.date() - timedelta(days=1)
    observation = record_observation(data, output / "observations", source_name, decision_at.isoformat())
    if utc_timestamp(observation["observed_at"]) > decision_at:
        raise ValueError("Publication observation is later than the decision")
    target = output / "predictions" / f"{anchor}.json"
    if target.exists():
        previous = read_json(target)
        if previous["source_name"] != source_name:
            raise ValueError("Journal belongs to another endpoint")
        return previous

    rows, excluded = [], {}
    for rid in sorted(data.scope):
        try:
            features = feature_row(data, rid, anchor)
        except Ineligible as exc:
            excluded[str(rid)] = str(exc)
            continue
        rows.append({"repository_id": rid, "persistence_30d": features["star_events_sum_30d"],
                     "zero": 0, "lookback_activity": features["total_events_sum_30d"]})
    if not rows:
        return {"status": "blocked", "anchor": anchor.isoformat(), "excluded": excluded,
                "reason": "No repositories have a complete feature window on the candidate day"}

    report = {
        "status": "captured", "mode": "prospective_shadow", "spec_version": SPEC_VERSION,
        "source_name": source_name, "anchor": anchor.isoformat(), "decision_at": decision_at.isoformat(),
        "publication": data.publication, "availability": observation, "horizon_days": HORIZON_DAYS,
        "rows": rows, "excluded": excluded,
    }
    try:
        write_once(target, report)
    except FileExistsError:
        winner = read_json(target)
        if winner["source_name"] != source_name:
            raise ValueError("Journal belongs to another endpoint") from None
        return winner
    return report


def evaluate(data, source_name, output):
    if data.publication["data_source"] != "live":
        raise ValueError("Prospective labels require a ClickHouse publication")
    target = output / "evaluation.json"
    if target.exists():
        result = read_json(target)
        if result["source_name"] != source_name:
            raise ValueError("Journal belongs to another endpoint")
        return result
    paths = sorted((output / "predictions").glob("*.json"))[:COHORT_ANCHORS]
    if len(paths) < COHORT_ANCHORS:
        return {"status": "blocked", "captures": len(paths), "required": COHORT_ANCHORS}

    cohort = [read_json(path) for path in paths]
    anchors = [datetime.fromisoformat(capture["anchor"]).date() for capture in cohort]
    for path, capture, anchor in zip(paths, cohort, anchors):
        available = utc_timestamp(capture["availability"]["observed_at"])
        decision = utc_timestamp(capture["decision_at"])
        if (path.stem != anchor.isoformat() or capture["source_name"] != source_name
                or capture["availability"]["source_name"] != source_name
                or capture["availability"]["publication_id"] != capture["publication"]["publication_id"]
                or capture["spec_version"] != SPEC_VERSION or capture["horizon_days"] != HORIZON_DAYS
                or available > decision or decision.date() != anchor + timedelta(days=1)):
            raise ValueError("Invalid prospective prediction record")
    last_needed = sample_window(anchors[-1]).label_end.isoformat()
    if data.upper < last_needed:
        return {"status": "blocked", "reason": "Label horizon has not matured", "required_through": last_needed}

    records = []
    for capture, anchor in zip(cohort, anchors):
        for row in capture["rows"]:
            try:
                actual = label(data, row["repository_id"], anchor)
            except Ineligible as exc:
                return {"status": "blocked", "reason": str(exc), "anchor": capture["anchor"],
                        "repository_id": row["repository_id"]}
            records.append({"anchor": capture["anchor"], **row, "target": actual})

    frame = pd.DataFrame(records)
    scores = {}
    for name in ("persistence_30d", "zero"):
        scores[name] = score(frame, frame[name])
        scores[name]["by_anchor"] = {day: score(group, group[name]) for day, group in frame.groupby("anchor")}
        scores[name]["by_activity"] = {
            key: score(group, group[name]) if len(group) else None
            for key, group in (("zero", frame.loc[frame.lookback_activity.eq(0)]),
                               ("nonzero", frame.loc[frame.lookback_activity.gt(0)]))
        }
    result = {"status": "completed", "mode": "prospective_shadow", "source_name": source_name,
              "first_anchor": anchors[0].isoformat(), "last_anchor": anchors[-1].isoformat(),
              "anchor_count": len(cohort), "label_publication": data.publication,
              "score": scores, "release_approved": False}
    try:
        write_once(target, result)
    except FileExistsError:
        winner = read_json(target)
        if winner["source_name"] != source_name:
            raise ValueError("Journal belongs to another endpoint") from None
        return winner
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "evaluate"))
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.source_name.strip():
        parser.error("--source-name must not be empty")
    data = Inputs.from_adapter(get_adapter("clickhouse"))
    report = (capture(data, args.source_name, args.output, datetime.now(timezone.utc))
              if args.action == "capture" else evaluate(data, args.source_name, args.output))
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
