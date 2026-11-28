# GH Archive Unified Snapshot (2025-01-01 → 2026-07-21 UTC)

Bộ dữ liệu hợp nhất theo hợp đồng APP-02 cho cùng phạm vi **20 repository** trong [scope.json](scope.json), nối liền 3 chặng dữ liệu thật từ GH Archive:

| Chặng | Khoảng ngày (UTC) | Nguồn |
| --- | --- | --- |
| Lịch sử 2025 | `2025-01-01` → `2025-11-16` | [gharchive-2025-11-16](../gharchive-2025-11-16/snapshot/manifest.json) |
| Holdout ML-03 | `2025-11-17` → `2026-02-05` | [gharchive-2026-02-05](../gharchive-2026-02-05/snapshot/manifest.json) |
| Backfill Medallion (Airflow + ClickHouse Gold) | `2026-02-06` → `2026-07-21` | Pipeline `gharchive_to_minio_hourly` → Bronze/Silver/Gold + `app_serving.gold_hour_receipts` |

## Độ phủ và chất lượng

- **Tổng khung ngày:** `567` ngày (`2025-01-01` → `2026-07-21` UTC), `11.340` dòng repo-ngày.
- **Ngày đủ 24/24 tệp giờ:** `563` ngày.
- **Trạng thái APP-02:** `297` ngày `complete`, `269` ngày `provisional` (đủ 24/24 giờ nhưng thiếu cờ `merged` trên một số `PullRequestEvent` đóng từ nguồn GH Archive), `1` ngày `missing` (`2026-04-21` UTC do timeout khi crawl).
- **Tổng hoạt động ghi nhận:** `1.786.073` sự kiện và `103.964` lượt star.
- **Bằng chứng pipeline:** [app10-airflow-runs.json](de-evidence/app10-airflow-runs.json) (`173` lượt chạy Airflow xuất từ metadata thực tế).

## Cách nối vào pipeline và ứng dụng

- **RepoScope (`/reposcope`):** Đọc trực tiếp `snapshot/` qua `APP_SNAPSHOT_DIR` và `de-evidence/app10-airflow-runs.json` qua `APP_PIPELINE_RUNS_FILE` trong `docker-compose.demo.yaml`.
- **ClickHouse & Superset (`/superset`):** `demo-first-run` gọi `airflow/scripts/seed_snapshot_to_clickhouse.py` để nạp idempotent toàn bộ ngày có dữ liệu vào `gold.gold_repo_daily_activity` và công bố cửa sổ 366 ngày gần nhất vào `app_serving.*` theo hợp đồng APP-02.
- **Demo ML (`/ml`):** Dùng `snapshot/` cho tab dự báo Persistence 30 ngày mới nhất (`2026-07-22` → `2026-08-20` UTC) và đối chiếu thực tế kỳ `2026-02-06` → `2026-03-07` UTC, đồng thời giữ nguyên bộ holdout ML-03 đã khóa ở `gharchive-2026-02-05`.
