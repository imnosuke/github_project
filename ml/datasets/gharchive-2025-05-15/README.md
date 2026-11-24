# GH Archive backfill through 2025-05-15 UTC

The ML-03 export covers 135 complete days from 2025-01-01, 20 repositories, 3,240 verified hourly files and 668,067 deduplicated events.

- `scope.json` records repository IDs.
- `days/` holds the Parquet/checkpoint pairs and day summaries. Copy it and the scope into the collector data root to resume with the same configuration.
- `snapshot/` holds the daily APP-02 tables and the manifest for ML-03 audit and feature generation.

ML-03 requires at least 239 calendar days and eligible train, validation and test anchors. This retrospective snapshot still awaits Gold reconciliation and historical availability evidence.
