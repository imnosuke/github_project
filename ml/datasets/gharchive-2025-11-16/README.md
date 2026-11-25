# GH Archive backfill through 2025-11-16 UTC

Coverage runs from 2025-01-01 through 2025-11-16 UTC for 20 repositories. The export includes 7,676 verified hourly files and 1,266,626 deduplicated events over 320 days. Daily quality checks passed for 282 days. The other 38 days have their status and quality details in the daily manifests.

- `days/` contains hourly Parquet, checksum checkpoints and daily summaries.
- `scope.json` records the GitHub repository IDs.
- `snapshot/` contains daily APP-02 tables and the manifest for ML-03 audit and feature generation.
