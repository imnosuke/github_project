# ML-04 — Dự thảo contract dự đoán star events

Trạng thái **dự thảo**, chờ nghiệm thu ML-03 trên Gold và thống nhất publication, SLA, quyền đọc với DE.

## Một dòng dự đoán

Grain là một repo và một anchor trong mỗi publication dự đoán. Khóa duy nhất `(prediction_publication_id, repository_id, anchor_date)`. Một publication chốt một phiên bản model và một publication đầu vào. Repo lấy từ registry có hiệu lực tại anchor.

| Trường | Kiểu | Quy tắc |
| --- | --- | --- |
| `prediction_publication_id`, `input_publication_id` | string | ID của batch đã publish và dữ liệu dùng để tính feature |
| `repository_id` | int64 | ID repo dương trong registry |
| `anchor_date` | date | Ngày cuối lookback, tính theo UTC |
| `horizon_days` | int | `30`. Dự đoán tổng `star_events` từ anchor + 1 đến anchor + 30, gồm cả hai đầu |
| `decision_at`, `generated_at` | timestamp UTC | Thời điểm chốt input và thời điểm ghi kết quả. Publication đầu vào phải khả dụng tại `decision_at`. `generated_at >= decision_at` |
| `model_id`, `feature_schema_id` | string | Phiên bản bất biến của model và schema feature, truy được về ML-03 artifacts |
| `status` | enum | `ready`, `insufficient_history`, `incomplete_features` |
| `predicted_star_events` | float64 nullable | Hữu hạn và không âm khi `ready`. `null` ở hai trạng thái thiếu dữ liệu. `0` là dự đoán hợp lệ |

Tính feature từ `[anchor_date-29, anchor_date]`. Batch inference chỉ cần lookback đã qua quality gate. Dữ liệu vào sau anchor nằm ngoài cửa sổ feature. Nếu batch chạy muộn, UI vẫn hiển thị ngày bắt đầu và kết thúc của horizon theo anchor cùng giờ tạo. [Đặc tả thời gian ML-01](ML-01-problem-and-evaluation.md#2-ngày-dữ-liệu-và-thời-điểm-thông-tin-sẵn-sàng)

## Batch và hiển thị

- Khóa chạy logic gồm anchor, input publication, model version và feature schema. Retry cùng khóa tái sử dụng lần chạy đã commit. Khi đổi input hoặc model, tạo publication mới với ID riêng.
- Batch ghi vào vùng staging, kiểm tra schema, repo coverage, khóa trùng, giá trị và provenance rồi mới chuyển con trỏ publication. Batch lỗi giữ publication hợp lệ trước đó và ghi trạng thái lỗi ở cấp batch.
- Explorer và Growth đọc publication đang phục vụ, hiển thị horizon, anchor và giờ cập nhật. Khi thiếu publication hoặc thiếu feature, hiển thị đúng lý do. Khi quá SLA đã chốt, gắn nhãn stale dựa trên anchor và thời gian publish.
- Artifact hồi cứu chỉ dùng trong đánh giá offline. Bật serving sau khi có model đã nghiệm thu, input Gold đối soát và SLA cùng cơ chế publish được DE thống nhất.

## Điều kiện chọn model và mở luồng batch

Chốt phạm vi ban đầu ở 20 repo đã đánh giá hồi cứu. Persistence 30 ngày là baseline bắt buộc để đối chiếu. Phiên bản model được đưa vào batch phải tham chiếu lượt nghiệm thu ML-03 trên Gold và checksum artifact. Khoảng test hồi cứu 2025-09-10 đến 2025-10-09 đã dùng để chấm điểm. Khi xem xét lựa chọn Ridge, khóa một holdout mới trước khi xem điểm của nó.

Producer công bố danh sách repo thuộc scope của anchor, kết quả cho từng repo và manifest theo cùng một batch ID. App chỉ đọc batch đã commit, xem kết quả có thuộc anchor đang chọn, giữ trạng thái thiếu feature và dùng timestamp công bố để đánh giá freshness. SLA chạy và thời gian giữ publication cần được chốt khi DE đo staging. Phần triển khai batch chờ model và publication Gold đã nghiệm thu.

## Chạy thử offline với fixture

Dùng `python -m ml.batch_fixture --fixture PATH --run MODEL_RUN_DIR --anchor YYYY-MM-DD --decision-at UTC_TIMESTAMP --output PATH` với lần train fixture có `run.json` và `model.json`. Batch kiểm tra loại nguồn, schema feature và checksum của model. File JSON đã commit có ID ổn định theo khóa batch. Retry trả lại kết quả đã commit. Lỗi ghi hoặc công bố giữ nguyên các file đã commit trước đó. Batch fixture nằm ngoài luồng serving.

Để khóa holdout ML-03, dùng `python -m ml.holdout_plan --coverage-start DATE --complete-through DATE --publication-id ID --output FILE` sau khi xác minh coverage liền mạch. Công cụ chỉ dùng metadata độ phủ. Holdout đã chấm gần nhất kết thúc ở anchor `2026-01-06` với nhãn đến `2026-02-05`. Một cửa sổ hồi cứu kế tiếp bắt đầu sớm nhất ở anchor `2026-03-07` và cần dữ liệu hoàn chỉnh đến `2026-05-05` UTC. Nghiệm thu theo thời điểm dự đoán còn cần bằng chứng availability tương ứng. Chỉ ghi file khóa khi đủ độ phủ.

## Luồng ClickHouse sau khi model được nghiệm thu

Chạy [DDL ML-04](ml-04-serving-schema.sql) trong database `app_serving`. Cấp SELECT trên hai bảng prediction cho app reader. Cấp SELECT và INSERT cho tài khoản writer riêng qua `ML04_CLICKHOUSE_*`, với cùng quy ước host, port, TLS và database như `APP_CLICKHOUSE_*`. Dùng một writer tuần tự cho mỗi môi trường.

Lệnh `python -m ml.live_batch --release RELEASE_JSON --model MODEL_JSON --observations PATH --source-name NAME` đọc Gold bằng `APP_CLICKHOUSE_*`. `MODEL_JSON` phải đi kèm `run.json` ghi lượt train đã hoàn thành với nguồn `live`. Release JSON chứa `status: approved`, `release_id`, `approved_at` UTC, `model_sha256`, danh sách `repository_ids` gồm 20 ID, và `ml03_acceptance` với `gold_training_run_sha256` cùng các tham chiếu `gold_reconciliation`, `contract_confirmation`, `prospective_evaluation`. Người duyệt ML-03 xác nhận các tham chiếu từ hồ sơ nghiệm thu trước khi phát hành release. Job kiểm tra checksum của cả model và báo cáo train.

Lệnh ghi nhận lần đọc input thực tế, lấy anchor là ngày UTC trước ngày chạy, tạo kết quả cho registry đã duyệt và ghi manifest sau khi đọc lại đủ rows. Chạy lại cùng release, anchor, model và publication Gold trả cùng publication dự đoán. Mỗi lần thử trước commit dùng staging ID mới. Bản công bố trước đó vẫn đọc được khi lần ghi mới lỗi.

Để bật Explorer và Growth, đặt `APP_ENABLE_PREDICTIONS=1`, `APP_PREDICTION_RELEASE_ID` đúng release ID đã duyệt và `APP_PREDICTION_MAX_AGE_HOURS` theo SLA. UI đọc đúng anchor đang chọn, hiển thị horizon và thời điểm cập nhật. Ngày thiếu batch, repo thiếu feature, lỗi nguồn và batch quá hạn có thông báo riêng. Giá trị dự đoán quá hạn được ẩn.
