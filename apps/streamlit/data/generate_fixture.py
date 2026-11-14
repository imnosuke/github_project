"""Generate deterministic synthetic data; never represents measured GitHub activity."""
import json
from pathlib import Path

import pandas as pd

from .adapter import COUNTS


def generate(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2026-08-01", "2026-11-03").strftime("%Y-%m-%d")
    registry, metadata, daily, statuses = [], [], [], []
    for day in dates:
        status = "missing" if day == "2026-08-15" else "provisional" if day == "2026-11-03" else "complete"
        statuses.append(dict(date=day, status=status, expected_files=24,
                             processed_files=0 if status == "missing" else 12 if status == "provisional" else 24,
                             quality_passed=status == "complete",
                             published_at=None if status == "missing" else f"{day}T23:59:59Z",
                             reason=None if status == "complete" else "Synthetic edge case"))
    for rid, name in enumerate(["rising", "falling", "quiet", "new-activity", "short-history", "no-metadata"], 1001):
        start = "2026-10-20" if name == "short-history" else "2026-08-01"
        registry.append(dict(repository_id=rid, repository_name=f"example/{name}", tracking_start_date=start,
                             tracking_end_date=None, category="data-engineering", ecosystem="analytics"))
        if name != "no-metadata":
            metadata.append(dict(repository_id=rid, snapshot_date="2026-11-01", observed_at="2026-11-01T23:00:00Z",
                                 repository_name=f"example/{name}", description="Synthetic demo repository",
                                 primary_language="Python", topics=["demo"], license="MIT", archived=False,
                                 is_fork=False, created_at="2025-01-01T00:00:00Z", current_stars=200, current_forks=30))
        for i, day in enumerate(dates):
            if day < start:
                continue
            stars = i // 10 if name == "rising" else max(0, 10-i//10) if name == "falling" else (3 if day >= "2026-10-20" else 0) if name == "new-activity" else 0 if name == "quiet" else 2
            values = {key: 0 for key in COUNTS}
            values.update(star_events=stars, total_events=stars, unique_actors=min(stars, 3),
                          unique_human_actors=min(stars, 2), active_contributors=None)
            if day == "2026-08-15":
                values = {key: None for key in COUNTS}
            daily.append(dict(repository_id=rid, date=day, **values))
    for name, records in [("repository_registry", registry), ("repository_metadata", metadata),
                          ("repository_daily_metrics", daily), ("daily_data_status", statuses)]:
        frame = pd.DataFrame(records)
        if name == "repository_daily_metrics":
            for col in COUNTS:
                frame[col] = frame[col].astype("Int64")
        frame.to_parquet(root / f"{name}.parquet", index=False)
    manifest = dict(contract_version="1.0.0-draft", data_source="fixture", publication_id="fixture-001",
                    published_at="2026-11-04T03:00:00Z", expected_complete_through="2026-11-02",
                    description="Synthetic deterministic demo, not ML evaluation data")
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    generate(Path(__file__).parent / "fixtures")
