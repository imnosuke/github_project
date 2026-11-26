# ML-03 — Chuẩn bị audit dữ liệu

Ngày: 14/11/2026. Trạng thái: **audit local đã có; ML-03 trên Gold chưa nghiệm thu**.

## Contract hiện tại

[APP-02](APP-02-data-contract-v1.md) vẫn là `1.0.0-draft`, hoàn tất phía ứng dụng và **chờ DE xác nhận**. Scope/schema đang được dùng cho fixture không phải bằng chứng hai phía đã chốt hoặc Gold đã đáp ứng. ML-01/02 đã chốt phần bài toán và triển khai local; không thay thế xác nhận data contract.

Cần ghi nhận xác nhận của DE với version/tài liệu cụ thể, người xác nhận, ngày và reference biên bản/issue/PR: schema/types/grain, registry history, metric semantics/actor IDs/bot handling, sparse → dense, completeness/quality gates, serving mapping/read-only và publication consistency, refresh/SLA, metadata availability. Không điền trạng thái approved khi chưa có bằng chứng này.

## Cách dùng

Chạy từ repository root bằng môi trường ML-02 (`ml/requirements.txt`). Audit chỉ đọc input và ghi output vào **thư mục mới**; không train/tune, không đổi split, không ghi dữ liệu pipeline. Không thay hành vi trainer ML-02 hoặc tự tạo model.

```bash
python3 -m ml.cli audit --config ml/configs/app_fixture.json \
  --output /tmp/ml03-audit-app
```

Fixture dài riêng cho kiểm tra các gate:

```bash
python3 -m ml.generate_fixture --output /tmp/ml03-audit-smoke-fixture
python3 -m ml.cli audit --config ml/configs/smoke.json \
  --fixture-dir /tmp/ml03-audit-smoke-fixture --output /tmp/ml03-audit-smoke
```

**Exit code 2 là dự kiến khi readiness còn blocked**, kể cả các kiểm tra dữ liệu đã chạy thành công. Output vẫn có báo cáo để xem lý do. Các lệnh hiện tại không thể tự xác nhận external evidence; `ready_for_ml03` luôn false trong phiên bản chuẩn bị này. Đừng dùng exit 2 để kết luận audit bị crash hoặc tự giảm purge để chuyển thành pass.

Với snapshot backfill GH Archive, dùng `--source snapshot --snapshot-dir <thư-mục-snapshot>` cùng config và output. Audit kiểm tra lịch sử theo thời điểm sự kiện và giữ trạng thái overall `blocked` cho tới khi có bằng chứng về Gold và thời điểm dữ liệu đã sẵn sàng. Snapshot có nguồn riêng trong report để phân biệt với fixture tổng hợp.

Trong khi backfill đang chạy, có thể tạo features ngoài mẫu từ snapshot đã xuất và kiểm tra điều kiện train bằng cùng cấu hình thời gian.

```powershell
python -m ml.cli build --snapshot-dir <snapshot> --config ml/configs/smoke.json --features-only --output ml/runs/ml03-features
python -m ml.cli build --snapshot-dir <snapshot> --config ml/configs/smoke.json --output ml/runs/ml03-dataset
python -m ml.cli train --dataset ml/runs/ml03-dataset --config ml/configs/smoke.json --output ml/runs/ml03-train
```

Với snapshot, train ghi báo cáo `blocked` nếu các kiểm tra lịch và số anchor chưa đạt. Khi qua các kiểm tra đó, model và test metrics vẫn mang nhãn đánh giá hồi cứu đến khi Gold và lịch sử publication được xác minh.

Chuẩn bị chọn nguồn thật:

```bash
python3 -m ml.cli audit --config ml/configs/smoke.json \
  --source clickhouse --output /tmp/ml03-audit-gold
```

Kết nối dùng cấu hình server-side APP-07. Đặt `APP_CLICKHOUSE_DATABASE=app_serving` để đọc publication theo APP-02. Khi endpoint không khả dụng hoặc chưa có publication, audit ghi `source_unavailable`. Khi publication sai schema hoặc thiếu coverage, audit báo lỗi input. Audit luôn kiểm tra thêm các gate về đối soát Gold và thời điểm khả dụng. Các gate này cần bằng chứng từ môi trường DE.

## Kiểm tra tự động và cách đọc kết quả

Audit tái sử dụng `Inputs` validation và `build_dataset()` của ML-02, nên cùng định nghĩa count/null/scope/completeness và purge. Dữ liệu malformed làm dừng validation, không thành zero hoặc bị bỏ qua để làm đẹp coverage.

