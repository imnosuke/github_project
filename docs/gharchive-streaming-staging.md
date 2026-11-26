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

## Bật producer APP-02 trong staging

Chạy với một writer và ClickHouse/MinIO staging riêng. Đưa file registry JSON vào thư mục scripts được mount vào Airflow. Registry pilot có một khoảng theo dõi mỗi ID, với `repository_id`, `repository_name`, `tracking_start_date` và các trường tùy chọn `tracking_end_date`, `category`, `ecosystem`. Dùng GitHub repo ID từ scope đã xác minh. `APP02_REGISTRY_FILE=/opt/airflow/scripts/<registry>.json` bật bước `publish_app02_gold`. Khi biến rỗng, DAG giữ cách ingest trước đó và bỏ qua publication. `APP02_WINDOW_DAYS` mặc định là 61 và giới hạn từ 1 đến 366 ngày. Tạo registry mới và đối soát lại trước khi đổi phạm vi ingest.

Ở chế độ publish, ingest dùng ID trong registry và ghi Parquet vào prefix theo phạm vi. Sau Bronze và `dbt run`/`dbt test` thành công, producer ghi bằng chứng theo ngày, giờ và run ID vào `app_serving.gold_hour_receipts`. Bản xuất dùng receipt theo đúng phạm vi, đối chiếu event counts của Gold với Silver và chỉ điền zero cho repo không có event khi cả ngày qua quality gate. Ngày thiếu giờ hoặc thiếu metric bắt buộc giữ `provisional` hoặc `missing`. Metadata có thể rỗng. `commits_pushed` giữ NULL nếu thiếu giá trị `size` hợp lệ. Hai metric PR merge giữ NULL khi chưa xác định được cờ merge hoặc action.

Producer kiểm tra số dòng ở bốn bảng trước khi ghi manifest. Retry sau commit của cùng DAG run trả lại publication ID. Retry trước commit tạo ID mới và giữ các dòng chưa commit ngoài đường đọc của ứng dụng. Giữ publication cũ cho reader đang dùng ID đó. Với schema pilot, mỗi publisher chạy riêng một môi trường. Thời điểm trong day status là bằng chứng đã xử lý đến dbt Gold. Thời điểm trong manifest phản ánh lượt công bố lớp phục vụ.

Dùng writer của pipeline cho bảng ingest/dbt/serving. Cấp tài khoản ứng dụng quyền SELECT trên `app_publications`, `repository_registry`, `repository_metadata`, `daily_data_status`, `repository_daily_metrics` trong `app_serving`. Chạy [APP-11 acceptance](app-ml/APP-11-acceptance.md) bằng tài khoản reader, với một ngày tham chiếu và anchor đủ hai cửa sổ 30 ngày. Giữ `expected_complete_through` là NULL đến khi đo và chốt SLA.

### Export trạng thái vận hành và bằng chứng thời điểm đọc

Từ môi trường Airflow có kết nối metadata PostgreSQL, chạy `python /opt/airflow/scripts/export_pipeline_runs.py --airflow-metadata --output /opt/airflow/logs/app10-airflow-runs.json` và cấu hình `APP_PIPELINE_RUNS_FILE` trên app trỏ tới bản xuất. Script cũng nhận `--database PATH` cho lần chạy SQLite local. Mỗi bản ghi gồm phạm vi giờ, kết quả upload đã xác nhận, số lần thử lỗi, thời lượng, trạng thái dbt và publication ID khi có. Khi Airflow chưa có XCom, giờ upload và giờ thiếu để trống. Khi một giờ lỗi trước khi đóng Parquet, số record bị loại vẫn chưa xác định.

Sau mỗi lần publish, dùng tài khoản reader tại endpoint app chạy `python -m ml.observe_publication --source-name ENDPOINT_NAME --output PATH`. Lệnh giữ lần đầu đọc thành công cho mỗi cặp endpoint/publication ID. Lưu các file quan sát ở nơi tồn tại qua restart và theo lịch publish. Một replay lịch sử ghi thời điểm reader đọc được bản replay hiện tại. Nghiệm thu availability của ML cần bằng chứng trước `decision_at` và đủ thời gian quan sát nhãn.

### Kết quả replay local ngày 26/11/2026

- **DAG với publisher bật.** Hai lượt `dag.test` cùng ngày `2025-01-15` nạp 24 giờ qua S3 và Bronze, chạy dbt rồi công bố APP-02. Cả hai lượt cho 516 events, 33 stars và 19 forks. Truy vấn kiểm tra chỉ có 24 giờ distinct. Lượt tải giờ gặp 404 kết thúc failed và giữ hai publication đã commit.
- **Cửa sổ dài.** Dùng checkpoint nhánh dữ liệu tại `1e205c6c` để replay vào Bronze, gồm 1.463 giờ và 205.314 dòng. `dbt` chạy incremental theo lô 5 ngày và 4 test Silver/Gold đạt. Producer công bố 20 repo với 60 ngày complete (`2025-06-19` đến `2025-08-17`) và ngày `2025-08-18` provisional với 23 giờ. Đối soát event/star/fork khớp toàn bộ 1.200 repo-ngày complete. Lỗi chèn trước manifest giữ publication cũ, và retry của run đã commit trả lại cùng ID.
- **Reader.** APP-11 đạt với tài khoản SELECT. Lần đo local tải publication 0,852 giây và đối soát 0,312 giây. Mốc validator đọc publication thành công được lưu lúc `2026-11-26T10:58:22.050036Z`.
- **Holdout ML-03.** Phạm vi 89 ngày đủ 2.136 giờ có 2.255 sự kiện đóng PR thiếu cờ merge, ảnh hưởng 541 cặp repo-ngày có event quan sát. Phạm vi nghiệm thu APP-11 dùng cửa sổ đã đạt quality gate. Giữ giá trị PR chưa xác định ở NULL trong holdout. Chỉ bổ sung từ bằng chứng xác nhận được theo repo, PR và lần đóng nếu dùng các ngày đó làm Gold complete.

Lượt local dùng SQLite cho metadata Airflow. Bước bàn giao tiếp theo là chạy exporter với PostgreSQL của staging và đo nhiều lần publish để chốt freshness/SLA. Lịch sử availability dành cho ML bắt đầu từ các lần đọc thực tế ở endpoint đó.
