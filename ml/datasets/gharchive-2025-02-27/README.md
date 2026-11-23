# GH Archive backfill through 2025-02-27 UTC

Partial ML-03 backfill for the fixed 20-repository scope. Includes 58 complete days from 2025-01-01, 1,392 verified hourly files, and 290,767 deduplicated events. This is a retrospective snapshot. Historical availability and Gold reconciliation remain unverified.

- `scope.json` records the GitHub repository IDs.
- `days/` contains the hourly Parquet and matching checksum checkpoints, plus daily summaries. Use these files with the existing collector and the same scope to resume from verified hours.
- `snapshot/` contains the APP-02 daily tables and manifest for analysis and audit. It covers part of the planned 320-day window and falls short of the 239-day ML-03 minimum.

Hourly Parquet retains event and actor IDs, a bot marker and metric fields from the payload. The export excludes raw archives, runtime logs and temporary files.
