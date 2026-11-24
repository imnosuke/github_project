# 🚀 GitHub Archive Data Lakehouse, Analytics & ML Forecasting (Medallion Architecture)

Hệ thống **Data Lakehouse, BI Analytics & Machine Learning End-to-End** thu thập trực tiếp dữ liệu sự kiện mã nguồn mở toàn cầu từ **[GH Archive](https://www.gharchive.org/)**, lưu trữ trên **MinIO S3**, xử lý qua kiến trúc **Medallion (Bronze $\rightarrow$ Silver $\rightarrow$ Gold)** trên **ClickHouse** bằng **dbt Incremental**, trực quan hóa qua **Apache Superset** và dự báo xu hướng tăng trưởng Star 30 ngày bằng **Streamlit (`RepoScope`) + Machine Learning**.

---

## 🏛️ 1. Kiến trúc hệ thống

```text
[GH Archive HTTPS] (https://data.gharchive.org/{YYYY-MM-DD}-{H}.json.gz)
        │
        ▼ (1) Apache Airflow (`gharchive_to_minio_hourly`) / Direct HTTPS -> S3 Stream
              • Giải nén Gzip on-the-fly và đóng gói Snappy Parquet ngay trên RAM (`io.BytesIO`)
              • Xóa object cũ (nếu chạy lại) và đẩy thẳng lên S3 MinIO (0 byte ghi xuống ổ cứng)
        │
[MinIO S3 Storage] (`s3://gharchive/bronze/events_parquet/year=YYYY/month=MM/day=DD/`)
        │
        ▼ (2) ClickHouse Native S3 Engine (`DELETE WHERE _source_file = ...` + `INSERT FROM s3()`)
┌────────────────────────────── ClickHouse OLAP ──────────────────────────────┐
│                                                                             │
│  🥉 Tầng BRONZE (`bronze.gharchive_events`)                                  │
│     Lưu dữ liệu sự kiện từ Parquet (~557 MB / ~785.000 dòng), Idempotent    │
│       │                                                                     │
│       ▼ (3) dbt Incremental (`delete+insert` theo `event_date`)             │
│  🥈 Tầng SILVER (`silver.stg_gharchive_events`)                              │
│     • Lần Init đầu tiên: Transform toàn bộ lịch sử từ Bronze                │
│     • Các lần chạy sau: Chỉ xóa & tính lại đúng ngày mới nạp (`event_date`) │
│     • Chuẩn hóa thời gian, tách chủ sở hữu repo, bóc tách JSON payload      │
│       │                                                                     │
│       ▼ (4) dbt Incremental (`delete+insert` theo `event_date`)             │
│  🥇 Tầng GOLD (`gold.*`)                                                     │
│     - `gold.gold_repo_daily_activity` (Repo × Ngày: Stars, Forks, PRs...)   │
│     - `gold.gold_actor_activity`      (Developer × Ngày: Commits, Bot...)   │
│     - `gold.gold_hourly_event_stats`  (Ngày × Giờ × Loại Event)             │
│                                                                             │
└─────────────────┬─────────────────────────────────────────┬─────────────────┘
                  │                                         │
                  ▼ (5A) Tự động tạo Dataset & 5 Charts     ▼ (5B) Ứng dụng & Dự báo ML
       [Apache Superset BI (:8088)]             [Streamlit `RepoScope` (:8501) & ML CLI]
  (Dashboard tổng quan Lakehouse Gold)          • Overview, Repo Explorer, Growth 7d/30d
                                                • ML Forecast: Dự báo Star 30 ngày tới
                                                  (28 features, Purge 30d, Ridge Regression)
```

### Công nghệ sử dụng (Tech Stack)
* **Orchestration:** Apache Airflow `2.9.3` (`LocalExecutor`)
* **Object Storage (S3 Compatible):** MinIO / Silo (`pgsty/silo`)
* **OLAP Data Warehouse / Lakehouse:** ClickHouse Server `24.3`
* **Data Transformation:** dbt (`dbt-core 1.8.8` & `dbt-clickhouse 1.8.4`, Incremental `delete+insert`)
* **BI Dashboard:** Apache Superset `3.1.3`
* **Analytics Web App & ML Serving:** Streamlit (`RepoScope`), Plotly, PyArrow, NumPy, Pandas
* **Containerization:** Docker & Docker Compose

---

## 📂 2. Cấu trúc thư mục dự án

```text
final_project/
├── airflow/
│   ├── dags/
│   │   └── gharchive_to_minio_dag.py     # DAG 4 bước: Resolve -> Stream HTTPS->S3 -> ClickHouse Bronze -> dbt Incremental
│   └── scripts/
│       ├── gharchive_extractor.py        # Stream trực tiếp HTTPS .json.gz -> RAM Parquet (io.BytesIO) -> S3 MinIO
│       └── clickhouse_loader.py          # Khởi tạo DB & nạp Idempotent từ MinIO S3 vào ClickHouse Bronze
├── dbt_gharchive/
│   ├── dbt_project.yml                   # Cấu hình project dbt
│   ├── profiles.yml                      # Kết nối ClickHouse + custom_settings tối ưu RAM
│   ├── macros/
│   │   └── generate_schema_name.sql      # Giữ nguyên tên database `silver` và `gold`
│   └── models/
│       ├── bronze/sources.yml            # Khai báo bảng nguồn `bronze.gharchive_events`
│       ├── silver/
│       │   ├── stg_gharchive_events.sql  # Incremental model: Làm sạch & bóc tách JSON payload theo `event_date`
│       │   └── schema.yml                # Data tests tầng Silver
│       └── gold/
│           ├── gold_repo_daily_activity.sql  # Incremental Data Mart: Hoạt động Repo theo ngày
│           ├── gold_actor_activity.sql       # Incremental Data Mart: Hoạt động Developer/Bot theo ngày
│           ├── gold_hourly_event_stats.sql   # Incremental Data Mart: Lưu lượng sự kiện theo giờ
│           └── schema.yml                    # Data tests tầng Gold
├── apps/streamlit/
│   ├── app.py                            # Giao diện chính RepoScope (4 trang: Overview, Explorer, Growth, ML Forecast)
│   ├── analytics.py                      # Logic hiển thị Overview & Growth Analytics (7d / 30d)
│   ├── explorer.py                       # Tìm kiếm, lọc, xem chi tiết & so sánh 2 Repositories
│   ├── ml_view.py                        # Trang trình diễn Model Card, Feature Importance & Dự báo Star 30 ngày tới
│   ├── data/                             # Data Adapter & ClickHouseConfig theo chuẩn Data Contract v1
│   └── tests/                            # Bộ 44 unit/UI tests cho Streamlit App
├── ml/
│   ├── spec.py                           # Đặc tả bài toán `ml-stars-30d-v1`, cửa sổ [T-29,T] -> [T+1,T+30] & Purge 30d
│   ├── features.py                       # Trích xuất 28 đặc trưng số (rolling 7d/30d sums, active days, daily actors)
│   ├── training.py                       # Huấn luyện & đánh giá Persistence-30d, Zero baseline và Ridge Regression
│   ├── readiness.py                      # Kiểm tra chất lượng dữ liệu ML-03 (tối thiểu 239 ngày, 60/30/30 anchors)
│   ├── cli.py                            # Giao diện dòng lệnh: `audit`, `build`, `train`, `evaluate`
│   ├── fetch_github_data.py              # Kết hợp dữ liệu ClickHouse Gold & GitHub API ra chuẩn Contract v1 (150 repos × 320 ngày)
│   └── tests/                            # Bộ 76 unit tests cho ML pipeline
├── superset/
│   ├── Dockerfile                        # Cài đặt Superset + driver clickhouse-connect
│   ├── superset_init.sh                  # Khởi tạo DB, Admin user cho Superset
│   └── bootstrap_clickhouse.py           # Tự động tạo Connection, 3 Datasets, 5 Charts & Dashboard
├── Dockerfile                            # Custom Airflow Image (tích hợp PyArrow, Boto3 & dbt venv)
├── docker-compose.yaml                   # Khai báo toàn bộ hạ tầng Docker Containers
├── requirements.txt                      # Thư viện Python cho Airflow
└── .env                                  # Biến môi trường cấu hình hệ thống
```

---

## ⚡ 3. Hướng dẫn khởi chạy toàn bộ hệ thống bằng Docker

### Yêu cầu hệ thống
* Đã cài đặt **Docker** và **Docker Compose** (khuyến nghị RAM trống tối thiểu $\ge$ 6GB).

### Bước 1: Khởi dựng và bật các Docker Containers
Mở terminal tại thư mục gốc `final_project` và chạy lệnh:

```bash
docker compose up -d --build
```

### Bước 2: Kiểm tra trạng thái các Container
```bash
docker compose ps
```
Đảm bảo các container đều ở trạng thái `Up (healthy)`:
* `gharchive-postgres` (Metadata DB cho Airflow)
* `gharchive-minio` (S3 Object Storage cổng `9000` / Web Console cổng `9001`)
* `gharchive-clickhouse` (ClickHouse OLAP Server cổng HTTP `8123` / Native `9002`)
* `gharchive-airflow-webserver` (Airflow UI cổng `8080`)
* `gharchive-airflow-scheduler` (Airflow Scheduler chạy DAG tự động)
* `gharchive-superset` (Apache Superset BI cổng `8088`)

---

## 🔑 4. Danh sách Giao diện (Web UI) & Tài khoản truy cập

| Dịch vụ | Địa chỉ (URL) | Tài khoản | Mật khẩu | Vai trò |
| :--- | :--- | :--- | :--- | :--- |
| **Apache Airflow** | [http://localhost:8080](http://localhost:8080) | `airflow` | `airflow` | Điều phối & giám sát DAG `gharchive_to_minio_hourly` |
| **MinIO Console** | [http://localhost:9001](http://localhost:9001) | `minioadmin` | `minioadmin` | Quản lý S3 Bucket `gharchive` (`bronze/events_parquet/`) |
| **ClickHouse Play UI** | [http://localhost:8123/play](http://localhost:8123/play) | `default` | `clickhouse` | Truy vấn trực tiếp SQL trên 3 tầng `bronze`, `silver`, `gold` |
| **Apache Superset BI** | [http://localhost:8088](http://localhost:8088) | `admin` | `admin` | Dashboard BI `GitHub Archive - Lakehouse Gold Analytics` |
| **Streamlit `RepoScope`** | [http://localhost:8501](http://localhost:8501) | *(Không cần)* | *(Không cần)* | Ứng dụng phân tích chuyên sâu & Dự báo ML 30d Stars |

---

## 🔄 5. Hướng dẫn vận hành Data Pipeline (Airflow + MinIO + ClickHouse + dbt)

### 5.1. Cơ chế Idempotent & Incremental Transformation
Pipeline **`gharchive_to_minio_hourly`** gồm 4 task nối tiếp nhau:
1. **`resolve_target_datetime`**: Xác định khung giờ `(date_str, hour)` hoặc danh sách nhiều khung giờ cần xử lý. Nếu chạy cho ngày hôm nay (theo giờ UTC), tự động giới hạn đến giờ UTC đã hoàn tất gần nhất để tránh lỗi HTTP 404 ở các giờ tương lai.
2. **`stream_gharchive_to_minio_s3`**: Mở kết nối HTTPS tới `https://data.gharchive.org/{YYYY-MM-DD}-{H}.json.gz`, giải nén Gzip và đóng gói Snappy Parquet **ngay trên RAM (`io.BytesIO`)**, xóa object cũ trên MinIO (nếu có) và đẩy thẳng lên `s3://gharchive/bronze/events_parquet/year=YYYY/month=MM/day=DD/` (**0 byte ghi xuống ổ cứng**).
3. **`load_to_clickhouse_bronze`**: Chạy `ALTER TABLE bronze.gharchive_events DELETE WHERE _source_file = ... SETTINGS mutations_sync = 1` rồi `INSERT INTO ... FROM s3(...)` để nạp lại an toàn mà không bao giờ trùng dữ liệu.
4. **`dbt_transform_silver_gold`**:
   - **Lần Init đầu tiên** (khi bảng chưa tồn tại hoặc bật `"dbt_full_refresh": true`): Transform toàn bộ lịch sử từ Bronze sang Silver và 3 bảng Gold.
   - **Các lần chạy hàng ngày / hàng giờ tiếp theo**: Chạy ở chế độ **Incremental (`delete+insert` theo `event_date`)** với biến `--vars '{"target_dates": "YYYY-MM-DD"}'`, chỉ xóa và tính lại đúng ngày vừa nạp (hoàn tất trong ~2–5 giây), sau đó chạy 9 bài kiểm tra chất lượng `dbt test`.

### 5.2. Chạy (Trigger) DAG cho một ngày hoặc khoảng ngày trên Airflow
1. Mở [http://localhost:8080](http://localhost:8080), chọn DAG **`gharchive_to_minio_hourly`** $\rightarrow$ bấm nút **Play (Trigger DAG w/ config)**.
2. **Ví dụ 1 — Chạy lại toàn bộ các giờ đã hoàn tất của một ngày (ví dụ `2026-11-24`):**
   ```json
   {
     "custom_date": "2026-11-24",
     "custom_hour": null,
     "filter_default_repos": true,
     "dbt_full_refresh": false
   }
   ```
3. **Ví dụ 2 — Tải hàng loạt ~500 MB dữ liệu Parquet lên MinIO S3 bằng CLI trong Docker:**
   ```bash
   docker exec -it gharchive-airflow-webserver python /opt/airflow/scripts/gharchive_extractor.py \
     --date 2025-01-01 \
     --end-date 2025-01-25 \
     --hours-step 6 \
     --max-records 24000 \
     --target-total-mb 500 \
     --skip-existing
   ```

### 5.3. Kiểm tra dữ liệu trên ClickHouse (`http://localhost:8123/play`)
```sql
-- 1. Kiểm tra tổng số dòng và khoảng thời gian ở cả 3 tầng
SELECT 'bronze' AS layer, count() AS rows FROM bronze.gharchive_events
UNION ALL
SELECT 'silver' AS layer, count() AS rows FROM silver.stg_gharchive_events
UNION ALL
SELECT 'gold_repo_daily' AS layer, count() AS rows FROM gold.gold_repo_daily_activity;

-- 2. Kiểm tra dữ liệu ngày 2026-11-24 đã được nạp và transform sang Silver & Gold
SELECT event_date, count() AS total_rows, sum(total_events) AS events_sum
FROM gold.gold_repo_daily_activity
WHERE event_date = '2026-11-24'
GROUP BY event_date;
```

---

## 📊 6. Hướng dẫn chạy Ứng dụng Streamlit (`RepoScope`) & Huấn luyện Model ML

Ứng dụng **RepoScope** ([apps/streamlit/app.py](file:///c:/Users/PC/Desktop/Nosuke/final_project/apps/streamlit/app.py)) tích hợp cả phân tích dữ liệu (Overview, Repository Explorer, Growth Analytics 7d/30d) lẫn **Dự báo Machine Learning (`ML Forecast (30d Stars)`)**.

### 6.1. Tạo Dataset Contract v1 & Huấn luyện Mô hình ML (150 Repos × 320 Ngày)
Từ thư mục `final_project`, chạy các lệnh sau để trích xuất dữ liệu từ ClickHouse Gold + GitHub profiles, kiểm tra `audit`, tạo 28 đặc trưng (`build`), huấn luyện mô hình Ridge Regression (`train`) và đánh giá (`evaluate`):

```powershell
# 1. Tổng hợp bộ dữ liệu 150 repositories x 320 ngày (46.425 dòng daily metrics)
python -m ml.fetch_github_data --output ml/runs/github_pc_fixture --repos 150 --days 320 --no-github-api

# 2. Kiểm tra độ sẵn sàng dữ liệu (ML-03 Readiness Audit: tối thiểu 239 ngày & 60/30/30 anchors)
python -m ml.cli audit --config ml/configs/smoke.json --fixture-dir ml/runs/github_pc_fixture --output ml/runs/github_pc_audit

# 3. Xây dựng 26.445 mẫu học có giám sát (28 features quá khứ [T-29,T] + nhãn Star [T+1,T+30], Purge 30 ngày)
python -m ml.cli build --config ml/configs/smoke.json --fixture-dir ml/runs/github_pc_fixture --output ml/runs/github_pc_dataset

# 4. Huấn luyện & chọn mô hình tốt nhất (Persistence-30d vs. Zero vs. Ridge Regression)
python -m ml.cli train --config ml/configs/smoke.json --dataset ml/runs/github_pc_dataset --output ml/runs/github_pc_model

# 5. Đánh giá độc lập trên tập Test
python -m ml.cli evaluate --dataset ml/runs/github_pc_dataset --run ml/runs/github_pc_model --output ml/runs/github_pc_eval
```

### 6.2. Khởi chạy Giao diện Streamlit (`http://localhost:8501`)
```powershell
cd C:\Users\PC\Desktop\Nosuke\final_project
$env:APP_DATA_SOURCE="fixture"
$env:APP_FIXTURE_DIR="C:\Users\PC\Desktop\Nosuke\final_project\ml\runs\github_pc_fixture"
python -m streamlit run apps/streamlit/app.py
```
Truy cập **[http://localhost:8501](http://localhost:8501)** và chuyển qua 4 trang trên thanh điều hướng bên trái:
1. **Overview**: Kiểm tra trạng thái dữ liệu `complete` (24/24h), KPI tổng quan và biểu đồ xu hướng theo ngày.
2. **Repository Explorer**: Tìm kiếm trong 150 repositories, lọc theo ngôn ngữ/danh mục, xem chi tiết 13 chỉ số và so sánh trực tiếp 2 repositories.
3. **Growth Analytics**: Bảng xếp hạng tăng trưởng Star trong cửa sổ 7 ngày và 30 ngày (`current` vs `previous`).
4. **ML Forecast (30d Stars)**:
   - Xem **Model Card** (kết quả huấn luyện trên 26.445 mẫu, bảng so sánh MAE/RMSE giữa `Ridge`, `Persistence-30d` và `Zero`, biểu đồ Top 15 Feature Importance).
   - Xem **Dự báo trực tiếp (Live Batch Inference)**: Xếp hạng Top Repositories được dự báo bùng nổ Star mạnh nhất trong 30 ngày kế tiếp từ ngày neo $T$ bạn chọn.
   - Xem **Biểu đồ Kiểm chứng (Holdout Evaluation)**: So sánh đường Thực tế (`target`) vs. Dự đoán (`ridge`) trên tập Test cho từng repository.

---

## 🛠️ 7. Các lệnh kiểm thử & vận hành hữu ích

* **Chạy toàn bộ bộ kiểm thử tự động (120 unit & UI tests cho ML và Streamlit):**
  ```powershell
  python -m pytest ml/tests apps/streamlit/tests -q
  ```
* **Chạy dbt incremental trực tiếp trong container Airflow cho ngày `2026-11-24`:**
  ```bash
  docker exec -it gharchive-airflow-webserver /opt/airflow/dbt_venv/bin/dbt run \
    --project-dir /opt/airflow/dbt_gharchive \
    --profiles-dir /opt/airflow/dbt_gharchive \
    --vars '{"target_dates": "2026-11-24"}'
  ```
* **Khởi tạo lại Dashboard mẫu trên Apache Superset:**
  ```bash
  docker exec -it gharchive-superset python /app/bootstrap_clickhouse.py
  ```
* **Dừng toàn bộ hệ thống Docker:**
  ```bash
  docker compose down
  ```