- Calendar span ít nhất **239 ngày** theo bố cục tối thiểu ML-01 (lookback 30, train/validation/test 60/30/30, hai purge 30, label horizon 30). Đây là raw calendar span, không có nghĩa mọi ngày complete hoặc đủ thống kê.
- Input bounds phải phủ từ `train_start-29` đến `test_end+30` của config đã chọn. Các ngày thiếu bên trong vẫn được xét bằng eligibility, không suy ra đủ dữ liệu chỉ từ min/max.
- Sau eligibility/purge, tối thiểu **60/30/30 distinct anchor dates** tương ứng train/validation/test, tính toàn dataset. Nhiều repo trong một ngày không thay thế nhiều ngày lịch sử. Coverage từng repo được báo riêng; không áp ngưỡng 60/30/30 cho mọi repo vì ML-01 cho phép repo mới có đủ lookback ở evaluation.
- Coverage theo từng ngày gồm status complete/provisional/missing/**unknown**, số repo thuộc scope, số row có mặt và số row thiếu. Ngày complete với zero activity, row bị thiếu và null metric là các khái niệm riêng. Null counts thống kê trên **observed rows**, không giả rằng missing row chứa zero/null đã quan sát được.
- Report có longest complete run, các khoảng ngày chưa complete, eligibility reasons, counts/bounds theo split, label zero fraction/min/median/p90/max. Tập không có mẫu có label statistics null, không phải zero.

`data_status=passed` chỉ nói các gate dữ liệu/cửa sổ ở trên đã đạt. Overall `status=blocked` vẫn giữ khi source là fixture hoặc thiếu bằng chứng bên ngoài; không phải nghiệm thu ML-03 hay đánh giá model quality. Các ngưỡng được ghi trong report, không tune theo model scores. Config vẫn dùng schema ML-02; `ridge_alpha` được giữ trong provenance nhưng audit không sử dụng để fit.

## Output

- `readiness.json`: machine-readable report, config và hash, spec/audit version, publication/input fingerprint, policy, blockers, data gates, coverage, eligibility, label summary và required external evidence.
- `readiness.md`: báo cáo ngắn cho người review, shortfalls và việc tiếp theo.
- `coverage.parquet`: một ngày một row; unknown không bị forward-fill thành complete.
- `repository_coverage.parquet`: candidates, kept/excluded và distinct anchors theo split của từng repo.
- `eligibility.parquet`: một repo/anchor một primary reason, cùng thứ tự ưu tiên ML-02.

Ba diagnostic Parquet files có checksums trong report. Nếu input invalid hoặc source unavailable, chỉ ghi JSON/Markdown có lỗi; không tạo coverage rỗng/số zero giả. Output đã tồn tại bị từ chối, không overwrite báo cáo cũ. Kết quả có thể tái lập với cùng input/config/code/environment.

## Bằng chứng còn cần trước ML-03

Audit đánh dấu ba mục **unverified**, không có flag tự bật approved:

1. **contract_confirmation:** xác nhận DE cho APP-02 với version/reference cụ thể.
2. **gold_reconciliation:** APP-07 đọc nguồn thật bằng quyền chỉ đọc, đối soát sample ngày/repo, kiểm tra publication/schema/status. Contract/schema pass không thay đối soát số liệu.
3. **historical_availability:** dữ liệu/publication thực sự available ở decision time, hoặc prospective snapshots theo ML-01. Backfill/event date không chứng minh availability lịch sử.

Người phụ trách hai phía cần review evidence và config hash trước khi cố định evaluation boundaries. Công cụ này chưa load/verify các evidence đó; schema hay nguồn gắn nhãn live cũng không tự chứng minh DE đã chấp thuận.

## Kết quả local và giới hạn

Fixture ứng dụng được báo blocked vì thiếu calendar/window/split coverage và source thật; chỉ có 5 validation rows nhưng thuộc **1 anchor date**, chưa đạt 30 ngày. Fixture dài riêng đạt data gates nhưng vẫn blocked vì synthetic source và ba evidence gates unverified. Không chạy model hoặc in model score trong lượt audit.

Tests kiểm tra distinct dates thay vì row counts; trường hợp 200 rows từ 10 repo nhưng chỉ có 20 test anchors vẫn fail ngưỡng 30; unknown status/missing row/zero tách biệt; schema invalid không có coverage giả; nguồn ClickHouse chưa có không fallback; data live đủ cửa sổ vẫn không tự thông qua evidence; empty registry không pass chỉ vì đủ ngày; label statistics và output tái lập; audit không gọi trainer.

```bash
python3 -m pytest ml/tests apps/streamlit/tests -q
git diff --check
```

ML-03 training/evaluation trên Gold và các checklist tương ứng trong plan vẫn chưa hoàn tất. Không có liên hệ/xác nhận DE hoặc thay đổi contract được giả định từ việc thêm audit này.

Validation local ngày 14/11/2026: **120 passed in 11.34s** (76 tests ML và 44 tests ứng dụng), `git diff --check` sạch. Hai lệnh audit đã chạy trực tiếp: app fixture trả data blocked; long smoke fixture trả data passed nhưng overall blocked, đều exit 2 như quy ước. Chưa chạy audit trên Gold.

Review trước bàn giao: Gemini 3.8 Flash và Codex review độc lập lần 2 đều không phát hiện lỗi chức năng cần sửa. Codex chạy lại **120 tests pass trong 11.23s**, diff sạch. Các review xác minh công cụ local, không phải xác nhận data contract hoặc nghiệm thu ML-03 trên Gold.
