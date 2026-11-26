# Demo đồ án RepoScope

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

## Kịch bản trình bày trong 90 giây

1. **Bài toán.** Dự đoán số sự kiện star của một repo trong 30 ngày dựa trên 30 ngày hoạt động trước đó. Đây là số sự kiện, không phải số star hiện có của repo.
2. **Dữ liệu.** Holdout dùng **2.136 giờ GH Archive, 89 ngày, 20 repo**. Sau khi dựng feature và nhãn theo thời gian, tập chấm có **600 mẫu từ 30 mốc dự đoán**. Dữ liệu và bản khóa có checksum trong [bộ dữ liệu](../../ml/datasets/gharchive-2026-02-05/README.md).
3. **Kết quả.** Chỉ biểu đồ MAE. Persistence 30 ngày đạt **28,07**, Ridge đạt **53,79**. Persistence thấp hơn ở cả 30 mốc. Chọn một repo và một ngày để trình bày dự đoán, thực tế và cửa sổ nhãn.
4. **Phạm vi đồ án local.** ML-03 đã chấm holdout hồi cứu từ dữ liệu GitHub thật. ML-04 chạy batch từ snapshot đã crawl và hiển thị dự đoán trong Streamlit local. Kết quả dựa trên mốc dữ liệu của snapshot. Ngày tạo file dự đoán là thời điểm chạy chương trình.

## Khi được hỏi về dữ liệu thiếu

Holdout có đủ từng giờ nhưng APP-02 vẫn đánh dấu `provisional` vì một phần sự kiện PR close thiếu cờ merge. Thí nghiệm hồi cứu kiểm tra lại từng giờ và loại hai feature tổng PR merge. Không điền zero cho PR chưa xác định. Các kết quả này dùng để so sánh model trong phạm vi đã nêu.

## Bằng chứng

- [Kết quả hai holdout và quyết định baseline](ML-03-retrospective-results.md)
- [Bằng chứng chạy pipeline và đối soát](../gharchive-streaming-staging.md)
- [Số liệu MAE/RMSE đầy đủ](../../ml/datasets/gharchive-2026-02-05/evaluation/metrics.json)
