"""Check a ClickHouse publication against an independent GH Archive snapshot."""

import argparse
from datetime import date, timedelta
import json
from time import perf_counter

from apps.streamlit.data import get_adapter


METRICS = ("total_events", "star_events", "fork_events")


def check_publication(live, reference, reference_day, anchor):
    started = perf_counter()
    first = (anchor - timedelta(days=59)).isoformat()
    end = anchor.isoformat()
    day = reference_day.isoformat()
    statuses = live.day_status(first, end)
    growth = live.growth_ranking(end, 30)
    expected = reference.overview(day, day)
    observed = live.overview(day, day)
    matched, mismatches = [], []
    for repo_id in reference.repository_catalog().repository_id.tolist():
        reference_rows = reference.time_series(int(repo_id), day, day)
        try:
            gold = live.time_series(int(repo_id), day, day)
        except KeyError:
            gold = None
        if (
            len(reference_rows) == 1 and reference_rows.iloc[0].status == "complete"
            and gold is not None and len(gold) == 1 and gold.iloc[0].status == "complete"
            and all(reference_rows.iloc[0][metric] == gold.iloc[0][metric] for metric in METRICS)
        ):
            matched.append(int(repo_id))
        else:
            mismatches.append(int(repo_id))
    valid_growth = int(growth[["current", "previous"]].notna().all(axis=1).sum()) if len(growth) else 0
    checked_days = set(statuses.loc[statuses.status.eq("complete"), "date"])
    dates = {(anchor - timedelta(days=offset)).isoformat() for offset in range(60)}
    checks = {
        "metrics_match": bool(matched and not mismatches and expected["totals"] and observed["totals"]),
        "sixty_complete_days": dates <= checked_days,
        "growth_has_eligible_scope": valid_growth > 0,
    }
    return {
        "passed": all(checks.values()), "checks": checks,
        "publication_id": live.publication()["publication_id"], "reference_day": day, "growth_anchor": end,
        "matched_repo_ids": matched, "mismatched_repo_ids": mismatches,
        "missing_or_incomplete_days": sorted(dates - checked_days),
        "growth_eligible_repositories": valid_growth, "growth_total_repositories": len(growth),
        "validation_seconds": round(perf_counter() - started, 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="Independent APP-02 snapshot directory")
    parser.add_argument("--reference-day", required=True, type=date.fromisoformat)
    parser.add_argument("--anchor", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    start = perf_counter()
    try:
        live = get_adapter("clickhouse")
        query_seconds = round(perf_counter() - start, 3)
        report = check_publication(live, get_adapter("snapshot", args.reference), args.reference_day, args.anchor)
        report["publication_load_seconds"] = query_seconds
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report = {"passed": False, "error": str(exc)}
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
