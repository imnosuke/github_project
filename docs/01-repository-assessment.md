# Đánh giá tiến độ repository

Ngày: **14/11/2026** · Mốc kiểm tra: `156cd42`.

## Kết luận

Repo đã vượt mức khung rỗng: có mã nối GH Archive → Airflow → MinIO Parquet → ClickHouse Bronze → dbt Silver/Gold → Superset. Đây là prototype có luồng xuyên suốt ở mức mã nguồn, chưa đủ bằng chứng để nghiệm thu một pipeline chạy ổn định hoặc MVP hoàn chỉnh.

Ước lượng đã trao đổi: **25–35% phạm vi MVP theo mức độ hiện diện của mã**. Con số này là nhận định sơ bộ, không phải phép đo theo effort, thời gian hay tỷ lệ đã nghiệm thu. Nên dùng các tiêu chí hoàn thành trong backlog thay cho phần trăm khi báo cáo tiến độ chính thức.

Theo timeline kế hoạch, repo gần phần hạ tầng/ingestion của tuần 2 và làm trước một phần Gold/dashboard tuần 5–7. Không thể coi đã hoàn thành đến tuần 7 vì các phần xử lý, backfill và chất lượng dữ liệu ở giữa còn thiếu.

## Những phần đã có

| Hạng mục | Bằng chứng | Trạng thái |
| --- | --- | --- |
| Hạ tầng | `docker-compose.yaml`, Dockerfiles | Có Airflow, PostgreSQL metadata, MinIO, ClickHouse, Superset; chưa kiểm chứng khởi chạy |
| Ingestion | `airflow/scripts/gharchive_extractor.py` | Tải theo giờ, streaming download, timeout; chuyển Parquet theo batch, Snappy |
| MinIO | Hàm upload trong extractor | Đường dẫn theo year/month/day; giờ nằm trong tên file |
| Orchestration | `airflow/dags/gharchive_to_minio_dag.py` | DAG hourly, retries, nối các bước tới dbt và cleanup |
| Bronze | `airflow/scripts/clickhouse_loader.py` | Bảng events, `_source_file`, `_ingested_at`, nạp từ S3 |
| Silver | `dbt_gharchive/models/silver/stg_gharchive_events.sql` | Chuẩn hóa common fields, JSON payload push/PR/issue, cờ bot |
| Gold | `dbt_gharchive/models/gold/` | Repo/ngày, actor/ngày, event/giờ |
| Data tests | Hai file `schema.yml` của Silver/Gold | 9 khai báo `not_null`; chưa có bộ kiểm tra đầy đủ |
| BI | `superset/bootstrap_clickhouse.py` | Mã tạo ba dataset Gold, năm chart, một dashboard |
| Tài liệu | `README.md` | Hướng dẫn kiến trúc, cài đặt, vận hành |

## Khoảng cách với kế hoạch

| Yêu cầu | Hiện trạng quan sát được |
| --- | --- |
| Spark Bronze → Silver | Chưa có service/job Spark |
| Registry và lọc tracked repositories | Chưa có; extractor xử lý toàn bộ events của file |
| Raw immutable, checksum, manifest | Raw gzip chỉ upload tùy chọn, mặc định tắt; chưa có checksum/manifest |
| Incremental processing | Silver/Gold đều materialize toàn bảng |
| Backfill theo range | Có custom date/hour; chưa có workflow range, checkpoint, kiểm tra đủ giờ |
| Metadata API | Chưa có GitHub API client/snapshot DAG |
| Data model | Một Silver rộng và ba Gold aggregate; thiếu dimensions và facts chuyên biệt theo kế hoạch |
| Analytics nâng cao | Chưa có rolling 7/30 ngày, growth, health, ecosystem, cohort |
| Control tables | Chưa có `ingestion_run`, `source_file`, `data_quality_result`, `repository_registry` |
| Quality/observability | Chưa có completeness, freshness, volume anomaly, operations dashboard |
| Tests | Chưa thấy bộ unit/integration/E2E tests riêng |
| ML | Chưa có features, training, evaluation, inference hoặc MLflow |

Kiến trúc hiện tại đặt Bronze/Silver/Gold trong ClickHouse, trong khi kế hoạch có Spark và các dataset Silver/Gold trên lake. Nhóm cần chốt giữ kiến trúc kế hoạch hay điều chỉnh có tài liệu; không nên xem tên các tầng là bằng chứng hai kiến trúc đã tương đương.

