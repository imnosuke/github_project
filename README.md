# 🚀 GitHub Archive Data Lakehouse (Medallion Architecture)

Hệ thống Data Pipeline & Lakehouse End-to-End thu thập, lưu trữ, biến đổi và trực quan hóa dữ liệu sự kiện mã nguồn mở toàn cầu từ **[GH Archive](https://www.gharchive.org/)** theo kiến trúc **Medallion (Bronze $\rightarrow$ Silver $\rightarrow$ Gold)**.

---

## 🏛️ 1. Kiến trúc hệ thống

```text
[GH Archive API] (Dữ liệu sự kiện GitHub toàn cầu theo từng giờ - .json.gz)
       │
       ▼ (1) Apache Airflow (Extract & Convert sang chuẩn Parquet nén Snappy)
[MinIO S3 Storage] (Lưu trữ Data Lake phân vùng theo year/month/day)
       │
       ▼ (2) ClickHouse Native S3 Engine (Đọc trực tiếp Parquet từ MinIO)
┌─────────────────────────── ClickHouse OLAP ───────────────────────────┐
│                                                                       │
│  🥉 Tầng BRONZE (`bronze.gharchive_events`)                            │
│     Lưu dữ liệu thô nguyên bản từ Parquet, hỗ trợ Idempotent Load     │
│       │                                                               │
│       ▼ (3) dbt (`dbt-clickhouse`) - Làm sạch, khử trùng, bóc tách JSON│
│  🥈 Tầng SILVER (`silver.stg_gharchive_events`)                        │
│     Chuẩn hóa kiểu thời gian, tách chủ sở hữu repo, trích xuất         │
│     commits, PRs, issues, nhận diện tài khoản [bot]                   │
│       │                                                               │
│       ▼ (4) dbt (`dbt-clickhouse`) - Tổng hợp Data Marts              │
│  🥇 Tầng GOLD (`gold.*`)                                               │
│     - `gold.gold_repo_daily_activity` (Top Repos, Stars, Forks, PRs)  │
│     - `gold.gold_actor_activity`      (Top Developers, Commits)       │
│     - `gold.gold_hourly_event_stats`  (Lưu lượng theo giờ & Event)    │
│                                                                       │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼ (5) Tự động khởi tạo Dataset & Dashboard
                         [Apache Superset BI]
            (Dashboard trực quan hóa chỉ số mã nguồn mở)
```

### Công nghệ sử dụng (Tech Stack)
* **Orchestration:** Apache Airflow `2.9.3` (LocalExecutor)
* **Object Storage (S3 Compatible):** MinIO / Silo (`pgsty/silo`)
* **OLAP Data Warehouse / Lakehouse:** ClickHouse Server `24.3`
* **Data Transformation:** dbt (`dbt-core 1.8.8` & `dbt-clickhouse 1.8.4`)
* **BI & Visualization:** Apache Superset `3.1.3`
* **Containerization:** Docker & Docker Compose

---

## 📂 2. Cấu trúc thư mục dự án

```text
final_project/
├── airflow/
│   ├── dags/
│   │   └── gharchive_to_minio_dag.py     # DAG điều phối toàn bộ luồng E2E
│   └── scripts/
│       ├── gharchive_extractor.py        # Tải .json.gz, chuyển đổi Parquet & đẩy lên MinIO
│       └── clickhouse_loader.py          # Khởi tạo DB & nạp Parquet từ MinIO vào ClickHouse Bronze
├── dbt_gharchive/
│   ├── dbt_project.yml                   # Cấu hình project dbt
│   ├── profiles.yml                      # Cấu hình kết nối dbt -> ClickHouse
│   ├── macros/
│   │   └── generate_schema_name.sql      # Macro giữ nguyên tên database `silver` và `gold`
│   └── models/
│       ├── bronze/
│       │   └── sources.yml               # Khai báo bảng nguồn `bronze.gharchive_events`
│       ├── silver/
│       │   ├── stg_gharchive_events.sql  # Làm sạch, khử trùng lặp & giải nén JSON payload
│       │   └── schema.yml                # Data tests & tài liệu tầng Silver
│       └── gold/
│           ├── gold_repo_daily_activity.sql  # Data Mart: Thống kê hoạt động Repo theo ngày
│           ├── gold_actor_activity.sql       # Data Mart: Thống kê đóng góp của Developer
│           ├── gold_hourly_event_stats.sql   # Data Mart: Thống kê lưu lượng sự kiện theo giờ
│           └── schema.yml                    # Data tests & tài liệu tầng Gold
├── superset/
│   ├── Dockerfile                        # Cài đặt Superset + driver clickhouse-connect
│   ├── superset_init.sh                  # Script khởi tạo DB, Admin user cho Superset
│   └── bootstrap_clickhouse.py           # Tự động tạo Connection, Datasets, 5 Charts & Dashboard
├── Dockerfile                            # Custom Airflow Image (tích hợp PyArrow, Boto3 & dbt venv)
├── docker-compose.yaml                   # Khai báo toàn bộ hạ tầng контейners
├── requirements.txt                      # Thư viện Python cho Airflow
└── .env                                  # Biến môi trường cấu hình hệ thống
```

---

## ⚡ 3. Hướng dẫn cài đặt và chạy dự án

### Demo local trên một cổng

Từ thư mục gốc repo, dùng Docker với Compose v2 hỗ trợ thẻ `!reset`.

```powershell
docker compose -f docker-compose.yaml -f docker-compose.demo.yaml up -d --build
```

Mở **http://127.0.0.1:8089/** sau khi các dịch vụ khởi động. Hai lệnh chạy Streamlit riêng được thay bằng các service trong Compose.

| Đường dẫn | Giao diện |
| --- | --- |
| `/reposcope` | Overview, Repository Explorer và Growth Analytics |
| `/ml` | Đánh giá hồi cứu và batch dự báo 20 repo |
| `/airflow` | Lịch sử và thao tác DAG GH Archive |
| `/superset` | Dashboard Gold Analytics |
| `/pipeline` | Pipeline Health từ bản xuất Airflow đã lưu |

RepoScope đọc [snapshot GitHub thật đã nghiệm thu](ml/datasets/gharchive-2025-11-16/snapshot/manifest.json) lấy từ commit `1e205c6c`. ML kiểm chứng 720 tệp giờ của snapshot holdout và tạo kết quả batch khi container khởi động lần đầu. Airflow xếp một lượt fetch mẫu cho 14:00 UTC ngày 15/01/2025 khi chưa có run đó trong metadata. Lượt này xử lý dữ liệu mới tải cho Superset và pipeline, còn các dashboard snapshot có dữ liệu ngay khi Streamlit sẵn sàng.

Cổng mặc định chỉ bind loopback. Có thể đặt `REPOSCOPE_DEMO_PORT` nếu 8089 đang bận. Airflow và Superset dùng thông tin đăng nhập của stack local.

Khi cần xem trạng thái hoặc dừng demo, dùng cùng hai file Compose.

```powershell
docker compose -f docker-compose.yaml -f docker-compose.demo.yaml ps
docker compose -f docker-compose.yaml -f docker-compose.demo.yaml down
```

### Yêu cầu hệ thống
* Đã cài đặt **Docker** và **Docker Compose** (khuyến nghị RAM trống tối thiểu $\ge$ 6GB).

### Bước 1: Khởi chạy toàn bộ hệ thống
Mở terminal tại thư mục gốc của dự án và chạy lệnh:

```bash
docker compose up -d --build
```

> **Lưu ý:** Lần chạy đầu tiên sẽ mất khoảng 2–4 phút để Docker tải các image, cài đặt môi trường ảo `dbt_venv` cho Airflow và khởi tạo metadata cho Airflow & Superset.

### Bước 2: Kiểm tra trạng thái các Container
```bash
docker compose ps
```
Đảm bảo các container sau đều ở trạng thái `Up (healthy)`:
* `gharchive-postgres`
* `gharchive-minio`
* `gharchive-clickhouse`
* `gharchive-airflow-webserver`
* `gharchive-airflow-scheduler`
* `gharchive-superset`

---

## 🔑 4. Thông tin truy cập các Giao diện (Web UI)

| Dịch vụ | Địa chỉ (URL) | Tài khoản (Username) | Mật khẩu (Password) | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| **Apache Airflow** | [http://localhost:8080](http://localhost:8080) | `airflow` | `airflow` | Quản lý & chạy DAG pipeline |
| **MinIO Console** | [http://localhost:9001](http://localhost:9001) | `minioadmin` | `minioadmin` | Quản lý S3 Bucket `gharchive` (API cổng `9000`) |
| **ClickHouse Web UI** | [http://localhost:8123/play](http://localhost:8123/play) | `default` | `clickhouse` | Truy vấn trực tiếp SQL (Native TCP cổng `9002`) |
| **Apache Superset** | [http://localhost:8088](http://localhost:8088) | `admin` | `admin` | Xem Dashboard & xây dựng biểu đồ BI |

---

## 🔄 5. Hướng dẫn vận hành Pipeline

### 5.1. Kích hoạt Pipeline trên Airflow
1. Truy cập [http://localhost:8080](http://localhost:8080) và đăng nhập với `airflow` / `airflow`.
2. Tìm DAG **`gharchive_to_minio_hourly`**.
3. DAG được cấu hình chạy tự động mỗi giờ (`@hourly`). Bạn cũng có thể chạy thủ công cho một ngày/giờ bất kỳ bằng cách:
   * Bấm nút **Play (Trigger DAG w/ config)** ở góc phải.
   * Nhập tham số tùy chọn (hoặc để trống để lấy giờ gần nhất):
     ```json
     {
       "custom_date": "2025-01-15",
       "custom_hour": 14,
       "upload_raw_gz": false
     }
     ```
4. Luồng xử lý tự động đi qua 7 bước:
   `resolve_target_datetime` → `stream_gharchive_to_minio_s3` → `load_to_clickhouse_bronze` → `dbt_transform_silver_gold`.

### 5.2. Kiểm tra dữ liệu trên ClickHouse
Truy cập [http://localhost:8123/play](http://localhost:8123/play) (User: `default`, Password: `clickhouse`) và chạy thử các câu truy vấn:

```sql
-- 1. Kiểm tra số lượng bản ghi ở tầng Bronze
SELECT count(), min(created_at), max(created_at) FROM bronze.gharchive_events;

-- 2. Xem dữ liệu đã làm sạch & bóc tách JSON ở tầng Silver
SELECT event_id, event_type, event_timestamp, actor_login, is_bot, repo_full_name, action, push_commit_count
FROM silver.stg_gharchive_events
LIMIT 20;

-- 3. Xem Top 10 Repositories nhận được nhiều Stars nhất ở tầng Gold
SELECT event_date, repo_full_name, stars_gained, forks_count, total_commits_pushed, prs_opened, total_events
FROM gold.gold_repo_daily_activity
ORDER BY stars_gained DESC
LIMIT 10;
```

### 5.3. Xem Dashboard trên Apache Superset
1. Truy cập thẳng vào Dashboard được tạo tự động tại:
   👉 **[http://localhost:8088/superset/dashboard/gharchive-gold-analytics/](http://localhost:8088/superset/dashboard/gharchive-gold-analytics/)**
2. Dashboard **`GitHub Archive - Lakehouse Gold Analytics`** bao gồm 5 biểu đồ kết nối trực tiếp tới tầng Gold của ClickHouse:
   * **Tổng số Sự kiện GitHub (Total Events)** *(Big Number KPI)*
   * **Phân bố các loại Sự kiện (Event Types)** *(Donut Chart)*
   * **Tỷ lệ sự kiện: Lập trình viên vs Bot** *(Donut Chart)*
   * **Top 20 Repositories sôi động nhất (Stars, Commits, PRs)** *(Interactive Table)*
   * **Top 20 Lập trình viên hoạt động tích cực nhất** *(Interactive Table)*

---

## 🛠️ 6. Các lệnh hữu ích khi vận hành / xử lý sự cố

* **Chạy riêng bước dbt (run & test) từ Terminal:**
  ```bash
  docker exec -it gharchive-airflow-webserver /opt/airflow/dbt_venv/bin/dbt run --project-dir /opt/airflow/dbt_gharchive --profiles-dir /opt/airflow/dbt_gharchive
  ```

* **Đồng bộ lại kết nối ClickHouse và tạo lại Dashboard mẫu trên Superset:**
  ```bash
  docker exec -it gharchive-superset python /app/bootstrap_clickhouse.py
  ```

* **Reset mật khẩu tài khoản Admin của Airflow (nếu quên hoặc lỗi đăng nhập):**
  ```bash
  docker exec -it gharchive-airflow-webserver airflow users create --username airflow --password airflow --firstname Air --lastname Flow --role Admin --email admin@example.com
  ```

* **Dừng toàn bộ hệ thống:**
  ```bash
  docker compose down
  ```
  *(Thêm cờ `-v` nếu muốn xóa toàn bộ dữ liệu trong các Docker volumes: `docker compose down -v`).*

---

## 🤖 7. Hướng dẫn Tải dữ liệu (~20 MB) & Huấn luyện Model ML trên Máy Cá Nhân

Để phục vụ bài toán dự báo số lượng `star_events` trong 30 ngày tiếp theo (**ML-01 / ML-02 / ML-03**) trên máy cá nhân mà không cần tải hàng trăm GB raw GH Archive, dự án cung cấp chế độ trích xuất giới hạn dung lượng (~20 MB ổ cứng) kết hợp bộ tạo dữ liệu chuẩn **Contract v1**.

### 7.1. Lấy mẫu trên MinIO hoặc dùng snapshot local

Dùng CLI bên dưới cho dữ liệu thăm dò. File ghi dưới `samples/gharchive/` trong MinIO, ngoài đường nạp Bronze. Bộ train demo ở bước sau có thể đọc thư mục Parquet local nếu bạn đã tải mẫu từ MinIO. Dữ liệu demo kết hợp Parquet lấy mẫu với fixture.

```bash
python airflow/scripts/gharchive_extractor.py --date 2025-01-15 --hour 14 --max-records 22000
```

Để chạy trên lịch sử đã crawl, dùng [kết quả và snapshot ML-03](docs/app-ml/ML-03-retrospective-results.md).

#### Dữ liệu backfill ML-03 cho DE

Bản xuất holdout mới có **89 ngày, 2.136 giờ** cho 20 repo từ **09/11/2025 đến 05/02/2026 UTC**. Snapshot, checkpoint theo giờ, kết quả ML-03 và bằng chứng nghiệm thu pipeline nằm trong [bộ dữ liệu holdout](ml/datasets/gharchive-2026-02-05/README.md).

Bản xuất lịch sử từ **01/01 đến 16/11/2025 UTC** nằm trên nhánh dữ liệu. Trong 320 ngày lịch, 282 ngày đạt kiểm tra chất lượng. [Chỉ mục dữ liệu lịch sử](https://github.com/imnosuke/github_project/blob/feature/ml-gharchive-backfill-checkpoints/ml/datasets/README.md)

- Dùng `snapshot/manifest.json` và các bảng Parquet trong `snapshot/` để kiểm tra nguồn, checksum, metrics và trạng thái từng ngày trước khi audit ML-03.
- Dùng `days/` và `scope.json` để tiếp tục backfill bằng collector tương thích với checkpoint. Giữ các cặp Parquet/checksum theo giờ và GitHub repo ID.

Mở nhánh dữ liệu trong thư mục riêng:

```bash
git fetch origin feature/ml-gharchive-backfill-checkpoints
git worktree add --detach ../github-project-data origin/feature/ml-gharchive-backfill-checkpoints
```

### 7.2. Tổng hợp Dataset theo chuẩn Contract v1 (150 Repos × 320 Ngày)
Gộp dữ liệu Parquet GH Archive vừa tải với danh mục 150 repositories trong 320 ngày (vượt ngưỡng tối thiểu 239 ngày của `ML-01` / `ML-03`):

```bash
python -m ml.fetch_github_data \
  --output ml/runs/github_pc_fixture \
  --repos 150 \
  --days 320 \
  --local-parquet-dir ./airflow/data/parquet
```
*(Thêm cờ `--no-github-api` nếu muốn chạy hoàn toàn offline không gọi GitHub REST API).*
* **Kết quả:** Tạo `ml/runs/github_pc_fixture` gồm **46.425 dòng daily metrics** hoàn chỉnh theo đúng schema `APP-02 Data Contract v1`.

### 7.3. Kiểm tra Readiness Audit, Tạo Features (28 đặc trưng) & Train Model
Chạy tuần tự các lệnh CLI của module `ml`:

```bash
# 1. Kiểm tra chất lượng & độ phủ dữ liệu (ML-03 Readiness Audit)
python -m ml.cli audit \
  --config ml/configs/smoke.json \
  --fixture-dir ml/runs/github_pc_fixture \
  --output ml/runs/github_pc_audit

# 2. Xây dựng tập mẫu học có giám sát (26.445 mẫu hợp lệ sau khi lọc & purge 30 ngày)
python -m ml.cli build \
  --config ml/configs/smoke.json \
  --fixture-dir ml/runs/github_pc_fixture \
  --output ml/runs/github_pc_dataset

# 3. Huấn luyện & lựa chọn mô hình (Persistence-30d, Zero baseline, Ridge Regression)
python -m ml.cli train \
  --config ml/configs/smoke.json \
  --dataset ml/runs/github_pc_dataset \
  --output ml/runs/github_pc_model

# 4. Đánh giá độc lập lại mô hình đã lưu trên tập Test
python -m ml.cli evaluate \
  --dataset ml/runs/github_pc_dataset \
  --run ml/runs/github_pc_model \
  --output ml/runs/github_pc_eval
```

### 7.4. Bảng thống kê dung lượng & quy mô bộ dữ liệu (~20 MB)

| Thành phần | Đường dẫn | Quy mô dữ liệu | Dung lượng ổ cứng |
| :--- | :--- | :--- | :--- |
| **GH Archive Parquet** | `airflow/data/parquet/2025-01-15-14.parquet` | 22.000 sự kiện GitHub thực tế | **~18.39 MB** |
| **Contract v1 Fixture** | `ml/runs/github_pc_fixture/` | 150 repos × 320 ngày = 46.425 dòng | **~0.24 MB** |
| **ML Feature Dataset** | `ml/runs/github_pc_dataset/` | 26.445 mẫu × 28 features (`train`: 17.446, `val`: 4.576, `test`: 4.423) | **~0.45 MB** |
| **Model & Audit Reports** | `ml/runs/github_pc_model/`, `github_pc_audit/`, `github_pc_eval/` | Trọng số Ridge, dự đoán tập test & báo cáo audit | **~0.19 MB** |
| **Tổng cộng** | | | **~19.27 MB** |

