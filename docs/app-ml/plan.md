# Kế hoạch triển khai ứng dụng và ML

Ngày lập: **14/11/2026**. Owner: thành viên phụ trách ứng dụng/ML.

Trạng thái cập nhật 14/11/2026: **APP-01 hoàn tất quyết định thiết kế; APP-02 hoàn tất draft phía ứng dụng, chờ DE xác nhận**. APP-03–06 hoàn tất fixture/local; phần chuẩn bị APP-07 đã merge, suite ứng dụng 44 tests pass; chưa có live adapter/đối soát Gold. **ML-01 hoàn tất thiết kế local**: regression star events 30 ngày, baseline, eligibility và time split có purge được kiểm chứng bằng code. **ML-02 hoàn tất local**: feature builder và train/evaluate CLI đã chạy trên fixture, chưa nghiệm thu khả thi hoặc model trên Gold thật.

- [APP-01 — Phạm vi và stack](APP-01-scope-and-stack.md).
- [APP-02 — Data contract v1 draft](APP-02-data-contract-v1.md).

- [Review UI APP-04–06 và bước chuẩn bị APP-07](APP-06-ui-review.md).
- [ML-01 — Bài toán, label và evaluation](ML-01-problem-and-evaluation.md).
- [ML-02 — Feature builder và training skeleton](ML-02-feature-and-training.md).
- [ML-03 — Audit readiness (chuẩn bị local)](ML-03-readiness-audit.md).

## 1. Mục tiêu và phạm vi

Phát triển một ứng dụng phân tích GitHub sử dụng dữ liệu Gold từ pipeline của thành viên DE. Có thể làm trước bằng fixture cùng hợp đồng dữ liệu, sau đó thay bằng nguồn thật theo từng mốc.

Bản đầu gồm **Overview, Repository Explorer và Growth Analytics**. Các module tiếp theo gồm Ecosystem Comparison, Technology Radar, Repository Health, Contributor Analytics và ML Trending Prediction. Dữ liệu vận hành do DE cung cấp; phía ứng dụng có thể làm màn hình Pipeline Health khi contract sẵn sàng.

Phần việc này sở hữu giao diện, lớp truy xuất/phục vụ dữ liệu cho ứng dụng, logic phân tích đã thống nhất, feature engineering, training, evaluation và batch inference. DE sở hữu ingestion, raw/Silver/Gold, backfill, completeness và hạ tầng pipeline. Việc ghi prediction về serving và orchestration inference cần hai bên thống nhất.

## 2. Nguyên tắc triển khai

- Đọc curated Gold hoặc serving views, tránh gắn UI với raw payload.
- Tách UI, logic metric và data adapter để chuyển fixture sang nguồn thật qua cấu hình.
- Dữ liệu demo phải được ghi nhãn; không dùng để chứng minh chất lượng ML.
- Dùng UTC cho contract; phân biệt ngày event, ngày snapshot và thời điểm dự đoán.
- Không biến ngày thiếu dữ liệu thành ngày có giá trị zero.
- Không cộng các daily distinct counts để suy ra unique contributors của cả kỳ.
- Chỉ tính growth/rolling khi đủ cửa sổ dữ liệu; trường hợp mẫu số zero cần quy tắc rõ.
- Chưa đặt deadline theo tuần khi chưa có thời hạn đồ án và dữ liệu bàn giao.

## 3. Task chi tiết

### Giai đoạn A — Chốt đầu vào và dựng nền tảng

#### APP-01 — Chốt phạm vi và stack ứng dụng

- [x] Viết user flows: xem tổng quan → tìm repo → xem chi tiết → so sánh tăng trưởng.
- [x] Chốt các trang bản đầu, metric hiển thị và các trạng thái dữ liệu.
- [x] Chọn frontend, lớp API/backend nếu cần, thư viện chart và cách chạy local.
- [x] Chốt ranh giới giữa ứng dụng tùy chỉnh và dashboard Superset đã có.

**Đầu ra:** quyết định stack và danh sách màn hình bản đầu có lý do lựa chọn.

