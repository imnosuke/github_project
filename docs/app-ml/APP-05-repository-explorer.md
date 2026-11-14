# APP-05 — Repository Explorer

Ngày: 14/11/2026. Trạng thái: **hoàn tất local trên fixture**; chưa nghiệm thu nguồn thật.

## Chức năng

- Tìm theo tên không phân biệt hoa/thường, lọc language/category/ecosystem; chọn dữ liệu thiếu metadata.
- Sắp xếp tên A–Z/Z–A hoặc ID, phân trang 5/10/20 dòng.
- Chọn repository từ kết quả đã lọc để xem detail: metadata snapshot, tổng event metrics trong kỳ, time series và bảng daily.
- So sánh hai repo khác nhau trong kết quả lọc, cùng kỳ UTC; bảng metric và chart star events.
- Metadata hiển thị thời điểm observation, không gán thành metadata lịch sử. Snapshot stars không được cộng vào star events.
- Repo thiếu metadata vẫn dùng được; lịch sử thiếu/ngày không complete không được tổng hợp toàn kỳ. Biểu đồ giữ gap cho ngày thiếu/provisional hoặc ngoài scope.
- Không cộng daily unique actors để gọi là unique contributors trong kỳ. Event metrics gồm bot theo contract.

## Implementation và kiểm tra

`apps/streamlit/explorer.py` tách khỏi app shell. Catalog hiện đọc fixture registry/latest metadata; khi làm APP-07 phải đưa filtering/pagination vào query adapter live thay vì tải tất cả registry.

Kiểm tra AppTest cho detail thiếu metadata, short history, compare khác ID và filter không có metadata; kiểm tra độc lập expected total 59 star events của rising repo từ 26/10 đến 01/11, mask provisional và từ chối tổng incomplete. Chạy cùng bộ tests hiện có:

```bash
python3 -m pytest apps/streamlit/tests -q
```

Chưa kiểm tra hình ảnh browser, chưa có query latency benchmark hoặc live database. Fixture chủ yếu có star events, các metrics PR/issues/push bằng zero; chưa thể dùng kết quả đó để khẳng định parser/metric pipeline thật đúng.

## Tiếp theo

APP-06: Overview và Growth Analytics 7/30 ngày. Chưa triển khai các trang đó trong APP-05.
