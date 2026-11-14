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

Có thể truyền `directory=...` để đọc bộ fixture khác. `source="live"` hiện báo lỗi rõ; implement trong APP-07. UI phải đọc `adapter.envelope` và gắn nhãn fixture.

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

APP-06: Growth dùng end date làm anchor, tự đọc đủ hai cửa sổ liên tiếp; start date chung chỉ áp dụng Overview/Explorer. Không công bố tổng KPI cho kỳ incomplete, không xếp hạng các repo thiếu lịch sử.
