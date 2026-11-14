# Phạm vi ứng dụng và ML

## Hình thức sản phẩm

Theo kế hoạch, một nền tảng phân tích GitHub có nhiều module dùng chung curated data từ pipeline. Không bắt buộc triển khai mỗi module thành một ứng dụng hoặc service riêng.

## Danh mục module

| Module | Chức năng | Dữ liệu cần |
| --- | --- | --- |
| Executive Overview | Tổng quan tracked repos, activity, growth, insight nổi bật | Gold metrics và metadata |
| Repository Explorer | Tìm kiếm, lọc, xem chi tiết, so sánh repo | Metadata snapshots, repo daily metrics |
| Growth & Trending Analytics | Growth ranking, star/fork velocity, gia tốc 7/30 ngày | Daily và rolling metrics |
| Technology Radar | Momentum theo công nghệ/ecosystem, phân nhóm Adopt/Trial/Assess/Watch | Category/ecosystem, growth, contributor và activity metrics |
| Repository Health Analytics | Đánh giá hoạt động, maintenance, sức khỏe cộng đồng | Push, PR, issue, release, contributor metrics |
| Contributor Analytics | New/returning contributors, retention, cohorts, concentration | Actor–repo activity và cohort aggregates |
| Ecosystem Comparison | So sánh tăng trưởng và cộng đồng giữa các nhóm công nghệ | Registry, metadata, ecosystem aggregates |
| ML Trending Prediction | Dự đoán tăng trưởng hoặc khả năng nổi lên trong 30 ngày tới | Historical features, labels, model outputs |
| Pipeline Operations / Data Quality | Freshness, thiếu file/ngày, trạng thái run/test, lỗi xử lý | Run metadata, file status, quality results |

Radar categories và health/momentum scores cần có công thức, ngưỡng và giải thích; không thể suy ra chỉ từ tên module. Đây là phần thiết kế tiếp theo.

## Phạm vi bản đầu

Ưu tiên **Executive Overview + Repository Explorer + Growth Analytics**.

Gold hiện có hỗ trợ một phần activity và daily metrics. Metadata, rolling growth và completeness cần DE bổ sung. Giao diện có thể phát triển trước bằng fixture tuân thủ schema, ghi rõ dữ liệu demo.

Thứ tự mở rộng đề xuất:

1. Explorer và overview.
2. Growth analytics.
3. Ecosystem comparison và Technology Radar khi có metadata.
4. Health và Contributor Analytics khi metric/facts đủ rõ.
5. ML khi có lịch sử và chất lượng dữ liệu phù hợp.

Operations dashboard làm song song với pipeline: DE cung cấp dữ liệu vận hành, phía ứng dụng có thể phụ trách hiển thị.

## ML: phần có thể làm trước

Có thể dựng feature builder, time split, training/evaluation scripts, batch inference và schema prediction bằng fixture. Dữ liệu mẫu chỉ giúp kiểm tra luồng và code, không chứng minh chất lượng dự đoán.

Bài toán đầu tiên đã chốt cho triển khai local tại [ML-01](app-ml/ML-01-problem-and-evaluation.md); tính khả thi trên Gold thật còn chờ khảo sát:

> Dùng dữ liệu đến ngày T để dự đoán số star events trong 30 ngày T+1 đến T+30.

Đây là bài toán regression, MAE là metric chính và persistence-30d là baseline chính. `ml/spec.py` kiểm chứng cutoff, label và split có purge 30 ngày. [ML-02](app-ml/ML-02-feature-and-training.md) đã có feature builder và train/evaluate skeleton trên fixture; chưa có model được đánh giá trên Gold thật. Nếu chuyển sang dự đoán emerging/trending repository dạng classification hoặc ranking, phải chốt định nghĩa label và metric đánh giá riêng.

Nguyên tắc:

- Feature tại T chỉ dùng dữ liệu có thể biết đến T; metadata join cũng cần xét thời điểm snapshot.
- Label dùng tương lai T+1 đến T+30.
- Chia train/validation/test theo thời gian, xử lý ranh giới label để tránh dùng thông tin tương lai của tập đánh giá trong huấn luyện.
- Lịch sử phải đủ cho feature lookback, label horizon và các tập đánh giá; một ngày dữ liệu không đủ.
- Phân biệt ngày thật sự không có event với ngày ingest thiếu.
- Bắt đầu bằng baseline đơn giản; so với baseline trước khi thêm model phức tạp.
- Regression có thể dùng MAE/RMSE; ranking có thể dùng Precision@K; chọn theo bài toán được chốt.
- Prediction lưu ngày dự đoán, horizon và model version để truy vết.

Growth ranking theo công thức minh bạch nên làm trước ML: tạo giá trị sớm, đồng thời giúp kiểm tra feature và dữ liệu.

MLflow, Iceberg, graph analytics và hạ tầng bổ sung chưa phải ưu tiên của sprint tích hợp đầu tiên.
