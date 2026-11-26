# ML-03 — Kết quả hồi cứu trên GH Archive

Ngày thực hiện 25/11/2026. Phạm vi 20 repo, từ 2025-01-01 đến 2025-11-16 UTC. Lần chạy đánh giá theo ngày sự kiện trên snapshot đã crawl. Việc đối soát Gold và xác minh dữ liệu có sẵn tại thời điểm dự đoán vẫn đang chờ DE.

## Xác minh dữ liệu và khóa lịch

- Kiểm tra checksum của snapshot, sau đó đọc lại 840 Parquet theo giờ trên 35 ngày `provisional` có đủ 24 giờ. Đối soát số dòng, phạm vi, ngày UTC, event ID, dedup và các trường dùng trong đánh giá với manifest.
- Xác nhận 16 cặp repo/ngày có số liệu star đang trống và có **0 sự kiện** trong cả 24 giờ. Chỉ dùng các giá trị này trong lần đánh giá hồi cứu. Status APP-02 và số liệu PR trong snapshot tiếp tục theo contract.
- Loại 600 mẫu có cửa sổ đi qua ngày 2025-06-12, ngày còn thiếu hai file giờ. Bộ feature hồi cứu có 26 cột, bỏ hai tổng PR merge 7/30 ngày. Lookback, horizon và hai khoảng purge giữ nguyên 30 ngày.
- Mốc chia tập đã khóa trước khi chấm điểm. Train gồm 103 ngày từ 2025-01-30 đến 2025-05-12, có 2.060 mẫu. Validation gồm 30 ngày từ 2025-07-12 đến 2025-08-10, có 600 mẫu. Test gồm 30 ngày từ 2025-09-10 đến 2025-10-09, có 600 mẫu. Mỗi ngày đánh giá có đủ 20 repo.

## Đánh giá

| Phương án | MAE validation | MAE test | RMSE test |
| --- | ---: | ---: | ---: |
| Persistence 30 ngày | **40,43** | 107,95 | 139,15 |
| Ridge, alpha = 1 | 49,78 | **84,88** | **109,56** |
| Dự đoán 0 | 313,77 | 197,74 | 245,86 |

Chọn **persistence** theo MAE validation trước khi mở test. Ridge có lỗi thấp hơn trên holdout này. Đánh giá thêm một giai đoạn chưa chấm điểm nếu muốn kiểm tra liệu lợi thế đó có lặp lại. Các mẫu liên tiếp có nhãn 30 ngày chồng lấn, nên kết quả trên một holdout mang tính mô tả.

Kết quả chạy local nằm trong `ml/runs/ml03-retrospective-20261125/`. `frozen.json` lưu cấu hình, kiểm tra nguồn và checksum mẫu. `metrics.json` lưu số liệu theo ngày, nhóm repo đã thấy trong train và nhóm activity. `model.json` lưu model được chọn. `holdout_predictions.parquet` lưu kết quả chấm điểm offline. Script `run.py` đi kèm lần chạy, dùng hai bước `prepare` và `evaluate` trong một thư mục run mới để tái lập.

## APP-07 và ML-04

Streamlit AppTest đã chạy qua Overview, Repository Explorer và Growth Analytics trên snapshot 20 repo. Dùng ngày 2025-10-12 UTC làm mốc Growth để có đủ lịch sử cho kỳ hiện tại và kỳ trước. Chọn 12–13/10 để kiểm tra cảnh báo ngày provisional và việc ẩn KPI toàn kỳ. Báo cáo kiểm tra nằm trong `app07-demo.json`.

```powershell
$env:APP_DATA_SOURCE = 'snapshot'
$env:APP_SNAPSHOT_DIR = (Resolve-Path 'airflow/data/ml-gharchive-2025/snapshot-repaired-20261125-012524').Path
python -m streamlit run apps/streamlit/app.py
```

APP-07 live cần DE build lại Silver/Gold và ghi kết quả đối soát. ML-04 đã có [dự thảo contract dự đoán](ML-04-prediction-contract-draft.md) để review trước khi triển khai serving.

## Holdout thứ hai

Đợt đánh giá thứ hai dùng 30 anchor từ `2025-12-08` đến `2026-01-06`, với 600 mẫu trên 20 repo. Cửa sổ ảnh hưởng từ `2025-11-09` đến `2026-02-05` có đủ 2.136 giờ. Hai model được cố định từ 2.060 mẫu train của lượt trước. Giữ 26 feature hồi cứu và bỏ hai tổng PR merge vì chưa xác định được cờ merge cho một phần nguồn.

| Model | MAE | RMSE |
| --- | ---: | ---: |
| Persistence 30 ngày | **28,07** | **39,88** |
| Ridge, alpha = 1 | 53,79 | 75,57 |

Persistence có MAE thấp hơn ở cả 30 anchor. Giữ persistence làm baseline cho bước tiếp theo. Lượt đánh giá thuộc chế độ hồi cứu theo ngày sự kiện. Nghiệm thu trên Gold và xác minh availability tại thời điểm dự đoán vẫn là điều kiện cho ML-04. [Snapshot, bản khóa và kết quả chi tiết](../../ml/datasets/gharchive-2026-02-05/README.md)
