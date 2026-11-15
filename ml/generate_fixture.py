"""Generate a separate long synthetic dataset; never overwrites app fixtures."""
from datetime import date, timedelta
from pathlib import Path
import argparse
import json

import pandas as pd

from apps.streamlit.data.adapter import COUNTS


def generate(output, num_repos: int = 6, num_days: int = 320):
    if num_repos < 6:
        raise ValueError("num_repos must be at least 6")
    if num_days < 320:
        raise ValueError("num_days must be at least 320")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    start = date(2025, 1, 1)
    days = [(start + timedelta(days=i)).isoformat() for i in range(num_days)]
    registry, daily, statuses = [], [], []
    for index, day in enumerate(days):
        status = "missing" if index == 45 else "provisional" if index == num_days - 1 else "complete"
        statuses.append({"date": day, "status": status, "expected_files": 24,
                         "processed_files": 0 if status == "missing" else 12 if status == "provisional" else 24,
                         "quality_passed": status == "complete",
                         "published_at": None if status == "missing" else f"{day}T23:59:59Z",
                         "reason": None if status == "complete" else "Synthetic edge case"})
    for index in range(num_repos):
        rid = 2101 + index
        scope_start = "2025-08-15" if index == 5 else days[0]
        registry.append({"repository_id": rid, "repository_name": f"synthetic/repo-{rid}",
                         "tracking_start_date": scope_start, "tracking_end_date": None,
                         "category": None, "ecosystem": None})
        for offset, day in enumerate(days):
            if day < scope_start:
                continue
            if index < 6:
                stars = [1 + offset // 14, max(0, 24 - offset // 16), 0,
                         0 if offset < 150 else 8, 2 + (offset % 7 == 0), 3][index]
            else:
                mode = index % 5
                base = (index % 11) + 1
                wave = (offset + index * 3) % 7
                if mode == 0:
                    stars = base + offset // 18 + int(wave in (0, 1))
                elif mode == 1:
                    stars = max(0, base + 15 - offset // 22) + int(wave == 0)
                elif mode == 2:
                    stars = 0 if (offset + index) % 4 else base
                elif mode == 3:
                    stars = base + (offset // 30) * 2 + (wave // 3)
                else:
                    stars = max(0, base + ((offset // 10 + index) % 5) - 2)
            values = dict.fromkeys(COUNTS, 0)
            if index != 2:
                fork_val = (offset + index) % 3 if index >= 6 else offset % 3
                push_val = 2 + (index % 4) if index >= 6 else 2
                pr_open_val = (offset + index) % 2 if index >= 6 else offset % 2
                issue_open_val = int((offset + index) % 5 == 0) if index >= 6 else int(offset % 5 == 0)
                values.update(star_events=stars, fork_events=fork_val,
                              push_events=push_val, prs_opened=pr_open_val,
                              issues_opened=issue_open_val)
                values["total_events"] = sum(values[c] for c in
                                              ("star_events", "fork_events", "push_events", "prs_opened", "issues_opened"))
                values.update(unique_actors=min(values["total_events"], 5 + (index % 4 if index >= 6 else 0)),
                              unique_human_actors=min(values["total_events"], 3 + (index % 3 if index >= 6 else 0)))
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
    end_ts = (date.fromisoformat(days[-1]) + timedelta(days=1)).isoformat() + "T03:00:00Z"
    manifest = {"contract_version": "1.0.0-draft", "data_source": "fixture",
                "publication_id": "ml-smoke-001", "published_at": end_ts,
                "expected_complete_through": days[-2],
                "description": "Long synthetic ML-02 smoke data; not model quality evidence"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repos", type=int, default=6, help="Number of repositories to generate (default: 6, e.g., 40 for personal PC training)")
    parser.add_argument("--days", type=int, default=320, help="Number of calendar days to generate (default: 320, e.g., 365)")
    args = parser.parse_args()
    generate(args.output, num_repos=args.repos, num_days=args.days)
    print(f"Created synthetic smoke fixture at {args.output} ({args.repos} repos, {args.days} days); not real ML evaluation data.")


if __name__ == "__main__":
    main()
