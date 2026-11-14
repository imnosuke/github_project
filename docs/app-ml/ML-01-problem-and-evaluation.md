# ML-01 — Dự đoán star events 30 ngày

Ngày: 14/11/2026. Phiên bản đặc tả: **ml-stars-30d-v1**.

**Đã chốt thiết kế local để bắt đầu ML-02.** Chưa khảo sát Gold thật, chưa train hoặc đánh giá model; tính khả thi vận hành còn chờ contract và lịch sử DE. Quyết định này thay đề xuất chưa chốt trong kế hoạch trước đây.

## 1. Bài toán và đơn vị mẫu

Chọn **regression**, một mẫu `(repository_id, anchor_date=T)`, dự đoán tổng `star_events` trong `[T+1, T+30]`, UTC inclusive. Đây là WatchEvent theo APP-02, gồm bot; không phải net stars, snapshot total stars, phần trăm growth hay nhãn trending. ID chỉ dùng join/đối soát, không đưa ID hoặc tên repo làm feature.

Đối tượng là các repo có trong registry lịch sử, có đủ 30 ngày lookback đến T. Giữ cả repo zero activity; không chọn cohort bằng số stars hoặc thứ hạng tương lai. Đánh giá khả năng dự đoán các ngày mới trong tracked universe, không tuyên bố cold-start generalization. Repo mới trong evaluation được báo cáo riêng nếu đã đủ lookback.

Mẫu training/evaluation cần đủ scope và dữ liệu **cả lookback lẫn label**. Production inference chỉ cần lookback; không yêu cầu tồn tại label tương lai. Không dùng việc thiếu label để chặn dự đoán thật.

## 2. Ngày dữ liệu và thời điểm thông tin sẵn sàng

- Feature event dates: `[T-29, T]`; các cửa sổ 7 ngày là `[T-6, T]`.
- Event/metadata cutoff: trước `00:00:00 UTC` ngày T+1. Không đọc activity của T+1 dù pipeline chạy muộn.
- Label: `y(T) = sum(star_events[d], d=T+1…T+30)`; label bằng zero là hợp lệ khi đủ 30 ngày complete có zero counts.
- `decision_at`: thời điểm thực sự chạy dự đoán, lưu riêng với anchor T. Chỉ sử dụng publication đã có tại decision_at; model và dữ liệu training cũng phải tồn tại trước lần dự đoán đó.

Gold ngày T có thể chỉ công bố ở T+1 hoặc muộn hơn. Khi đó một phần cửa sổ label đã trôi qua ở decision_at. Phải ghi `decision_at`, publication/version và độ trễ; không gọi toàn bộ label là 30 ngày tương lai tính từ thời điểm chạy. Nếu sản phẩm cần 30 ngày hoàn toàn sau lúc chạy, phải sửa anchor/label bằng phiên bản đặc tả mới trước ML-03.

Fixture được công bố theo một manifest sau cả dải ngày, không có lịch sử các publication dùng được tại từng T. Backfill Gold hiện tại cũng không chứng minh dữ liệu đã sẵn sàng trong quá khứ. ML-02 được chạy ở chế độ **retrospective event-time** để kiểm tra logic; trước khi tuyên bố backtest mô phỏng vận hành cần DE cung cấp publication history hoặc bắt đầu lưu prospective snapshots. Không giả thời điểm availability bằng event date.

## 3. Eligibility và dữ liệu thiếu

Đọc curated datasets theo APP-02, cùng publication đã validate. Trước khi tạo mẫu:

1. Khóa repo/date và status/date unique; registry intervals hợp lệ. Scope phải liên tục trong lookback; với training/evaluation phải liên tục cả label. Không suy ra scope lịch sử từ registry mới nhất.
2. Mỗi ngày yêu cầu phải có dense row và status complete, đủ quality/publication gates. Missing status, missing row, provisional hoặc metric bắt buộc null đều loại mẫu, không fill zero. Ngày sparse không có event chỉ densify khi upstream đã chứng minh complete.
3. Label chưa trưởng thành ở cuối dataset là `unmatured_label`, không phải zero. Không tạo label bằng tổng một phần.
4. Thiếu metadata không loại repo khỏi bộ numerics v1. Repo thiếu lookback là `insufficient_history`; không tự rút ngắn cửa sổ.