**Hoàn thành khi:** có thể mô tả một demo cụ thể, cách chạy local và phần nào dùng Superset; không cần triển khai mọi module ngay.

**Dependency:** không cần pipeline chạy thật.

#### APP-02 — Viết data contract v1

**Trạng thái:** phía ứng dụng đã chốt [cách tích hợp thử bằng snapshot tĩnh](APP-02-data-contract-v1.md#10-quyết-định-phía-ứng-dụng-cho-snapshot-tĩnh). Các checklist dưới đây là phần xác nhận hai phía cho Gold live.

- [ ] Định nghĩa `repository_daily_metrics`: một repo/ngày, khóa, tên cột, kiểu và nullability.
- [ ] Định nghĩa `repository_metadata`: repo/snapshot date, language, topics, category, ecosystem.
- [ ] Định nghĩa completeness/freshness và cách thể hiện ngày missing/provisional/complete.
- [ ] Ánh xạ các cột từ `gold.gold_repo_daily_activity` hiện tại; liệt kê phần DE cần bổ sung.
- [ ] Chốt stars gained, active contributor, bot handling, lookback và window boundaries.
- [ ] Chốt version schema, lịch cập nhật, cách truy cập và trách nhiệm thay đổi contract.

**Đầu ra:** tài liệu contract và sample records hợp lệ.

**Hoàn thành khi:** hai phía có thể tạo/đọc cùng sample mà không phải đoán ý nghĩa trường. Bản draft làm độc lập được; xác nhận với DE là gate tích hợp.

**Dependency:** APP-01; phối hợp DE.

#### APP-03 — Tạo fixture và data adapter

**Trạng thái:** hoàn tất local; xem [kết quả APP-03](APP-03-fixture-and-adapter.md).

- [x] Tạo dữ liệu tái lập cho nhiều repo, tối thiểu 90 ngày để thử hai cửa sổ 30 ngày và các trường hợp thiếu lịch sử.
- [x] Có repo tăng/giảm activity, ngày zero, ngày missing, metadata thiếu và dữ liệu chưa complete.
- [x] Tạo interface đọc list/detail/time series/ranking, kèm validation đầu vào.
- [x] Implement fixture adapter; thiết kế cấu hình chuyển nguồn dữ liệu.
- [x] Kiểm tra ý nghĩa metric và các edge cases bằng ví dụ có expected output.

**Đầu ra:** fixture, data adapter và hướng dẫn chạy demo.

**Hoàn thành khi:** UI và logic metric dùng được adapter mà không đọc trực tiếp file fixture; dữ liệu demo được nhận biết rõ.

**Dependency:** contract draft APP-02.

### Giai đoạn B — Ứng dụng bản đầu trên fixture

#### APP-04 — Dựng khung giao diện và điều hướng

**Trạng thái:** hoàn tất local; [kết quả APP-04](APP-04-streamlit-shell.md).

- [x] Tạo layout, navigation, bộ lọc ngày dùng chung và cấu hình data source.
- [x] Có loading, empty, error và stale/incomplete data states.
- [x] Hiển thị nguồn demo/thật và thời điểm dữ liệu cập nhật.

**Đầu ra:** ứng dụng local có điều hướng các trang bản đầu.

**Hoàn thành khi:** thay đổi bộ lọc có hành vi thống nhất và lỗi dữ liệu không bị hiển thị như số zero.

**Dependency:** APP-01, APP-03.

#### APP-05 — Repository Explorer và trang chi tiết

**Trạng thái:** hoàn tất fixture local; [kết quả APP-05](APP-05-repository-explorer.md).

- [x] Danh sách repo: tìm theo tên, sort, phân trang; lọc language/category khi metadata có sẵn.
- [x] Trang chi tiết: metadata, daily activity, star/fork events, PR/issue metrics.
- [x] Xử lý repo không tồn tại, thiếu metadata và thiếu lịch sử.
- [x] Cho phép so sánh hai repo trên cùng thời gian và cùng định nghĩa metric.

**Đầu ra:** luồng tìm → xem → so sánh repository.

**Hoàn thành khi:** các số liệu khớp fixture và hoạt động đúng với bộ lọc ngày.

**Dependency:** APP-04.

#### APP-06 — Overview và Growth Analytics

**Trạng thái:** hoàn tất local trên fixture; [kết quả APP-06](APP-06-overview-and-growth.md).

- [x] Tổng quan repo được theo dõi, events, star events và activity trend.
- [x] Tính tổng 7/30 ngày và so với kỳ liền trước có cùng độ dài.
- [x] Growth ranking có công thức, quy tắc ties và baseline zero.
- [x] Thể hiện cửa sổ thiếu dữ liệu bằng trạng thái phù hợp; không mặc định là giảm trưởng.
- [x] Phân biệt tổng repo trong registry với repo có activity trong kỳ.
- [x] Nếu cần unique contributors cả kỳ, yêu cầu aggregate đúng grain từ DE hoặc tập actor IDs; không cộng daily uniques.

**Đầu ra:** dashboard overview và trang growth có giải thích metric.

**Hoàn thành khi:** các trường hợp zero/missing/insufficient history được kiểm tra; xếp hạng khớp phép tính đối soát.

**Dependency:** APP-05 và contract metric APP-02.

### Giai đoạn C — Tích hợp pipeline thật

#### APP-07 — Adapter ClickHouse/API và kiểm tra contract

**Chuẩn bị local:** đã tách truy cập bảng thô khỏi UI, bổ sung interface và cấu hình ClickHouse; [chi tiết](APP-07-adapter-preparation.md). Các checklist tích hợp thật bên dưới vẫn chưa hoàn tất.

**Đã tích hợp thử snapshot GH Archive:** ngày 2025-01-15 UTC cho `apache/airflow` và `apache/superset`. Đã xử lý đủ 24 tệp giờ, giữ 516 sự kiện và đối chiếu tổng event, star event, fork event từ Parquet theo giờ. Cả ba trang Streamlit đọc được snapshot. Khi có Gold live cùng scope, dùng ngày này làm ca đối soát đầu tiên.

**Đã thử đọc Gold cục bộ:** `clickhouse_snapshot` đọc qua HTTP bằng tài khoản chỉ đọc và xác minh các metric theo snapshot một ngày trước khi hiển thị. [Cấu hình và giới hạn](APP-07-adapter-preparation.md#thử-nghiệm-qua-http-trên-máy-local)

- [ ] Thêm adapter nguồn thật theo stack đã chọn; credentials chỉ ở phía server/cấu hình môi trường phù hợp.
- [ ] Đọc Gold/view đúng contract, query có giới hạn ngày, sort và pagination.
- [ ] Kiểm tra schema, kiểu dữ liệu, completeness và freshness.
- [ ] Đối soát một ngày dữ liệu với DE; sau đó tích hợp nhiều tuần lịch sử.
- [ ] Xác minh UI chuyển fixture → nguồn thật mà không đổi cấu trúc trang.

**Đầu ra:** bản ứng dụng chạy với pipeline thật và biên bản đối soát ngắn.

**Hoàn thành khi:** metrics mẫu khớp truy vấn DE; dữ liệu thiếu/stale được hiển thị; có hướng dẫn cấu hình local.

**Dependency:** APP-06; DE có Gold theo contract và serving connection. Một ngày đủ để kiểm tra mapping, chưa đủ nghiệm thu rolling 30 ngày.

### Giai đoạn D — Analytics mở rộng

#### APP-08 — Ecosystem Comparison và Technology Radar

- [ ] Nhận registry/category/ecosystem cùng quy tắc repo thuộc nhiều nhóm.
- [ ] So sánh ecosystem trên cửa sổ thời gian giống nhau.
- [ ] Chốt công thức momentum, chuẩn hóa, trọng số và ngưỡng Radar.
- [ ] Hiển thị lý do xếp hạng/phân nhóm và giới hạn của score.

**Đầu ra:** comparison và Radar có giải thích.

**Hoàn thành khi:** score tái tính được, không double-count ngoài chủ đích và đủ input/window.

**Dependency:** APP-07; metadata và ecosystem aggregates từ DE.

#### APP-09 — Repository Health và Contributor Analytics

- [ ] Chốt định nghĩa contribution, new/returning, retention, concentration và maintenance.
- [ ] Xác định facts/aggregates bổ sung cho PR, issue, release và actor–repo activity.
- [ ] Thiết kế health score và các thành phần giải thích được.
- [ ] Tạo cohort/retention views khi có dữ liệu đủ grain và đủ lịch sử.

**Đầu ra:** health và contributor pages.

**Hoàn thành khi:** công thức và cohort boundaries có ví dụ kiểm chứng; không suy diễn contributor health chỉ từ tổng actor tương tác.

**Dependency:** APP-07 và dataset bổ sung từ DE; chưa thể hoàn thành chỉ với ba Gold tables hiện tại.

#### APP-10 — Pipeline Health view

- [ ] Chốt contract operations với DE: last success, files expected/processed, rejects, duration, freshness, test results.
- [ ] Hiển thị trạng thái và khoảng thời gian bị thiếu/lỗi.

**Đầu ra:** màn hình vận hành cho người dùng dự án.

**Hoàn thành khi:** phân biệt healthy/stale/incomplete/failed từ dữ liệu vận hành thực, có thời điểm cập nhật.

**Dependency:** control tables/operations outputs do DE cung cấp; có thể dựng UI bằng fixture trước.

### Giai đoạn E — ML

#### ML-01 — Chốt bài toán, label và evaluation

**Trạng thái:** hoàn tất thiết kế local; [đặc tả và mã tham chiếu](ML-01-problem-and-evaluation.md). Khảo sát Gold và availability thực tế còn là gate trước ML-03.

- [x] Xem xét bài toán khởi đầu: dự đoán số star events trong T+1…T+30 từ dữ liệu đến T.
- [x] Chốt regression hay ranking/classification, đối tượng repo và ngày dự đoán.
- [x] Định nghĩa label, metric đánh giá và baseline; quy tắc loại cửa sổ không complete.
- [x] Thiết kế train/validation/test theo thời gian, xử lý label windows chồng lấn ở ranh giới.

**Đầu ra:** đặc tả `ml-stars-30d-v1`, `ml/spec.py` và tests window/label/purge. Target đã chốt cho ML-02; chưa có bằng chứng chất lượng model hoặc mô phỏng availability lịch sử.

**Hoàn thành khi:** label/feature cutoff và split tính được bằng code, không dùng dữ liệu tương lai của tập đánh giá để train.

**Dependency:** APP-02; có thể thiết kế trước, cần khảo sát dữ liệu thật để chốt tính khả thi.

#### ML-02 — Feature pipeline và bộ khung training

**Trạng thái:** hoàn tất local; [cách chạy và giới hạn](ML-02-feature-and-training.md). Có fixture dài riêng cho full smoke test; fixture ứng dụng giữ nguyên và train bị chặn vì thiếu split. Chưa có evaluation trên Gold.

- [x] Tạo rolling stars/forks/activity và daily actor features theo contract ML-01; không gọi daily actors là unique contributors cả kỳ.
- [x] Tuân thủ quyết định metadata tại ML-01: v1 không dùng metadata, không join latest snapshot; as-of metadata là phần mở rộng sau này.
- [x] Có CLI/config cho feature generation, training và evaluation; output tái lập trong cùng môi trường.
- [x] Viết kiểm tra cutoff, window boundaries, missing dates và leakage bằng sample nhỏ.
- [x] Chạy fixture để kiểm tra luồng; ghi rõ metrics demo không có ý nghĩa đánh giá model.

**Đầu ra:** feature builder và skeleton train/evaluate chạy local.

**Hoàn thành khi:** cùng input/config tạo cùng feature dataset, và dữ liệu sau T không ảnh hưởng features tại T.

**Dependency:** ML-01, APP-03; không cần đợi toàn pipeline để dựng khung.

#### ML-03 — Huấn luyện và đánh giá trên lịch sử thật

**Chuẩn bị local:** đã có [audit readiness](ML-03-readiness-audit.md) cho coverage, eligibility và split shortfalls. Contract APP-02 vẫn chờ DE xác nhận; chưa có Gold audit hoặc training/evaluation thật. Các checklist nghiệm thu dưới đây giữ nguyên chưa hoàn tất.

- [ ] Kiểm tra đủ lookback, label horizon và các giai đoạn evaluation.
- [ ] Train baseline, sau đó thử một model phù hợp; chỉ tune trên train/validation.
- [ ] Báo cáo kết quả theo thời gian và nhóm repo; so với baseline.
- [ ] Lưu model, config, feature schema, dataset window và metrics.

**Đầu ra:** báo cáo evaluation và model artifact có truy vết.

**Hoàn thành khi:** có holdout hợp lệ và kết luận trung thực, kể cả model không tốt hơn baseline. Không bắt buộc model phức tạp.

**Dependency:** ML-02; DE bàn giao lịch sử complete đủ dài. Fixture không đáp ứng gate này.

#### ML-04 — Batch inference và tích hợp dự đoán

- [ ] Chốt prediction contract: repo, prediction date, horizon, output, model version, generated time.
- [ ] Implement inference và cách ghi output; thống nhất orchestration với DE.
- [ ] Tích hợp vào Explorer/Growth với ngày cập nhật và ý nghĩa prediction.
- [ ] Xử lý chưa có prediction, stale, thiếu feature và inference fail.

**Đầu ra:** predictions từ curated data xuất hiện trên ứng dụng.

**Hoàn thành khi:** output truy vết được tới model/features; rerun có quy tắc rõ; không hiển thị mock như prediction thật.

**Dependency:** ML-03 và serving/publish contract với DE.

### Giai đoạn F — Hoàn thiện và bàn giao

#### APP-11 — Kiểm thử tích hợp, tài liệu và demo

- [ ] Kiểm tra các user flows chính trên fixture và nguồn thật.
- [ ] Kiểm tra metric correctness, query latency thực tế và xử lý lỗi quan trọng.
- [ ] Viết hướng dẫn chạy, biến môi trường mẫu, data contract, metric definitions và ML limitations.
- [ ] Viết demo script đi từ repository detail → growth → prediction nếu đủ điều kiện.
- [ ] Ghi rõ tính năng đã nghiệm thu, tính năng demo và phần chưa hoàn thành.

**Đầu ra:** bản local tái lập, tài liệu và demo.

**Hoàn thành khi:** người khác làm theo hướng dẫn chạy được phần ứng dụng và hiểu dependency pipeline.

**Dependency:** APP-07 cho MVP; module mở rộng/ML chỉ đưa vào demo khi gate riêng đã đạt.

## 4. Mốc thực hiện

| Mốc | Task | Điều kiện đạt |
| --- | --- | --- |
| M1 — Nền tảng | APP-01 → APP-03 | Scope, contract draft, fixture và adapter |
| M2 — Demo ứng dụng | APP-04 → APP-06 | Overview, Explorer, Growth trên fixture |
| M3 — MVP dùng dữ liệu thật | APP-07 + APP-11 | Kết nối Gold, đối soát, tài liệu và demo local |
| M4 — Analytics mở rộng | APP-08/09/10 | Mỗi module có dataset và công thức phù hợp |
| M5 — ML thật | ML-01 → ML-04 | Đánh giá hợp lệ, batch output, hiển thị prediction |

ML-01/02 có thể làm song song với M2. APP-08/09/10 không bắt buộc hoàn thành trước ML nếu dữ liệu ML đã đủ. Bắt đầu bằng **APP-01 và APP-02**, sau đó APP-03; chưa cần xây mọi màn hình hoặc chọn model ngay.

## 5. Tài liệu liên quan

- [Đánh giá repository](../01-repository-assessment.md).
- [Phạm vi ứng dụng và ML](../02-applications-and-ml.md).
- [Phối hợp cuốn chiếu](../03-parallel-development.md).
- [Backlog chung](../04-priority-backlog.md).
