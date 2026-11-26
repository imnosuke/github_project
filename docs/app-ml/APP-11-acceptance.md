# APP-11 — Nghiệm thu và bàn giao MVP

Phạm vi MVP gồm Overview, Repository Explorer và Growth Analytics. Bài nghiệm thu chạy bằng Streamlit AppTest với fixture và với publication APP-02 đọc qua HTTP từ ClickHouse. Bản local dùng dữ liệu GH Archive phát lại trong một ClickHouse riêng.

## Chạy lại trên máy local

Chạy từ thư mục gốc repo. Ví dụ dùng PowerShell và Python 3.12.

```powershell
python -m venv .venv-app
.\.venv-app\Scripts\Activate.ps1
python -m pip install -r apps/streamlit/requirements.txt -r ml/requirements.txt
python -m pytest apps/streamlit/tests ml/tests -q
python -m apps.streamlit.mvp_acceptance --source fixture
```

Fixture trong repo kiểm tra luồng chính và việc ẩn số tổng hợp vào ngày provisional `2026-11-03`. APP-02 và [tài liệu cấu hình APP-07](APP-07-adapter-preparation.md#cấu-hình-chạy) mô tả biến môi trường và kiểu dữ liệu. `.env.example` là mẫu cho tiến trình Streamlit, cần export các biến trước khi chạy.

### Phát lại snapshot GH Archive trong ClickHouse riêng

Lấy đúng bộ snapshot đã nghiệm thu mà không cần checkout toàn bộ checkpoint theo giờ. Mốc dữ liệu dùng trong biên bản là `1e205c6c`.

```powershell
git fetch origin feature/ml-gharchive-backfill-checkpoints
$dataRoot = Join-Path $env:TEMP 'reposcope-app11-reference'
New-Item -ItemType Directory -Force $dataRoot | Out-Null
$snapshotPath = 'ml/datasets/gharchive-2025-11-16/snapshot'
git archive --format=tar -o "$dataRoot/reference.tar" 1e205c6c $snapshotPath
tar -xf "$dataRoot/reference.tar" -C $dataRoot
$snapshot = Join-Path $dataRoot $snapshotPath
```

Khởi động một ClickHouse local riêng. Nếu dùng Docker, ví dụ sau dùng cùng image với Compose của repo. Đặt `CLICKHOUSE_PASSWORD` cho user local trước khi chạy và chờ `/ping` trả HTTP 200 rồi mới seed. Lượt nghiệm thu ghi bên dưới dùng ClickHouse native trên WSL.

```powershell
docker run --rm -d --name reposcope-app11 -p 127.0.0.1:18126:8123 -e CLICKHOUSE_PASSWORD -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 clickhouse/clickhouse-server:24.3-alpine
Invoke-WebRequest http://127.0.0.1:18126/ping

$env:APP_CLICKHOUSE_HOST = '127.0.0.1'
$env:APP_CLICKHOUSE_PORT = '18126'
$env:APP_CLICKHOUSE_SECURE = 'false'
$env:APP_CLICKHOUSE_DATABASE = 'app11_qa'
$env:APP_CLICKHOUSE_USER = 'default'
$env:APP_CLICKHOUSE_PASSWORD = $env:CLICKHOUSE_PASSWORD
python -m apps.streamlit.seed_qa_publication --snapshot "$snapshot" --start 2025-06-19 --end 2025-08-18
```

Lệnh seed tạo database `app11_qa` mới và ghi manifest sau khi đã nạp bốn bảng. Lệnh chỉ nhận địa chỉ IP loopback, và từ chối ghi đè nếu database đã tồn tại. Khi seed lỗi giữa chừng hoặc muốn nạp lại, dùng một instance thử nghiệm mới.

Dùng tài khoản quản trị local để cấp quyền đọc. Với ví dụ Docker, mở SQL client bằng `docker exec -it reposcope-app11 clickhouse-client --user default --password`.

```sql
CREATE USER app11_reader IDENTIFIED BY '<local-reader-password>';
GRANT SELECT ON app11_qa.* TO app11_reader;
```

Sau đó chuyển sang tài khoản chỉ đọc và chạy nghiệm thu. Chọn `2025-08-18` để kiểm chứng ca provisional.

```powershell
$env:APP_CLICKHOUSE_USER = 'app11_reader'
$env:APP_CLICKHOUSE_PASSWORD = '<local-reader-password>'
python -m apps.streamlit.mvp_acceptance --source clickhouse --reference "$snapshot" --reference-day 2025-08-17 --anchor 2025-08-17 --incomplete-day 2025-08-18
```

Lệnh trả JSON và exit `0` khi đạt. Exit `2` ghi kiểm tra lỗi. Giữ JSON cùng commit ứng dụng, mốc snapshot và môi trường chạy. `publication_load_seconds` đo tải cả publication qua HTTP. `validation_seconds` đo đối soát trong tiến trình. `render_seconds` đo lần chạy AppTest, gồm cả dựng giao diện phía server.

### Kịch bản demo

1. Đặt `APP_DATA_SOURCE=clickhouse` và chạy `python -m streamlit run apps/streamlit/app.py` với tài khoản reader ở trên. Dùng `APP_DATA_SOURCE=fixture` để demo bộ dữ liệu tổng hợp đi kèm repo.
2. Mở **Repository Explorer**, chọn một repo như `apache/airflow`, xem chi tiết và so sánh với repo thứ hai trong cùng ngày `2025-08-17` UTC. Snapshot này chưa có metadata, nên Explorer hiển thị registry và event metrics.
3. Chuyển sang **Growth Analytics**, giữ ngày kết thúc `2025-08-17` UTC và chọn cửa sổ 30 ngày. Kiểm tra hai kỳ 30 ngày và số repo hợp lệ.
4. Mở **Overview**, xem KPI ngày `2025-08-17`, rồi mở rộng đến `2025-08-18` UTC. Kiểm tra cảnh báo provisional và KPI tổng hiển thị `—`.

`Star events` đếm `WatchEvent`, `Fork events` đếm `ForkEvent`, và `Total events` đếm events hợp lệ sau dedup. Định nghĩa metric, completeness và cách tính theo cửa sổ UTC nằm trong [APP-02](APP-02-data-contract-v1.md). Kết quả dự đoán chỉ xuất hiện trong demo sau khi ML-04 đủ điều kiện ở bảng bên dưới.

## Kết quả đã xác minh ngày 26/11/2026

| Phần | Bằng chứng |
| --- | --- |
| Suite ứng dụng và ML | 143 test pass trên Windows, Python 3.12.3. |
| Fixture | Ba màn hình, đổi repo trong Explorer, giữ bộ lọc ngày, 5 repo đủ điều kiện Growth và ẩn KPI ngày provisional. |
| ClickHouse local | ClickHouse 24.3.12.75, Windows/WSL, tài khoản SELECT. Publication `app11-local-2025-06-19-2025-08-18` gồm 20 repo, 60 ngày complete và một ngày provisional. |
| Đối soát | Kiểm checksum và tính lại số đếm theo từng repo từ 24 Parquet giờ ngày `2025-08-17`. Cả 20 repo khớp snapshot và ClickHouse. Tổng **1.312 events, 164 stars, 53 forks**. |
| UI trên ClickHouse | Overview hiển thị đúng tổng, Explorer đổi repo và so sánh, Growth đủ 20/20 repo. UI ẩn KPI ngày `2025-08-18` provisional. |
| Lỗi nguồn | Dừng ClickHouse thử nghiệm. Lệnh trả exit `2` và UI hiện lỗi kèm nút **Thử lại**. |
| Thời gian local | Lượt 15:15 giờ Việt Nam đo tải publication **1,317 s**, đối soát **0,352 s** và AppTest render lần đầu **1,874 s**. |

Hai lần replay pipeline ngày `2025-01-15` trong môi trường Airflow local trước đó có 24/24 giờ và cùng kết quả Gold cho hai repo. Đây là ca kiểm thử pipeline riêng. Ca 60 ngày ở trên nạp snapshot vào lớp phục vụ để kiểm tra đường đọc ứng dụng.

## Việc còn mở và điểm bắt đầu

| Việc | Lý do còn mở | Phụ thuộc và điều kiện có thể bắt đầu |
| --- | --- | --- |
| Chạy lại từ máy người nhận | Bài nghiệm thu hiện được chạy bằng AppTest trên máy phát triển. | Có thể bắt đầu ngay khi người nhận có branch này, Python và quyền lấy snapshot. Dùng fixture trước, sau đó dùng ClickHouse local theo hướng dẫn trên. |
| Nghiệm thu Gold staging của DE | Kết quả local dùng snapshot phát lại. Cần xác minh chính producer và publication mà DE bàn giao. | APP-07 và APP-02. Bắt đầu khi DE cung cấp endpoint đọc được, tài khoản SELECT, publication ID/version/scope và coverage 60 ngày liên tiếp. Cần một ca đối soát độc lập cùng phạm vi repo và ngày với publication. |
| Đo latency và freshness trên staging | Số đo hiện tại lấy trên loopback. Ngưỡng latency và lịch công bố staging cần xác nhận theo môi trường chạy thực tế. | Có thể thu thời gian ngay khi đọc được endpoint staging. Đánh giá đạt SLA khi DE chốt ngưỡng và lịch công bố, cung cấp `expected_complete_through`, rồi chạy qua các lần cập nhật và ghi bằng chứng. |
| Demo dự đoán | Dự đoán cần model đã nghiệm thu, batch và reader đầu ra. | ML-03 có holdout hợp lệ, Gold được đối soát và có bằng chứng thời điểm khả dụng. Sau đó ML-04 thống nhất contract serving/SLA với DE và có publication dự đoán mà Explorer/Growth đọc được. |

Khi nhận môi trường DE, người nhận chạy lại `mvp_acceptance` với các biến `APP_CLICKHOUSE_*` của staging, thư mục snapshot tham chiếu đúng phạm vi, ngày đối soát và anchor do DE xác nhận. Thêm `--incomplete-day` khi có một ngày kiểm thử chưa complete nằm trong publication. Ghi kết quả vào biên bản với publication ID, thời gian đo và các trường hợp lỗi đã kiểm tra.