ML-02 phải xuất số mẫu trước/sau lọc và lý do: insufficient_history, incomplete_features, unmatured_label, incomplete_label, out_of_scope, purged. Dữ liệu sai schema/duplicate/count âm là lỗi validation làm dừng input, không âm thầm loại rồi tiếp tục. Label helper tham chiếu chỉ kiểm tra complete/counts của một repo đã validate; không thay thế registry/quality/publication validation.

## 4. Feature contract cho ML-02

Numerics v1, tại T:

| Nhóm | Features | Quy tắc |
| --- | --- | --- |
| Events | sum 7/30 ngày của star_events, fork_events, total_events, push_events, prs_opened, prs_merged, issues_opened, issues_closed, issue_comments | Counts không âm; đủ từng ngày trong cửa sổ |
| Activity | số ngày total_events > 0 trong 7/30 ngày | Đếm ngày, không phải distinct contributors |
| Actors | mean/max daily unique_actors và unique_human_actors trong 7/30 ngày | Gắn tên daily_actor_mean/max; không gọi tổng daily uniques là unique cả kỳ |

Không dùng `active_contributors` chưa có semantics; không dùng `commits_pushed` optional trong core v1. Không dùng `growth_ranking()` hoặc `repository_catalog()` hiện tại làm input lịch sử vì chúng không cung cấp feature snapshot theo T.

Metadata **không dùng trong model v1**. Khi thử nghiệm thêm sau này, chọn snapshot có `observed_at < feature_cutoff_exclusive` và thực sự available trước decision_at, không join snapshot mới nhất; timestamp có timezone bắt buộc. Category/ecosystem cần lịch sử as-of để dùng làm feature hoặc nhóm báo cáo lịch sử; chưa đủ thì ghi unknown. Imputation/encoding/scaling nếu thêm chỉ fit trên training.

## 5. Baselines và metrics

- Baseline chính: **persistence-30d**, `y_hat = sum(star_events[T-29…T])`. Cùng số ngày với label, không cần biết tương lai.
- Baseline kiểm tra: luôn dự đoán zero. Không gọi model tốt chỉ vì vượt zero khi vẫn thua persistence.
- Dự đoán là số thực hữu hạn, clamp âm về zero thống nhất cho mọi model trước scoring; không làm tròn. NaN/inf hoặc thiếu prediction của một mẫu hợp lệ là lỗi evaluation, không bỏ mẫu để làm đẹp điểm.
- Metric chọn model: **MAE** trên original event-count scale. Secondary: RMSE và macro-MAE theo repo (trung bình MAE từng repo). Không dùng MAPE vì label zero hợp lệ; không tự chuyển metric sau khi xem test.
- Cùng eligibility và cùng test rows cho mọi baseline/model; nếu hòa MAE validation thì giữ phương án đơn giản hơn, persistence là mặc định. Test chỉ dùng sau khi đóng băng lựa chọn, không tune lại trên test.

ML-03 báo MAE/RMSE, số repo/mẫu, tỷ lệ zero-label, số bị loại, kết quả theo anchor date và nhóm mức activity **từ lookback** (zero / nonzero); tách repo từng thấy/chưa thấy trong train. Lưu cả absolute scores và chênh lệch MAE so persistence; relative improvement chỉ tính nếu MAE baseline > 0, nếu không thì null. Không đặt ngưỡng "tốt" khi chưa có dữ liệu thật.

Daily anchors và horizon 30 ngày làm labels trong cùng tập chồng lấn. Không coi từng row là quan sát độc lập, không dùng random-row confidence interval. Báo thêm độ nhạy trên anchors cách nhau 30 ngày với lịch cố định trước evaluation; không chọn offset tốt nhất. Các kết luận ban đầu là descriptive nếu chưa có đủ nhiều giai đoạn holdout.

## 6. Time split và purge

Một bộ boundary ngày dùng chung cho tất cả repo. Không random split theo row/repo. Config có train_start, validation_start=V, test_start=S và test_end, đều là anchor dates UTC.

- Train: `train_start <= T < V` và **`T+30 < V`**.
- Validation: `V <= T < S` và **`T+30 < S`**.
- Test: `S <= T <= test_end`, chỉ giữ label đã trưởng thành và complete.
- Các anchors còn lại trong hai khoảng giáp ranh là `purged`; ngoài range là `outside`.

Ví dụ minh họa (không phải ngày bàn giao DE):

| Tập | Anchors giữ lại | Ngày label cuối tối đa |
| --- | --- | --- |
| Train | 2026-01-30…2026-03-31 | 2026-04-30 |
| Purge | 2026-04-01…2026-04-30 | Không dùng |
| Validation | 2026-05-01…2026-05-31 | 2026-06-30 |
| Purge | 2026-06-01…2026-06-30 | Không dùng |
| Test | 2026-07-01…2026-07-30 | 2026-08-29 |

