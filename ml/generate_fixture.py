"""Generate a separate long synthetic dataset; never overwrites app fixtures."""
from datetime import date, timedelta
from pathlib import Path
import argparse
import json

import pandas as pd

from apps.streamlit.data.adapter import COUNTS


def generate(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    start = date(2025, 1, 1)
    days = [(start + timedelta(days=i)).isoformat() for i in range(320)]
    registry, daily, statuses = [], [], []
    for index, day in enumerate(days):
        status = "missing" if index == 45 else "provisional" if index == 319 else "complete"
        statuses.append({"date": day, "status": status, "expected_files": 24,
                         "processed_files": 0 if status == "missing" else 12 if status == "provisional" else 24,
                         "quality_passed": status == "complete",
                         "published_at": None if status == "missing" else f"{day}T23:59:59Z",
                         "reason": None if status == "complete" else "Synthetic edge case"})
    for index in range(6):
        rid = 2101 + index
        scope_start = "2025-08-15" if index == 5 else days[0]
        registry.append({"repository_id": rid, "repository_name": f"synthetic/repo-{rid}",
                         "tracking_start_date": scope_start, "tracking_end_date": None,
                         "category": None, "ecosystem": None})
        for offset, day in enumerate(days):
            if day < scope_start:
                continue
            stars = [1 + offset // 14, max(0, 24 - offset // 16), 0,
                     0 if offset < 150 else 8, 2 + (offset % 7 == 0), 3][index]
            values = dict.fromkeys(COUNTS, 0)
            if index != 2:
                values.update(star_events=stars, fork_events=offset % 3,
                              push_events=2, prs_opened=offset % 2,
                              issues_opened=int(offset % 5 == 0))
                values["total_events"] = sum(values[c] for c in
                                              ("star_events", "fork_events", "push_events", "prs_opened", "issues_opened"))
                values.update(unique_actors=min(values["total_events"], 5),
                              unique_human_actors=min(values["total_events"], 3))
            values["active_contributors"] = None
            if offset == 45:
                values = dict.fromkeys(COUNTS)
            daily.append({"repository_id": rid, "date": day, **values})
    daily_frame = pd.DataFrame(daily)
    daily_frame[COUNTS] = daily_frame[COUNTS].astype("Int64")
    metadata = pd.DataFrame(columns=[
        "repository_id", "snapshot_date", "observed_at", "repository_name",
        "description", "primary_language", "topics", "license", "archived",
        "is_fork", "created_at", "current_stars", "current_forks",
    ])
    for name, frame in [("repository_registry", pd.DataFrame(registry)),
                        ("repository_daily_metrics", daily_frame),
                        ("daily_data_status", pd.DataFrame(statuses)),
                        ("repository_metadata", metadata)]:
        frame.to_parquet(output / f"{name}.parquet", index=False)
    manifest = {"contract_version": "1.0.0-draft", "data_source": "fixture",
                "publication_id": "ml-smoke-001", "published_at": "2025-11-17T03:00:00Z",
                "expected_complete_through": days[-2],
                "description": "Long synthetic ML-02 smoke data; not model quality evidence"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    generate(args.output)
    print(f"Created synthetic smoke fixture at {args.output}; not real ML evaluation data.")


if __name__ == "__main__":
    main()
