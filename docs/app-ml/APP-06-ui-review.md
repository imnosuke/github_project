# APP-04–06 — Review UI thực tế và cập nhật sau review

Ngày ghi nhận: **14/11/2026**.

## Nguồn và phạm vi bằng chứng

Người phụ trách cung cấp báo cáo Gemini 3.8 Flash: đã tương tác trực tiếp với Streamlit tại `http://localhost:8501`, kiểm tra ba trang, filters, comparison và dữ liệu incomplete. Các quan sát browser bên dưới được ghi theo báo cáo đó; Codex không tự thực hiện lại phiên browser trong lượt cập nhật tài liệu này.

Codex đã xác nhận bốn file implementation/test đang có thay đổi trong working tree và chạy lại bộ tests hiện tại: **14 passed in 4.13s** với `python3 -m pytest apps/streamlit/tests -q`. Kết quả chạy lại độc lập này xác nhận automated suite pass, không thay thế visual QA hoặc nghiệm thu pipeline thật.

## 1. Kết quả UI theo báo cáo Gemini

| Hạng mục | Kịch bản và quan sát được báo cáo | Đánh giá |
| --- | --- | --- |
| Shell/header | Banner DEMO rõ; complete gần nhất 2026-11-02 UTC theo manifest; reload xóa cache | Đạt phạm vi APP-04 local |
| Bộ lọc ngày | Ngày missing 2026-08-15 và provisional 2026-11-03 có cảnh báo và bảng trạng thái; không cho start > end | Đạt APP-04 |
| Overview | Kỳ 2026-10-04…2026-11-02 có 6 tracked/5 active repo/430 star events; incomplete không công bố tổng giả; trend giữ gap | Đạt APP-06 theo báo cáo browser |
| Explorer | Search không phân biệt hoa/thường, language/category/ecosystem, pagination 5/10/20; lọc thiếu metadata tìm repo 1006 | Đạt APP-05 |
| Detail | Repo 1006 báo thiếu snapshot; repo 1005 không tổng hợp nếu kỳ vượt tracking history từ 2026-10-20 | Đạt APP-02/05 |
| Comparison | Hai repo cùng kỳ; phân biệt complete và incomplete/insufficient history | Đạt APP-05 |
| Growth | 7/30 ngày; sort current/delta/%; nhận diện new_activity/no_activity và loại short history | Đạt APP-06 |

Con số 430 thuộc kịch bản browser được báo cáo; automated test overview hiện có kiểm chứng riêng 119 star events cho kỳ 2026-10-26…2026-11-01. Không nhầm hai cửa sổ này thành cùng một kết quả.

## 2. Findings và chỉnh sửa được báo cáo

| Finding | Chỉnh sửa |
| --- | --- |
| Growth sort delta/% nhưng chart Y vẫn là current, gây khó đọc thứ hạng | Chart đổi Y và tiêu đề theo current / absolute_delta / growth_pct |
| Plotly line không có markers làm điểm đứng riêng cạnh gap khó nhìn thấy | Bật markers trên line charts Overview, detail và comparison |
| Trục/legend, snake_case và mã trạng thái thiếu thân thiện | Labels tiếng Việt, diễn giải lý do loại repo, column_config và định dạng integer/delta/% |
| KPI tracked repo đứng riêng, layout lệch khi incomplete | Một hàng năm cột; bốn KPI thiếu dữ liệu hiển thị dấu gạch ngang và cảnh báo |
| Comparison chart cố định star_events | Thêm chọn metric, gồm event metrics và daily unique actors |

Các chỉnh sửa là presentation/interaction; không phải thay đổi định nghĩa growth, bỏ completeness gates hay chứng nhận ML. Daily unique actors vẫn chỉ được so sánh ở grain ngày.

## 3. Files liên quan

- `apps/streamlit/analytics.py`: KPI layout, chart markers/labels, Growth Y theo sort, lý do loại và table formatting.
- `apps/streamlit/explorer.py`: table formatting, markers và comparison metric selector.
- `apps/streamlit/app.py`: column_config cho bảng day status.
- `apps/streamlit/tests/test_analytics.py`: thêm test thao tác các tùy chọn sort Growth.

Báo cáo Gemini ghi 14/14 tests pass trong 3.79s. Codex chạy lại sau khi nhận báo cáo: 14/14 pass trong 4.13s. Test sort mới kiểm tra đổi lựa chọn không sinh exception; riêng test này chưa assert chính xác Plotly Y cho từng lựa chọn. Không nên diễn giải số tests thành coverage toàn bộ hành vi hoặc visual correctness.

## 4. Trạng thái và giới hạn

APP-04–06 có UI review thực tế được báo cáo trên fixture; automated suite đã được Codex chạy lại thành công. Chưa có kiểm tra Gold thật, SLA live, hiệu năng ClickHouse hoặc ML evaluation. Không đánh dấu APP-07 hoàn tất từ kết quả này.

## 5. Bước tiếp theo — chuẩn bị APP-07

- [x] Bổ sung adapter interface cho catalog/latest metadata, day status, date bounds, publication và overview aggregates.
- [x] Loại `adapter.tables` khỏi UI và logic presentation; giữ fixture implementation sau interface.
- [x] Giữ các hành vi/filter/metric hiện có và tests khi refactor.
- [ ] Chuẩn bị cấu hình server-side ClickHouse, connection read-only và mapping Gold.
- [ ] Khi DE bàn giao registry/status/publication cùng contract đã xác nhận: tích hợp và đối soát dữ liệu thật.

Interface và cấu hình server-side đã được chuẩn bị trong [APP-07 preparation](APP-07-adapter-preparation.md); connection read-only và mapping Gold chưa triển khai. Nếu pipeline chưa sẵn sàng, có thể tiếp tục ML-01/02 sau phần chuẩn hóa interface.
