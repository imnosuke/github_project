# GH Archive backfill through 2025-07-25 UTC

This ML-03 export covers 2025-01-01 through 2025-07-25 UTC for 20 repositories. It includes 4,926 verified hourly Parquet files and 933,378 deduplicated events across 206 calendar days. 204 days passed the daily quality check.

- 2025-06-12 UTC has 22/24 verified hours and status `provisional`.
- 2025-07-25 UTC has 8/24 verified hours and status `provisional`.

- `scope.json` records the repository IDs.
- `days/` holds the hourly Parquet/checkpoint pairs and daily summaries. Copy it and the scope into the collector data root to resume with the same configuration.
- `snapshot/` holds the daily APP-02 tables and manifest for audit and feature generation.
