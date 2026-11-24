# Local ML — Hướng dẫn Tải Dữ liệu (~500 MB) & Huấn luyện Model

- Đặc tả bài toán & đánh giá: [ML-01](../docs/app-ml/ML-01-problem-and-evaluation.md)
- Thiết kế Feature Builder & Training CLI: [ML-02](../docs/app-ml/ML-02-feature-and-training.md)
- Kiểm tra mức độ sẵn sàng dữ liệu (Readiness Audit): [ML-03 audit](../docs/app-ml/ML-03-readiness-audit.md)

---

## 1. Cài đặt môi trường

Cài đặt các thư viện trong `ml/requirements.txt` (tách biệt với môi trường Airflow):

```bash
python -m pip install -r ml/requirements.txt
```

Chạy kiểm thử tự động từ thư mục gốc `final_project`:

```bash
python -m pytest ml/tests -q
```

---

## 2. Quy trình chuẩn bị ~500 MB dữ liệu trên ổ cứng & Huấn luyện Model

Contract `ML-01` và `ML-03` yêu cầu chuỗi thời gian liên tục tối thiểu **239 ngày** (lookback 30 ngày + train 60 ngày + purge 30 ngày + validation 30 ngày + purge 30 ngày + test 30 ngày + horizon nhãn 30 ngày). Để tải nhiều file sự kiện GitHub thật từ GH Archive đạt ngưỡng **~500 MB Parquet (32 files)** kết hợp cùng chuỗi lịch sử 320 ngày cho 150 repositories, thực hiện 3 bước sau:

### Bước 1: Stream hàng loạt file từ GH Archive sang Parquet (~518 MB / 32 files)
Chạy script `gharchive_extractor.py` với chế độ `--stream` (giải nén trực tiếp từ luồng HTTP sang Parquet mà không cần tải cả file `.json.gz` 150 MB về đĩa) và `--target-total-mb 500`:

```bash
python airflow/scripts/gharchive_extractor.py \
  --date 2025-01-01 \
  --end-date 2025-01-25 \
  --hours-step 6 \
  --max-records 24000 \
  --target-total-mb 500 \
  --skip-existing \
  --stream \
  --local-only \
  --output-dir ./airflow/data
```
* Thư mục đầu ra: `airflow/data/parquet/` gồm **32 file Parquet** (**518.17 MB**, ~766.000 events).

### Bước 2: Tạo bộ dữ liệu huấn luyện chuẩn Contract v1 (150 Repos × 320 Ngày)
Kết hợp toàn bộ 32 file Parquet vừa tải tại `./airflow/data/parquet` vào chuỗi lịch sử 320 ngày của 150 repositories:

```bash
python -m ml.fetch_github_data \
  --output ml/runs/github_pc_fixture \
  --repos 150 \
  --days 320 \
  --local-parquet-dir ./airflow/data/parquet
```
*(Thêm `--no-github-api` nếu muốn chạy offline không gọi GitHub REST API).*
* Tạo ra **46.425 dòng daily metrics** trong `ml/runs/github_pc_fixture/`.

### Bước 3: Chạy Audit, Build Features (28 đặc trưng), Train & Evaluate
```bash
# 1. Audit kiểm tra các cổng dữ liệu (Data checks: passed)
python -m ml.cli audit \
  --config ml/configs/smoke.json \
  --fixture-dir ml/runs/github_pc_fixture \
  --output ml/runs/github_pc_audit

# 2. Tạo 26.445 mẫu huấn luyện & kiểm thử (28 features + nhãn star_events 30 ngày tới)
python -m ml.cli build \
  --config ml/configs/smoke.json \
  --fixture-dir ml/runs/github_pc_fixture \
  --output ml/runs/github_pc_dataset

# 3. Huấn luyện mô hình (so sánh Persistence-30d, Zero baseline và Ridge Regression)
python -m ml.cli train \
  --config ml/configs/smoke.json \
  --dataset ml/runs/github_pc_dataset \
  --output ml/runs/github_pc_model

# 4. Đánh giá lại độc lập trên tập Test và xuất báo cáo MAE/RMSE
python -m ml.cli evaluate \
  --dataset ml/runs/github_pc_dataset \
  --run ml/runs/github_pc_model \
  --output ml/runs/github_pc_eval
```

---

## 3. Tóm tắt kết quả & Dung lượng ổ cứng

- **Tổng dung lượng trên đĩa:** **~519.05 MB** (`airflow/data/parquet`: ~518.17 MB qua 32 files + `ml/runs`: ~0.88 MB).
- **Số lượng mẫu học có giám sát (`kept`):** **26.445 mẫu**
  - Tập `train`: **17.446 mẫu** (143 repositories × 122 anchor dates)
  - Tập `validation`: **4.576 mẫu** (143 repositories × 32 anchor dates)
  - Tập `test`: **4.423 mẫu** (150 repositories × 30 anchor dates, bao gồm 7 unseen repositories mới xuất hiện)
- **Các file kết quả chính:**
  - Báo cáo kiểm tra dữ liệu: `ml/runs/github_pc_audit/readiness.md`
  - Tập đặc trưng & nhãn: `ml/runs/github_pc_dataset/samples.parquet`
  - Trọng số mô hình & báo cáo huấn luyện: `ml/runs/github_pc_model/model.json`, `ml/runs/github_pc_model/run.json`
  - Dự đoán trên tập Test: `ml/runs/github_pc_model/test_predictions.parquet`
