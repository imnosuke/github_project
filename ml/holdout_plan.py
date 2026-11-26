"""Freeze the next ML-03 holdout using verified coverage, before model scoring."""

import argparse
from datetime import date, timedelta
import json
from pathlib import Path

from ml.publication_files import commit_exclusive
from ml.spec import HORIZON_DAYS, LOOKBACK_DAYS, sample_window


LAST_SCORED_ANCHOR = date(2025, 10, 9)
HOLDOUT_DAYS = 30


def plan_holdout(coverage_start, complete_through, publication_id):
    if coverage_start > complete_through or not publication_id.strip():
        raise ValueError("A valid contiguous coverage span and publication ID are required")
    last_seen = sample_window(LAST_SCORED_ANCHOR).label_end
    first = max(coverage_start + timedelta(days=LOOKBACK_DAYS - 1), last_seen + timedelta(days=LOOKBACK_DAYS))
    last = first + timedelta(days=HOLDOUT_DAYS - 1)
    needed = last + timedelta(days=HORIZON_DAYS)
    return {
        "status": "ready" if complete_through >= needed else "blocked",
        "publication_id": publication_id, "last_seen_event_date": last_seen.isoformat(),
        "first_anchor": first.isoformat(), "last_anchor": last.isoformat(),
        "coverage_start": coverage_start.isoformat(), "complete_through": complete_through.isoformat(),
        "required_complete_through": needed.isoformat(), "selection": "coverage-only-v1",
        "model_baseline": "persistence-30d",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-start", type=date.fromisoformat, required=True)
    parser.add_argument("--complete-through", type=date.fromisoformat, required=True)
    parser.add_argument("--publication-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = plan_holdout(args.coverage_start, args.complete_through, args.publication_id)
    payload = json.dumps(report, indent=2) + "\n"
    if report["status"] == "ready":
        commit_exclusive(args.output, payload)
    print(payload, end="")
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
