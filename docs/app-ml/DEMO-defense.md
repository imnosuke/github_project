# Demo đồ án RepoScope

Demo gồm Overview, Repository Explorer, Growth Analytics và dự đoán lượt star 30 ngày bằng ML-03/04. APP-08 (Ecosystem Comparison và Technology Radar) và APP-09 (Repository Health và Contributor Analytics) được giữ trong [backlog mở rộng](plan.md#giai-đoạn-d--analytics-mở-rộng).

## Chạy demo

Từ thư mục gốc repo, cài `apps/streamlit/requirements.txt` nếu cần rồi chạy:

```powershell
python -m streamlit run apps/streamlit/retrospective_demo.py --server.address 127.0.0.1
```

Demo đọc Parquet và báo cáo holdout đã lưu trong repo. Có thể chạy ngay cả khi ClickHouse và Airflow tắt.

Tạo bộ dự đoán ML-04 local từ dữ liệu GH Archive đã fetch:

```powershell
python -m ml.local_batch --output ml/runs/ml04-local.json
```

Batch tính lại lượt star từ 720 tệp giờ của 30 ngày cuối snapshot đã kiểm chứng, rồi đối chiếu từng repo/ngày với bảng daily. Persistence 30 ngày tạo dự đoán cho 20 repo, lấy `2026-02-05` UTC làm mốc dữ liệu và dự đoán cửa sổ `2026-02-06` đến `2026-03-07`. Demo sẽ hiển thị file kết quả này. Với lần chạy mới, dùng thư mục hoặc tên output riêng nếu cần giữ kết quả đã có.

## Đối chiếu batch ML-04 với số lượt star thực tế

Đếm `WatchEvent` trên [bản sao GH Archive của ClickHouse](https://clickhouse.com/demos/explore-github-with-clickhouse-powered-real-time-analytics) cho 20 repo trong [scope.json](../../ml/datasets/gharchive-2026-02-05/scope.json). Truy vấn dùng `requested_name` để khớp tên repo trong dữ liệu sự kiện, gồm `dbt-labs/dbt-core` cho `dbt-labs/dbt`. Lọc theo `created_at` UTC từ đầu ngày 06/02 đến trước đầu ngày 08/03/2026. Đếm lại tương tự cho kỳ đầu vào 07/01–05/02 cho kết quả khớp với snapshot local ở cả 20 repo.

| Chỉ số | Kết quả |
| --- | ---: |
| Tổng lượt star dự báo | 3.670 |
| Tổng lượt star thực tế | 2.991 |
| Sai số tuyệt đối trung bình (MAE) | 42,85 lượt star/repo |
| Tổng sai số tuyệt đối chia tổng lượt star thực tế (WAPE) | 28,65% |
| Repo có dự báo cao hơn thực tế | 15/20 |

Ví dụ, `scikit-learn/scikit-learn` có dự báo 149 và thực tế 143. `huggingface/transformers` có dự báo 626 và thực tế 425. Tổng dự báo cao hơn thực tế 22,70%. Đây là kết quả hồi cứu của một kỳ 30 ngày vì batch được chạy sau khi kỳ kết thúc.

## Kịch bản trình bày trong 90 giây

1. **Bài toán.** Dự đoán số sự kiện star của một repo trong 30 ngày dựa trên 30 ngày hoạt động trước đó. Đây là số sự kiện, không phải số star hiện có của repo.
2. **Dữ liệu.** Holdout dùng **2.136 giờ GH Archive, 89 ngày, 20 repo**. Sau khi dựng feature và nhãn theo thời gian, tập chấm có **600 mẫu từ 30 mốc dự đoán**. Dữ liệu và bản khóa có checksum trong [bộ dữ liệu](../../ml/datasets/gharchive-2026-02-05/README.md).
3. **Kết quả.** Chỉ biểu đồ MAE. Persistence 30 ngày đạt **28,07**, Ridge đạt **53,79**. Persistence thấp hơn ở cả 30 mốc. Chọn một repo và một ngày để trình bày dự đoán, thực tế và cửa sổ nhãn.
4. **Phạm vi đồ án local.** ML-04 chạy batch từ snapshot đã crawl và hiển thị dự đoán trong Streamlit local. Đối chiếu batch với kỳ kết quả thực tế cho MAE **42,85** trên 20 repo. Ngày tạo file dự đoán là thời điểm chạy chương trình.

## Khi được hỏi về dữ liệu thiếu

Holdout có đủ từng giờ nhưng APP-02 vẫn đánh dấu `provisional` vì một phần sự kiện PR close thiếu cờ merge. Thí nghiệm hồi cứu kiểm tra lại từng giờ và loại hai feature tổng PR merge. Không điền zero cho PR chưa xác định. Các kết quả này dùng để so sánh model trong phạm vi đã nêu.

## Bằng chứng

- [Kết quả hai holdout và quyết định baseline](ML-03-retrospective-results.md)
- [Bằng chứng chạy pipeline và đối soát](../gharchive-streaming-staging.md)
- [Số liệu MAE/RMSE đầy đủ](../../ml/datasets/gharchive-2026-02-05/evaluation/metrics.json)
