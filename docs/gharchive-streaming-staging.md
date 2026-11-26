# GH Archive streaming và dbt incremental

DAG ghi Parquet theo giờ lên MinIO, sau đó ghi thêm các event vào Bronze. Silver đọc Bronze với FINAL theo khóa `(event_id, created_at)`, giữ bản mới nhất, rồi tính các ngày đích cho Silver và Gold. Lần đọc lại cùng giờ phải dùng cùng scope; đổi scope hoặc sửa nguồn lịch sử cần một lần rebuild được DE đối soát.

Chạy CLI thủ công để lấy mẫu dùng prefix `samples/gharchive/`. Khi DAG gặp 404, lỗi JSON hoặc mất kết nối trong một giờ đã yêu cầu, task thất bại để Airflow retry. Cả raw và Parquet upload trực tiếp lên cùng key và S3 chỉ thay bằng object upload thành công. Bronze append và FINAL bảo vệ retry cho nguồn giờ bất biến.

## Kiểm tra staging trước khi triển khai

1. Chọn môi trường MinIO/ClickHouse staging riêng và cùng scope repo trong cả hai lượt. Trigger DAG với `custom_date=2025-01-15`, `start_hour=0`, `end_hour=23`, `hours_step=1`. Giữ record cap rỗng. Khi chuyển đổi bảng cũ, dùng `dbt_full_refresh=true` cho lần migrate đã được DE lên lịch.
2. Kiểm tra đủ 24 Parquet và số dòng hàng giờ trong Bronze FINAL. So sánh tổng event, star và fork của Airflow/Superset với [ca APP-07](app-ml/APP-07-adapter-preparation.md). Chạy lại cùng giờ và so sánh Gold trước/sau. Kiểm tra thử một lần upload lỗi và một giờ 404 trên staging.
3. Đối soát một repo/ngày có PR close thiếu cờ merge. Hai cột PR ở Gold phải là NULL. APP-02 chỉ đánh dấu ngày complete sau khi xác minh đủ giờ, phạm vi và chất lượng.


## Kết quả kiểm tra local

- Pytest phát lại 24 file của snapshot APP-07 (516 events) qua parser và upload mock. Đã kiểm tra lỗi upload, thử lại và 404.
- ClickHouse local 24.3.12.75 trên máy đặt timezone Asia/Bangkok đã chạy SQL Silver/Gold với ngày đích UTC. Kết quả khớp đối soát trước và sau khi nạp lại. Staging cần chạy toàn bộ DAG, MinIO và dbt materialization.

## Bằng chứng DE cần lưu sau mỗi lần chạy

Dùng cùng `dag_run_id` để liên kết lần tải, nạp và build dbt. Ghi thời điểm bắt đầu/kết thúc UTC, scope repo, các giờ kỳ vọng/đã xử lý/thiếu, số record bị loại và lý do, checksum hoặc mã phiên bản object khi có, số dòng Bronze FINAL, kết quả dbt test và `publication_id` nếu đã công bố. Ghi riêng từng lần thử khi Airflow retry. Lần chạy có lỗi hoặc thiếu giờ vẫn cần một dòng trạng thái để APP-10 phân biệt đang trễ với chưa có dữ liệu vận hành.

Khi nối vào APP-10, khóa bản ghi theo `dag_run_id` và số lần thử. Freshness lấy từ publication thực tế và SLA đã chốt. Một giờ có Parquet rỗng vì scope không phát sinh sự kiện vẫn được tính là đã xử lý nếu đã xác minh tải và parse thành công.