Training labels kết thúc trước anchor đầu validation; validation labels kết thúc trước anchor đầu test. Feature history của tập sau được phép giao với dữ liệu lịch sử trước đó, vì đã có tại cutoff; không đưa labels của tập sau vào fit. Purge là gate theo event date; availability thực tế vẫn phải kiểm tra riêng theo mục 2.

ML-03 chốt boundary từ báo cáo coverage trước khi xem model scores, ưu tiên ít nhất 60 train anchors, 30 validation anchors, 30 test anchors sau purge. Cần tối thiểu **239 ngày liên tục** cho bố cục đó với lookback/horizon 30 và hai khoảng purge 30 ngày, chưa tính ngày mất hoặc scope bắt đầu muộn; đây là gate thiết kế của dự án, không đảm bảo đủ thống kê hay model tốt. Nếu dữ liệu không đủ, dừng ML-03 và báo giới hạn, không giảm purge hoặc random split để đủ mẫu. Trong lần evaluation đầu, giữ model fit trên train, tune trên validation rồi freeze trước test; chưa refit thêm validation cho kết quả test này.

## 7. Mã tham chiếu và kiểm chứng

`ml/spec.py` triển khai window/cutoff, label và split; chưa phải feature pipeline/trainer. Chạy từ repo root:

```bash
python3 -m ml.spec --anchor 2026-04-01 \
  --train-start 2026-01-30 --validation-start 2026-05-01 \
  --test-start 2026-07-01 --test-end 2026-07-30
python3 -m pytest ml/tests -q
```

Ví dụ trả feature_start=2026-03-03, feature_end=2026-04-01, label_start=2026-04-02, label_end=2026-05-01, cutoff_exclusive=2026-04-02T00:00:00Z và partition=purged. Label có daily counts 1…30 cho đúng 30 ngày có expected sum **465**; thay giá trị tại T hoặc T+31 không đổi label. Tests kiểm tra cả ngày nhuận, ranh giới purge, missing/provisional/null/âm và zero label.

Khảo sát fixture `fixture-001` bằng public adapter: 95 ngày, 93 complete, 1 missing (2026-08-15), 1 provisional (2026-11-03). Với lookback 30 và label 30, có **100 cặp repo/anchor** hợp lệ cho star/count completeness: mỗi repo 1001/1002/1003/1004/1006 có 20 anchors từ 2026-09-14 đến 2026-10-03; repo 1005 có zero mẫu do thiếu lịch sử. Đây là kiểm tra lịch/label trên fixture, không phải dataset nghiệm thu hay ML score. Các anchors quá ngắn để tạo ba tập đã purge.

Kiểm tra ngày 14/11/2026: `python3 -m pytest ml/tests apps/streamlit/tests -q` — **71 passed in 5.41s** (27 tests ML-01 và 44 tests ứng dụng). Ví dụ CLI bên trên trả đúng cửa sổ và `purged`; `git diff --check` sạch. Test fixture audit trong `ml/tests/test_fixture_contract.py` tái lập con số 100 mẫu; chưa kiểm tra feature builder vì thuộc ML-02.

Review trước bàn giao: Gemini 3.8 Flash không tìm thấy lỗi chức năng; góp ý định dạng đã được chỉnh. Codex review độc lập lần 2 không tìm thấy finding chức năng cần sửa và chạy lại **71 tests pass trong 5.15s**, CLI đúng kết quả và diff sạch. Các review này kiểm tra đặc tả/code local, không chứng nhận chất lượng model hoặc dữ liệu Gold.

## 8. Bàn giao và phần chưa hoàn tất

ML-01 hoàn tất thiết kế local và mã kiểm chứng. ML-02 tiếp theo: feature builder, dataset eligibility/audit, train/evaluate CLI và tests kiểm tra thay đổi dữ liệu sau T không đổi features tại T. Chưa có trained model, model artifact, predictions, evaluation report hoặc benchmark Gold.

Trước ML-03, DE cần xác nhận APP-02; bàn giao lịch sử registry/daily/status đủ dài, cơ chế publication/version nhất quán, lịch sử availability hoặc snapshot prospective và SLA. Khảo sát null/missing/zero/label distribution trên Gold rồi ghi biên bản khả thi và boundary cố định. Không coi các dependency này đã được DE chấp thuận qua tài liệu này.
