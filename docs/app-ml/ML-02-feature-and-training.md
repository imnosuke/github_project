# ML-02 — Feature builder và training skeleton

Ngày: 14/11/2026. Trạng thái: **hoàn tất local trên fixture**, theo `ml-stars-30d-v1` ở [ML-01](ML-01-problem-and-evaluation.md). Chưa có dữ liệu Gold hoặc model được đánh giá trên lịch sử thật; ML-03 chưa hoàn tất.

## Luồng và phạm vi

`ml/data.py` nạp dữ liệu qua public adapter: publication, date bounds, **registry_history()**, day status và time series. Phương thức registry mới trả tất cả intervals, không lấy registry hiện tại từ catalog để suy diễn quá khứ. ML không đọc `adapter.tables` hoặc envelope và không thay đổi UI/pipeline DE.

Inputs được copy/validate: schema cột bắt buộc, date ISO, UTC publication, keys unique, IDs/counts int64 không âm, scope không chồng lấn, quality/file gates của ngày complete, null policy và invariants counts. Publication phải giữ nguyên trước/sau lần đọc. Thiếu ngày/status/daily row vẫn là unknown và loại các mẫu liên quan; không tự densify thành zero. Các lần đọc phải thuộc một publication theo contract adapter; việc so envelope không thay thế snapshot isolation phía serving live.

`ml/features.py` tạo **28 numeric features**: event sums 7/30 ngày, active days và mean/max daily actor counts, đúng ML-01. Core không có commits optional, active_contributors, ID/name hoặc metadata. **Không join metadata trong v1**, theo quyết định ML-01; không dùng latest snapshot làm feature lịch sử. Khi bổ sung metadata sau này phải có availability/as-of join và tests riêng trước đổi schema.

`feature_row()` chỉ đọc `[T-29,T]`; `label()` đọc `[T+1,T+30]` riêng. `--features-only` chạy được đến ngày complete cuối mà không cần future label; chưa phải batch inference/publish của ML-04. Supervised dataset chỉ giữ samples qua eligibility và train/validation/test split; feature-only dataset bị từ chối khi đưa vào trainer.

## Eligibility và audit

Một audit row cho mỗi repo/anchor trong config, với một reason theo thứ tự kiểm tra:

1. Feature gate: out_of_scope tại T; insufficient_history nếu lookback trước bounds/first scope; out_of_scope nếu có scope gap; incomplete_features nếu ngày/status/metrics thiếu hoặc chưa complete.
2. Label gate (chỉ supervised): unmatured_label nếu label end sau input upper bound; out_of_scope nếu không thuộc scope suốt horizon; incomplete_label nếu cửa sổ thiếu/chưa complete.
3. Calendar split: purged hoặc outside; còn lại kept.

Mỗi row chỉ có lý do đầu tiên, không cộng nhiều lý do cho cùng một candidate. Dữ liệu malformed/duplicate/count âm hoặc required complete-day null làm dừng input validation. Audit không phải cơ chế bỏ qua lỗi schema. Với samples kept, split theo ML-01 và giữ label_end trước ngày đầu tập tiếp theo.

## Training và artifacts

`ml/training.py` có persistence-30d, zero và một model ridge tuyến tính. Ridge chuẩn hóa bằng mean/std **chỉ của train**, thay std zero bằng 1, fit intercept bằng mean label train và coefficients qua least squares với L2 penalty `ridge_alpha` (không phạt intercept). Không có random split hoặc random fitting; alpha do config chốt trước, chưa có hyperparameter search. Feature/schema giống nhau cho toàn bộ tập.

Chọn model theo validation MAE, giữ persistence khi hòa; zero rồi ridge chỉ thay lựa chọn khi MAE thấp hơn rõ ràng (tolerance tuyệt đối 1e-12). Test chỉ được score sau khi chốt lựa chọn; không refit validation. Prediction âm được clamp zero, không làm tròn; NaN/inf hoặc thiếu prediction gây lỗi.

Report có MAE/RMSE/macro-MAE trên original scale; scores theo anchor, zero/nonzero lookback **total_events**, repo seen/unseen trong train, delta/relative improvement so persistence. Baseline MAE zero thì relative improvement null. Sensitivity report dùng lịch 30 ngày cố định với origin **1970-01-01 UTC**; nếu tập không có anchor phù hợp thì null, không chọn offset khác để làm đẹp điểm. Đây là descriptive smoke metrics, không có confidence interval hoặc tuyên bố chất lượng model.

Output directories phải **chưa tồn tại**; không overwrite run/dataset cũ. Mỗi dataset có:

- `samples.parquet`: keys, split, 28 features và target (trừ features-only).
- `audit.parquet`: keys/split/reason cho mọi candidate.
- `manifest.json`: spec/artifact version, feature schema, config, publication, input bounds/fingerprint, counts, checksums hai Parquet files và cảnh báo synthetic/retrospective.

