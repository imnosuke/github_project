# Application data layer — APP-03

Đã có khung Streamlit local và lớp dữ liệu fixture. Chưa có live ClickHouse adapter. Fixture là dữ liệu tổng hợp, không dùng đánh giá chất lượng ML.

Chạy từ thư mục gốc repository trong môi trường Python riêng, không cài vào môi trường Airflow:

```bash
python3 -m venv .venv-app
source .venv-app/bin/activate
python -m pip install -r apps/streamlit/requirements.txt
python -m apps.streamlit.data.generate_fixture
python -m pytest apps/streamlit/tests -q
```

Các khoảng phiên bản dependency là giới hạn ban đầu, chưa là lockfile cho mọi môi trường.

## Sử dụng

```python
from apps.streamlit.data import get_adapter

adapter = get_adapter(source="fixture")
repos = adapter.list_repositories(query="rising", limit=20)
detail = adapter.repository_detail(1001)
series = adapter.time_series(1001, "2026-10-01", "2026-11-01")
ranking = adapter.growth_ranking("2026-11-01", window=30)
```

Có thể truyền `directory=...` để đọc bộ fixture khác. `source="clickhouse"` kiểm tra cấu hình và báo `NotImplementedError` cho tới khi live adapter hoàn thiện. UI đọc `adapter.publication()` để gắn nhãn nguồn dữ liệu.

## Fixture

- 95 ngày từ 2026-08-01 đến 2026-11-03; sáu repo tổng hợp, generator không dùng random/time hiện tại.
- Các case: rising, falling, quiet, new activity, short history, missing metadata.
- 2026-08-15 missing, mọi metric null; 2026-11-03 provisional.
- Metadata có heuristic actor/bot counts; active_contributors để null theo contract chưa chốt.
- Registry, metadata, daily metrics, day status lưu Parquet; manifest giữ version/source/publication.
- Fixture tập trung star growth và edge cases, các event metrics khác bằng zero; không đại diện phân phối GitHub thật.

Kết quả growth bao gồm các row không hợp lệ kèm `state`, current/delta null, xếp cuối. Consumer phải loại `insufficient_history`/`incomplete_data` khỏi bảng ranking và báo số bị loại. `new_activity` có growth_pct null; `no_activity` có growth_pct zero.

Validator kiểm tra keys, coverage, scope, counts và completeness quan trọng. Đây không phải validator JSON Schema tổng quát cho dữ liệu producer bất kỳ; live adapter cần kiểm tra schema/type và snapshot consistency bổ sung. Manifest là một publication cố định cho cả bộ fixture. Chưa có UI freshness indicator hoặc live publish protocol.

Contract: [APP-02](../../docs/app-ml/APP-02-data-contract-v1.md).

## Chạy giao diện APP-04

```bash
streamlit run apps/streamlit/app.py
```

Có ba trang điều hướng, bộ lọc ngày dùng chung, nhãn DEMO và trạng thái completeness/freshness. Overview có KPI/trend; Growth có ranking 7/30 ngày và danh sách loại do thiếu dữ liệu; Explorer có filters, pagination, detail và comparison (APP-05). `APP_DATA_SOURCE=fixture` là mặc định; `APP_FIXTURE_DIR` tùy chọn chỉ tới bộ fixture khác. Nút tải lại làm mới cache.

Để mở snapshot GH Archive đi kèm repo, chạy từ root repo bằng PowerShell.

```powershell
$env:APP_DATA_SOURCE = 'snapshot'
$env:APP_SNAPSHOT_DIR = (Resolve-Path 'apps/streamlit/data/snapshots/gharchive-2025-01-15').Path
python -m streamlit run apps/streamlit/app.py
```

`APP_SNAPSHOT_DIR` trỏ tới thư mục có `manifest.json` và các bảng Parquet theo APP-02. Snapshot ví dụ bao phủ ngày 2025-01-15 UTC cho `apache/airflow` và `apache/superset`. Thư mục `parquet/` chứa đủ 24 file theo giờ để đối soát các bảng tổng hợp. Manifest ghi trạng thái, checksum của từng file và lần che thông tin đăng nhập trong một URL ở nội dung bình luận.

### Thử đọc Gold trên ClickHouse local

Chế độ `clickhouse_snapshot` chạy với ClickHouse loopback đã nạp Silver/Gold cho cùng ngày và cùng phạm vi repo. Registry, metadata và trạng thái ngày lấy từ snapshot tham chiếu. Số liệu hiển thị đến từ bảng Gold và chỉ được chấp nhận khi khớp snapshot.

```powershell
$env:APP_DATA_SOURCE = 'clickhouse_snapshot'
$env:APP_SNAPSHOT_DIR = (Resolve-Path 'apps/streamlit/data/snapshots/gharchive-2025-01-15').Path
$env:APP_CLICKHOUSE_HOST = '127.0.0.1'
$env:APP_CLICKHOUSE_PORT = '18123'
$env:APP_CLICKHOUSE_SECURE = 'false'
$env:APP_CLICKHOUSE_USER = 'reposcope_reader'
python -m streamlit run apps/streamlit/app.py
```

Ví dụ dùng cổng của lượt thử APP-07. Đặt cổng và cấu hình người dùng theo ClickHouse local đang chạy. Tích hợp Gold live vẫn chờ các bảng phục vụ theo contract và xác nhận từ DE.

APP-06: Growth dùng end date làm anchor, tự đọc đủ hai cửa sổ liên tiếp; start date chung chỉ áp dụng Overview/Explorer. Không công bố tổng KPI cho kỳ incomplete, không xếp hạng các repo thiếu lịch sử.

## Chuẩn bị APP-07

UI dùng `DataAdapter` thay vì bảng nội bộ của fixture. Xem
[interface và cấu hình ClickHouse](../../docs/app-ml/APP-07-adapter-preparation.md)
và `.env.example` trong thư mục này. Export biến môi trường trước khi chạy;
file mẫu không tự được load. `APP_DATA_SOURCE=clickhouse` hiện báo lỗi rõ ràng
sau khi validate cấu hình: chưa có live adapter, không fallback sang demo.
Không commit mật khẩu; live cần DE xác nhận contract và cấp tài khoản chỉ đọc.

## Kiểm thử Forecast với fixture

Chạy bộ kiểm thử bằng `python -m pytest apps/streamlit/tests/test_forecast_fixture.py -q`.
Để mở riêng trang kiểm thử, chạy:

```powershell
$env:APP_ML_MODEL_DIR = (Resolve-Path 'ml/runs/github_pc_model').Path
python -m streamlit run apps/streamlit/tests/forecast_fixture_app.py
```

`APP_ML_MODEL_DIR` trỏ tới lần train fixture đã hoàn tất. Trang kiểm thử kiểm tra loại nguồn và checksum trước khi hiển thị kết quả đánh giá synthetic. Trang này có entry point riêng, ngoài điều hướng ứng dụng chính. Dự đoán thật sẽ đọc publication batch theo [dự thảo ML-04](../../docs/app-ml/ML-04-prediction-contract-draft.md).
