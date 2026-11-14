# APP-03 — Fixture và data adapter

Ngày: 14/11/2026. Trạng thái: **hoàn tất phạm vi fixture local**; chưa có UI/live integration.

## Đầu ra

- `apps/streamlit/data/generate_fixture.py`: dữ liệu tổng hợp tái lập 95 ngày, sáu repo.
- `apps/streamlit/data/fixtures/`: bốn Parquet datasets và manifest theo APP-02 draft.
- `apps/streamlit/data/adapter.py`: protocol và FixtureAdapter, search/pagination, detail, time series, growth 7/30 ngày.
- `apps/streamlit/tests/test_fixture.py`: kiểm tra expected growth/window, zero/missing/provisional, metadata thiếu, bounds, duplicate và quality gates.
- [Hướng dẫn chạy](../../apps/streamlit/README.md).

Fixture gồm growth tăng/giảm, zero, new activity, short history và missing metadata. Ngày missing không bị đổi thành zero; incomplete/history thiếu không có growth score hợp lệ. Bot chỉ là heuristic actor count, không tạo danh sách actor events.

## Verification

Chạy generator rồi `python3 -m pytest apps/streamlit/tests -q` từ root. Kiểm tra regenerate bằng so sánh nội dung DataFrames/manifest, không dùng đồng hồ hiện tại. Xem kết quả thực tế trong báo cáo commit/trao đổi; không coi đây là kiểm thử pipeline thật.

Không cài dependencies vào Airflow, không sửa Gold hay contract đã đề xuất. Fixture giữ contract draft; xác nhận DE vẫn là gate cho APP-07. Dependencies UI và entrypoint sẽ làm ở APP-04.

## Giới hạn và bước tiếp theo

Adapter hiện hỗ trợ fixture và validation trọng yếu, chưa là schema validator tổng quát, chưa hỗ trợ live freshness/publish consistency. Ranking trả invalid rows có state để UI báo số bị loại. Bước tiếp theo APP-04: giao diện Streamlit, navigation và các trạng thái dữ liệu.