Mỗi completed run có `run.json`, `model.json` (JSON có thể reload, không dùng pickle), `test_predictions.parquet`. Run ghi config, dataset manifest hash, input fingerprint/publication, feature schema, model hash và Python/NumPy/pandas/PyArrow versions. `evaluate` chỉ replay đúng dataset/model đã ghi, kiểm tra hashes/schema và xuất `evaluation.json`; không phải đánh giá model tùy ý trên serving mới.

Nếu bất kỳ split train/validation/test rỗng, trainer ghi `run.json` với `status=blocked`, `empty_splits`, trả **exit code 2**, không tạo model/predictions. Không giảm purge hoặc fallback random split. Gate số ngày và khảo sát lịch sử thật của ML-03 vẫn chưa được nghiệm thu; skeleton chỉ chứng minh đường chạy local với các split không rỗng.

## Môi trường và lệnh chạy

Chạy từ repository root. Môi trường ML tách khỏi Airflow; có thể dùng môi trường ứng dụng hiện tại nếu đã có đủ dependencies trong `ml/requirements.txt`.

```bash
python3 -m venv .venv-ml
.venv-ml/bin/python -m pip install -r ml/requirements.txt
```

Các lệnh dưới dùng `python3`; thay bằng `.venv-ml/bin/python` nếu dùng venv vừa tạo. Chọn các output paths mới cho mỗi lần chạy.

Fixture ứng dụng hiện có — kiểm tra dataset và trường hợp thiếu split:

```bash
python3 -m ml.cli build --config ml/configs/app_fixture.json \
  --output /tmp/ml02-app-dataset
python3 -m ml.cli train --config ml/configs/app_fixture.json \
  --dataset /tmp/ml02-app-dataset --output /tmp/ml02-app-run
```

Train ở ví dụ này **dự kiến exit 2 / blocked**. Dataset có 570 candidates, 5 kept validation rows, 95 purged; 100 label-eligible pairs trước purge khớp audit ML-01. Đây là hệ quả dữ liệu ứng dụng chỉ có 95 ngày, không phải lỗi trainer.

Smoke test toàn luồng — sinh fixture dài riêng, không sửa fixture ứng dụng:

```bash
python3 -m ml.generate_fixture --output /tmp/ml02-smoke-fixture
python3 -m ml.cli build --config ml/configs/smoke.json \
  --fixture-dir /tmp/ml02-smoke-fixture --output /tmp/ml02-smoke-dataset
python3 -m ml.cli train --config ml/configs/smoke.json \
  --dataset /tmp/ml02-smoke-dataset --output /tmp/ml02-smoke-run
python3 -m ml.cli evaluate --dataset /tmp/ml02-smoke-dataset \
  --run /tmp/ml02-smoke-run --output /tmp/ml02-smoke-evaluation
```

Generator tạo 320 ngày synthetic 2025-01-01…2025-11-16; có repo quiet/short-history, ngày missing và provisional, metadata rỗng. Config giữ 708 supervised rows: 380 train, 160 validation, 168 test, với purge đúng 30 ngày trước mỗi boundary. Repo 2106 thiếu training history được báo cáo là unseen ở test. Dữ liệu này được thiết kế để kiểm tra luồng, **không chứng minh chất lượng dự đoán hoặc thay lịch sử thật**.

Feature-only dataset:

```bash
python3 -m ml.cli build --config ml/configs/app_fixture.json \
  --features-only --output /tmp/ml02-features-only
```

## Kiểm chứng và giới hạn

```bash
python3 -m pytest ml/tests apps/streamlit/tests -q
git diff --check
```

Tests bao gồm expected feature/label values, thay activity sau T chỉ đổi label không đổi features, feature generation không cần future rows; zero/missing/provisional/null/schema; scope gaps/ended intervals; publication change; train-only scaling, test-label mutation không đổi model/selection; ties/zero baseline/invalid prediction; CLI blocked case; full build/train/reload/evaluate; cùng input/config/environment tạo các artifacts có checksum giống nhau; file đã sửa bị từ chối khi checksum không khớp.

Review trước bàn giao: Gemini 3.8 Flash không phát hiện lỗi chức năng; Codex review lần 2 xác nhận adapter thiếu cột có thể bị `reindex()` tạo thành null, làm lọt trường hợp thiếu optional metrics. Đã thay bằng kiểm tra field presence trước khi chọn columns và thêm regression tests cho thiếu `commits_pushed`, `active_contributors`, `star_events`. Nullable không đồng nghĩa với được bỏ tên cột.

Kết quả kiểm tra sau sửa ngày 14/11/2026: **110 passed in 9.82s** (66 tests ML và 44 tests ứng dụng), `git diff --check` sạch. Các CLI build/train/evaluate cũng đã được chạy trực tiếp thành công trên fixture dài; fixture ứng dụng trả blocked như dự kiến. Hai vòng review kiểm tra code local, không chứng nhận model quality trên dữ liệu thật.

Tính tái lập bitwise đã kiểm tra trong cùng môi trường. Không cam kết bitwise qua phiên bản NumPy/BLAS/PyArrow khác nhau. Chưa có Gold connection, khảo sát dữ liệu thật, historical publication availability, metadata features, hyperparameter search, model serving hoặc prediction publish. ML-03/04 vẫn giữ gate riêng.
