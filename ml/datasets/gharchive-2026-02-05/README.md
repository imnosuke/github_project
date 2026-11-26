# GH Archive — holdout ML-03 đến 05/02/2026 UTC

Bộ dữ liệu gồm **89 ngày, 2.136 giờ và 241.380 dòng sự kiện lưu theo giờ** cho 20 repository. Khoảng thu thập từ `2025-11-09` đến `2026-02-05` UTC. Cả 89 ngày đủ giờ và vẫn mang trạng thái `provisional` theo APP-02 do thiếu cờ merge cho một phần PR close.

| Đường dẫn | Nội dung |
| --- | --- |
| [`snapshot/`](snapshot/) | Manifest và bốn bảng APP-02 từ lượt crawl. |
| [`days/`](days/) | Parquet theo giờ, checkpoint checksum, báo cáo chất lượng và dữ liệu tổng hợp từng ngày. |
| [`scope.json`](scope.json), [`coverage.json`](coverage.json) | Phạm vi repo theo GitHub ID và độ phủ từng ngày. |
| [`evaluation/`](evaluation/) | Hai model đã khóa, manifest holdout, 600 mẫu, dự đoán hồi cứu và kết quả chấm điểm. |
| [`de-evidence/`](de-evidence/) | Kết quả pipeline, APP-10/11 và quan sát reader trên môi trường thử nghiệm local. Các lượt kiểm thử pipeline dùng cửa sổ đối soát riêng. |

## Payload và checksum

Parquet theo giờ giữ các trường sự kiện có cấu trúc và giữ trong `payload_json` các trường dùng cho phép tính hoặc định danh PR/issue. Payload văn bản tự do như nội dung mô tả, tiêu đề, bình luận và URL đã được loại khỏi bản xuất. Những action ngoài danh sách chuẩn được lưu thành `other` khi nguồn có action. Mình đã đối chiếu lại các metric và thống kê lỗi theo từng repo/ngày với dữ liệu nguồn trước khi xuất.

Checkpoint đặt `parquet_sha256` theo file trong repo và lưu `source_parquet_sha256` theo file trước khi thu gọn payload. Manifest khóa evaluation giữ checksum của các manifest ngày tại thời điểm audit nguồn. [`export-manifest.json`](export-manifest.json) liên kết cửa sổ, checksum snapshot và checksum các artifact đánh giá. Các bảng snapshot và artifact đánh giá được sao chép nguyên byte.

Các điểm số là hồi cứu theo ngày sự kiện. Dữ liệu giữ nguyên `NULL` khi thiếu bằng chứng xác định PR merge. Hồ sơ Gold và availability trước `decision_at` cần cho nghiệm thu ML chính thức.
