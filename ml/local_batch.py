"""Run the persistence baseline locally from verified GH Archive hours."""

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

import pyarrow.parquet as pq

from ml.publication_files import commit_exclusive
from ml.spec import LOOKBACK_DAYS, sample_window


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "ml/datasets/gharchive-2026-02-05"


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def run_batch(dataset):
    export = read(dataset / "export-manifest.json")
    source = dataset / "snapshot/repository_daily_metrics.parquet"
    if sha256(source.read_bytes()).hexdigest() != export["snapshot_files"][source.name]:
        raise ValueError("Daily metrics checksum differs from the dataset manifest")
    scope = {row["repository_id"]: row["repository_name"] for row in read(dataset / "scope.json")}
    if len(scope) != export["repos"]:
        raise ValueError("Repository scope differs from the export")
    anchor = date.fromisoformat(export["end"])
    window = sample_window(anchor)
    daily = pq.read_table(source, columns=["date", "repository_id", "star_events", "total_events"]).to_pylist()
    daily = {(row["date"], row["repository_id"]): row for row in daily}
    forecast = Counter()
    seen = set()
    for offset in range(LOOKBACK_DAYS):
        day = str(window.feature_start + timedelta(days=offset))
        folder = dataset / "days" / day
        manifest = read(folder / "day.json")
        files = manifest["files"]
        if (manifest["date"] != day or sorted(row["hour_utc"] for row in files) != list(range(24))
                or any(manifest[key] for key in ("conflicts", "invalid_events", "malformed_source_records"))):
            raise ValueError(f"Incomplete source hours or failed event checks for {day}")
        totals, stars = Counter(), Counter()
        for entry in files:
            file = folder / f"{entry['hour_utc']:02d}.parquet"
            if (entry["status"] != "processed" or not entry["source_md5_verified"]
                    or sha256(file.read_bytes()).hexdigest() != entry["parquet_sha256"]):
                raise ValueError(f"Unverified hour {day}/{entry['hour_utc']}")
            events = pq.read_table(file, columns=["event_id", "event_type", "created_at", "repo_id"]).to_pylist()
            if len(events) != entry["retained_records"]:
                raise ValueError(f"Unexpected row count in {file.name}")
            for event in events:
                rid = event["repo_id"]
                if rid not in scope or event["created_at"][:10] != day:
                    raise ValueError(f"Unexpected event scope for {day}")
                key = (event["event_id"], event["created_at"])
                if key in seen:
                    continue
                seen.add(key)
                totals[rid] += 1
                stars[rid] += int(event["event_type"] == "WatchEvent")
        if sum(totals.values()) != manifest["deduplicated_events"]:
            raise ValueError(f"Unexpected deduplicated event count for {day}")
        for rid in scope:
            row = daily[day, rid]
            for field, count in (("total_events", totals[rid]), ("star_events", stars[rid])):
                if row[field] != count and not (not totals[rid] and row[field] is None and count == 0):
                    raise ValueError(f"Source and daily {field} differ for {rid} on {day}")
        forecast.update(stars)
    return {"mode": "local_archive", "model": "persistence-30d", "input_publication": export["source_publication"],
            "anchor": anchor.isoformat(), "feature_start": window.feature_start.isoformat(),
            "forecast_start": window.label_start.isoformat(), "forecast_end": window.label_end.isoformat(),
            "hours_verified": LOOKBACK_DAYS * 24, "generated_at": datetime.now(timezone.utc).isoformat(),
            "rows": [{"repository_id": rid, "repository_name": scope[rid], "predicted_star_events": forecast[rid]}
                     for rid in sorted(scope)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_batch(DATASET)
    commit_exclusive(args.output, json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "repositories": len(result["rows"]), "anchor": result["anchor"]}))


if __name__ == "__main__":
    main()
