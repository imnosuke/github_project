# APP-01 — Phạm vi và stack ứng dụng

Ngày: 14/11/2026. Trạng thái: **hoàn tất quyết định thiết kế phía ứng dụng**. Streamlit đã được người phụ trách lựa chọn; chưa triển khai app hoặc cài dependencies.

## Quyết định stack

| Thành phần | Lựa chọn | Mục đích |
| --- | --- | --- |
| UI và xử lý request | Streamlit | Một ứng dụng Python đa trang, phát triển local |
| Data processing | pandas | Xử lý dữ liệu phục vụ hiển thị và analytics trong phạm vi truy vấn |
| Charts | Plotly | Biểu đồ tương tác |
| Fixture | Parquet | Dữ liệu mẫu có kiểu, dùng cùng adapter interface với nguồn thật |
| Serving connector | clickhouse-connect | Đọc Gold/serving views từ phía Python server |
| ML baseline về sau | scikit-learn | Training/evaluation sau khi chốt ML-01 |

Bản đầu không cần API service riêng. Streamlit chạy Python server và truy cập nguồn dữ liệu qua adapter. Credentials lấy từ môi trường server, không đưa vào client hay commit. Chốt phiên bản dependencies trong APP-03 khi kiểm tra môi trường; tài liệu này không khẳng định compatibility đã được thử.

## Các màn hình bản đầu

| Trang | Chức năng | Metric/đầu ra |
| --- | --- | --- |
| Overview | Chọn kỳ, xem tổng quan và trend | Tracked repos, repos có activity, total events, star/fork events theo kỳ |
| Repository Explorer | Tìm tên, lọc metadata, xem detail và so sánh hai repo | Daily time series, push/PR/issue metrics; metadata có thể chưa có |
| Growth Analytics | Chọn anchor date và cửa sổ 7/30 ngày | Stars trong kỳ, kỳ trước, absolute delta, growth percent, ranking |

Unique actors theo ngày chỉ hiển thị ở grain repo/ngày; không cộng thành unique contributors cả kỳ. Growth không đồng nghĩa với net stars hoặc tổng stars hiện tại.

## User flow và demo mục tiêu

1. Mở Overview, thấy nhãn demo/live và ngày dữ liệu complete gần nhất.
2. Chọn khoảng ngày, xem trend và danh sách repo có activity.
3. Tìm một repo trong Explorer, mở detail và đối chiếu hai repo cùng thời gian.
4. Sang Growth, chọn 7/30 ngày, xem xếp hạng và giải thích metric.
5. Gặp ngày thiếu dữ liệu thì thấy cảnh báo và không nhận một growth score giả.

Mọi trang cần loading, empty, error, missing metadata, insufficient history và incomplete/stale data states. Bộ lọc thời gian dùng ngày UTC, ranh giới inclusive theo contract.

## Ranh giới với Superset

Streamlit phục vụ trải nghiệm tìm kiếm, detail, comparison, custom analytics và ML. Superset hiện có tiếp tục phục vụ BI ad hoc và đối soát Gold; không cần sao chép mọi chart sang app. Pipeline và việc xây Gold vẫn thuộc DE.

## Cấu trúc và cách chạy dự kiến

Đề xuất đặt code dưới `apps/streamlit/`, entrypoint `app.py`, các module riêng cho pages, data adapters và analytics. Cấu trúc cụ thể triển khai ở APP-03/04; hiện chưa tạo entrypoint.

Lệnh mục tiêu sau khi implementation và môi trường đã sẵn sàng:

```bash
streamlit run apps/streamlit/app.py
```

Chuyển fixture/live bằng cấu hình adapter. Không tải toàn lịch sử vào UI để lọc; truy vấn nguồn thật phải giới hạn thời gian và phân trang.

## Bước kế tiếp

[APP-02 — Data contract](APP-02-data-contract-v1.md), sau đó APP-03 fixture và data adapter. ML, Radar, Health và Cohorts ngoài scope bản đầu.
