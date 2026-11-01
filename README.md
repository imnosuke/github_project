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
   `resolve_target_datetime` $\rightarrow$ `download_from_gharchive` $\rightarrow$ `convert_to_parquet` $\rightarrow$ `upload_to_minio_s3` $\rightarrow$ `load_to_clickhouse_bronze` $\rightarrow$ `dbt_transform_silver_gold` $\rightarrow$ `cleanup_temp_files`.

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

