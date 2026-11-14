# APP-04 — Khung ứng dụng Streamlit

Ngày: 14/11/2026. Trạng thái: **hoàn tất khung local**, chưa triển khai analytics APP-05/06 hoặc live adapter APP-07.

## Đã có

- Entry point `apps/streamlit/app.py`, navigation Overview / Repository Explorer / Growth Analytics.
- Sidebar ngày UTC dùng chung, giữ bộ lọc khi chuyển trang; mặc định 30 ngày đến ngày complete gần nhất.
- Nhãn DEMO, publication, thời điểm công bố, complete gần nhất và freshness theo expectation của manifest fixture.
- Loading spinner, empty source/search, load error với nút thử lại, incomplete/unknown day warning và bảng trạng thái.
- Explorer có preview danh sách và tìm tên; detail/comparison thuộc APP-05.
- Overview/Growth có placeholder rõ ràng; không hiển thị KPI/growth giả. Có ngày thiếu thì không công bố tổng kỳ.
- Cấu hình `APP_DATA_SOURCE` (chỉ fixture hiện được hỗ trợ), `APP_FIXTURE_DIR` tùy chọn; nút reload xóa cache adapter.

## Chạy local

Từ root, trong môi trường app đã cài `apps/streamlit/requirements.txt`:

```bash
streamlit run apps/streamlit/app.py
```

Không cần chạy Docker/pipeline. Fixture đi kèm có thể regenerate theo README ứng dụng.

## Kiểm tra

Streamlit AppTest kiểm tra navigation, bộ lọc ngày xuyên trang, cảnh báo incomplete, empty search và load failure; chạy chung với bốn test dữ liệu APP-03. AppTest kiểm tra thực thi/widgets, chưa là kiểm tra hình ảnh trên browser. Chưa công bố kết quả live hoặc benchmark.

Freshness fixture là tương đối với `expected_complete_through` trong manifest, không thể hiện GitHub hiện tại. Live SLA, snapshot consistency và UI metadata thiếu chi tiết tiếp tục ở task tương ứng.
