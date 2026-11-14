# Phối hợp DE và ứng dụng/ML theo cách cuốn chiếu

## Kết luận phối hợp

Có thể phát triển ứng dụng và bộ khung ML trước khi pipeline hoàn thiện. Điều kiện là thống nhất hợp đồng dữ liệu, dùng fixture cùng schema và tích hợp từng phần với dữ liệu thật.

Ứng dụng bắt đầu ngay; chất lượng model thật chỉ được đánh giá khi lịch sử đủ dài và đã kiểm tra chất lượng.

## Trách nhiệm

| DE/pipeline | Ứng dụng/ML | Cần cùng chốt |
| --- | --- | --- |
| Ingest, raw, Silver, dedup | UI, search/filter, repository detail | Scope repo, event types |
| Incremental, backfill, recovery | Growth views, comparison, scores | Grain, schema, metric definitions |
| GitHub snapshots và Gold | Features, training, evaluation | Timestamp, missing data, availability |
| Quality, serving, operations data | Inference consumer, prediction display | Kết nối, version schema, publish outputs |

Phía ứng dụng nên tiêu thụ Gold tables hoặc serving views ổn định. Không phụ thuộc trực tiếp vào tổ chức Spark jobs, raw objects hay cấu trúc nội bộ Silver. Nếu cần API, phía ứng dụng thêm lớp API theo nhu cầu; chưa có quyết định framework/backend trong trao đổi này.

## Hợp đồng dữ liệu khởi đầu — đề xuất

Các tên dưới đây là tên logic đề xuất, chưa phải các bảng đã tồn tại. Có thể tạo view ánh xạ từ `gold.gold_repo_daily_activity` hiện tại.

| Dataset | Grain | Trường cốt lõi |
| --- | --- | --- |
| `repository_daily_metrics` | Một repo/ngày | `repository_id`, `date`, star/fork events, push events, PR/issue metrics, active contributors |
| `repository_metadata` | Một repo/ngày snapshot | ID, tên, language, topics, category, ecosystem, `snapshot_date` |
| `repository_predictions` | Một repo/ngày dự đoán/horizon/model version | `repository_id`, `prediction_date`, `horizon_days`, prediction/score, `model_version` |

Trước khi coi contract hoàn tất, cần chốt:

- Tên cột, kiểu dữ liệu, nullability và khóa duy nhất.
- Ngày/giờ theo UTC; cách chuyển timezone khi hiển thị.
- Event date, ingestion time và prediction date là các khái niệm riêng.
- Stars gained là số star events, total stars hiện tại hay net growth; không dùng lẫn.
- Active contributor gồm loại event nào; cách xử lý bot, anonymous và actor ID thiếu.
- Ngày không activity có dòng zero hay không; ngày thiếu ingestion phải có trạng thái riêng.
- Daily rows là provisional hay complete; độ trễ và lịch cập nhật.
- Snapshot selection theo thời điểm để tránh leakage trong ML.
- Cách publish predictions, bên chịu trách nhiệm ghi bảng và quyền truy cập.
- Version schema và quy trình thay đổi: thêm trường optional trước; thay đổi phá vỡ cần phối hợp migration.

## Cách làm độc lập

1. DE và ứng dụng cùng viết contract nhỏ cho daily metrics và metadata.
2. Tạo fixture gồm nhiều repo/ngày, có zero activity, missing metadata, bot và ngày thiếu dữ liệu.
3. Ứng dụng tách lớp truy xuất dữ liệu khỏi UI và logic tính toán; chuyển fixture → ClickHouse/API qua cấu hình.
4. DE bàn giao sample thật sớm, không chờ hoàn tất toàn pipeline.
5. So sánh output thật với contract và fixture; cập nhật hai phía có chủ đích.
6. Tách rõ dữ liệu demo và prediction thật trên giao diện.

Không nên hardcode frontend theo raw payload hoặc âm thầm thay metric để khớp biểu đồ.

## Các mốc bàn giao

| Mốc | DE bàn giao | Ứng dụng/ML thực hiện | Gate tích hợp |
| --- | --- | --- | --- |
| 1 | Contract và sample nhỏ | UI, data access, charts | Đọc đúng schema, có empty/error states |
| 2 | Một ngày thật đủ 24 giờ, đã kiểm tra | Kết nối serving, mapping | Counts và metrics khớp truy vấn kiểm chứng |
| 3 | Nhiều tuần liên tục | Rolling growth, feature builder | Phân biệt zero với missing; xử lý lookback đúng |
| 4 | Lịch sử đủ feature/label/evaluation | Baseline và time-based evaluation | Không leakage, có báo cáo baseline |
| 5 | Feature/prediction jobs chạy theo lịch | Prediction views, freshness/version | Output truy vết được và có trạng thái stale |

Các mốc là dependency gates, không phải lịch ngày đã cam kết. Chưa có thông tin về deadline hoặc nguồn lực để ước lượng thời gian chính xác.
