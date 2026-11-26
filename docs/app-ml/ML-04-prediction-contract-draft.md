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

## Chạy thử offline với fixture

Dùng `python -m ml.batch_fixture --fixture PATH --run MODEL_RUN_DIR --anchor YYYY-MM-DD --decision-at UTC_TIMESTAMP --output PATH` với lần train fixture có `run.json` và `model.json`. Batch kiểm tra loại nguồn, schema feature và checksum của model. File JSON đã commit có ID ổn định theo khóa batch. Retry trả lại kết quả đã commit. Lỗi ghi hoặc công bố giữ nguyên các file đã commit trước đó. Batch fixture nằm ngoài luồng serving.

Để khóa holdout ML-03, dùng `python -m ml.holdout_plan --coverage-start DATE --complete-through DATE --publication-id ID --output FILE` sau khi xác minh coverage liền mạch. Công cụ chỉ dùng metadata độ phủ, không đọc nhãn hoặc điểm. Với lịch sử đã chấm hiện tại, anchor sớm nhất là 2025-12-08 và 30 anchor cần dữ liệu hoàn chỉnh đến 2026-02-05 UTC. Chỉ ghi file khóa khi đủ độ phủ.