## Findings cần ưu tiên

### 1. Silver/Gold rebuild toàn lịch sử

Các model dùng `materialized='table'`, không có điều kiện incremental theo partition. Mỗi lượt ingest giờ đều chạy lại dbt cho toàn dữ liệu. Chi phí tăng theo lịch sử và không đáp ứng yêu cầu chỉ cập nhật partition bị ảnh hưởng.

Đề xuất: thống nhất grain/partition, triển khai cập nhật phần bị ảnh hưởng và kiểm tra kết quả không đổi ở các partition khác.

### 2. Nạp lại chưa an toàn khi lỗi giữa chừng

Loader chạy `DELETE WHERE _source_file = ...` với `mutations_sync = 1`, sau đó mới `INSERT`. Nếu insert lỗi, dữ liệu cũ đã bị xóa. Cơ chế hỗ trợ nạp lại thành công nhưng chưa bảo đảm phục hồi an toàn.

Đề xuất: staging và cơ chế công bố/thay thế dữ liệu có kiểm soát. Thiết kế cụ thể phụ thuộc partition/storage đã chọn; kiểm thử lỗi sau delete hoặc trước publish là bắt buộc.

### 3. Dữ liệu lỗi có thể bị che khuất

- JSON parse lỗi bị bỏ qua, chưa có reject count hoặc quarantine.
- `parseDateTimeBestEffortOrZero` đưa timestamp lỗi về giá trị zero.
- Actor/repo thiếu được thay bằng `0`; `not_null` không phát hiện giá trị sentinel này.
- Chưa có unique event test, accepted values, freshness, completeness hay đối soát giữa các tầng.
- Bronze `ReplacingMergeTree` có khóa `(event_id, created_at)`; không nên coi đây là bảo đảm uniqueness chỉ theo event ID trong mọi trường hợp.

### 4. Metric cần định nghĩa nghiệp vụ

`unique_contributors` đếm mọi actor tương tác, kể cả chỉ star repo. Nên đổi tên thành unique actors hoặc định nghĩa rõ loại event được xem là đóng góp. Giá trị actor `0` cũng cần được loại khỏi phép đếm người hợp lệ.

Top repositories hiện lấy các dòng repo/ngày và sắp xếp theo `total_events`, chưa phải xếp hạng repo tổng hợp cho một khoảng ngày. Stars gained từ event cần phân biệt với total stars hiện tại và net star growth.

### 5. Mapping thời gian và cleanup cần kiểm thử

DAG lấy `data_interval_start` rồi trừ một giờ, tức xử lý lùi thêm một interval. Cần xác định đây là độ trễ chủ đích hay sai mapping; kiểm thử scheduled run, manual run và backfill.

Cleanup nhận output của task dbt. `all_done` chưa bảo đảm có metadata nếu upstream thất bại trước khi trả output; cần thiết kế cleanup lấy đường dẫn từ bước đã có kết quả.

### 6. Bootstrap có thể che lỗi

Một số lệnh init dùng `|| true`, gồm bootstrap Superset. Dịch vụ có thể khởi động dù khởi tạo dashboard thất bại. Cần phân biệt lỗi chấp nhận được như tài khoản đã tồn tại với lỗi migration/kết nối/bootstrap thật.

### 7. Môi trường chưa được khóa để tái lập

Requirements dùng nhiều khoảng phiên bản mở, một số images dùng `latest`. Repo track `.env`; dòng ignore `.env` đang bị comment, chưa có `.env.example`. Cần chuẩn hóa cấu hình mẫu, bỏ track secret thật nếu có và khóa dependencies/images sau khi xác minh bộ phiên bản chạy được.

## Phạm vi đã xác minh

- Đọc source/config, danh sách tracked files và lịch sử hai commit gần nhất.
- Parse cú pháp bốn file Python: DAG, extractor, loader, Superset bootstrap; đều hợp lệ.
- Không có Docker CLI trong môi trường đánh giá, nên không chạy Compose, dbt trên ClickHouse hay E2E.
- Local thiếu `boto3`; chưa chạy extractor tích hợp. Việc module khác có mặt không chứng minh đúng phiên bản hoặc import/runtime hoạt động.
- Chưa xác minh dữ liệu trong volumes, lịch sử DAG runs, throughput, dashboard rendering hoặc hiệu năng thực tế.
- Trong lượt đánh giá ban đầu không sửa source code.
