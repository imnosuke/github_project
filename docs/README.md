# Tài liệu đánh giá và kế hoạch phối hợp

Ngày đánh giá: **14/11/2026**. Mốc mã nguồn được kiểm tra: `156cd42` (commit trước đó: `033a556`).

Các tài liệu ghi lại findings từ việc đọc repo và đối chiếu kế hoạch GOSIP, cùng phương án phối hợp đã trao đổi. Đây là đánh giá tại một thời điểm, không phải trạng thái runtime trực tiếp.

| Tài liệu | Nội dung |
| --- | --- |
| [01-repository-assessment.md](01-repository-assessment.md) | Repo đã có gì, thiếu gì, vấn đề kỹ thuật và giới hạn xác minh |
| [02-applications-and-ml.md](02-applications-and-ml.md) | Các module sản phẩm, dữ liệu đầu vào và phạm vi ứng dụng/ML |
| [03-parallel-development.md](03-parallel-development.md) | Chia trách nhiệm, hợp đồng dữ liệu đề xuất và cách làm cuốn chiếu |
| [04-priority-backlog.md](04-priority-backlog.md) | Backlog ưu tiên, tiêu chí nghiệm thu và các mốc tích hợp |

## Kế hoạch theo phần việc

- [Ứng dụng và ML — plan theo task](app-ml/plan.md).
- [APP-01 — Quyết định Streamlit và phạm vi bản đầu](app-ml/APP-01-scope-and-stack.md).
- [APP-02 — Data contract v1 draft](app-ml/APP-02-data-contract-v1.md).

- [APP-03 — Fixture và data adapter](app-ml/APP-03-fixture-and-adapter.md).

- [APP-04 — Khung Streamlit](app-ml/APP-04-streamlit-shell.md).

## Cơ sở đánh giá

- Mã nguồn và cấu hình trong repo; không chỉ dựa vào mô tả README.
- Kế hoạch nhóm: [GitHub Open Source Intelligence Platform](https://chatgpt.com/library?file_id=libfile_59aea04645848191b24bd1230c9a5f06&account_id=personal).
- Phân công do nhóm xác nhận: một thành viên phụ trách DE/pipeline; thành viên còn lại phụ trách ứng dụng/ML.

Các schema, mốc bàn giao và thứ tự ưu tiên trong tài liệu là **đề xuất để nhóm thống nhất**, chưa phải cam kết đã được triển khai. Khi code thay đổi, cần cập nhật lại bảng trạng thái và bằng chứng nghiệm thu.
