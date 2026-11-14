# Backlog ưu tiên và tiêu chí nghiệm thu

Ngày lập: **14/11/2026**. Các mục dưới đây là công việc đề xuất, chưa được đánh dấu hoàn thành chỉ vì repo đã có một phần code.

## Sprint tích hợp tiếp theo

Mục tiêu: **một ngày đủ 24 giờ, scope repository rõ ràng, dữ liệu được đối soát, rerun không đổi kết quả và phục hồi được sau lỗi**; ứng dụng đọc được daily metrics theo contract.

| ID | Ưu tiên | Owner chính | Công việc | Tiêu chí hoàn thành |
| --- | --- | --- | --- | --- |
| B01 | P0 | DE | Xác minh stack và smoke test | Compose khởi động, một file chạy hết pipeline, dbt tests pass, dashboard có dữ liệu; lưu kết quả |
| B02 | P0 | Cả hai | Chốt scope/kiến trúc | Registry ban đầu 50–100 repo; quyết định Spark/lake so với ClickHouse hiện tại được ghi rõ |
| B03 | P0 | Cả hai | Chốt data contract | Grain, keys, types, metric semantics, missing/completeness, timezone và sample được thống nhất |
| B04 | P0 | DE | Raw ingestion có kiểm soát | Đủ 24 giờ/ngày, raw lưu lại, checksum/file size, valid/reject counts, trạng thái từng file |
| B05 | P0 | DE | Rerun/failure recovery | Hai lần chạy cùng partition cho cùng kết quả; lỗi giữa chừng không làm mất dữ liệu đã công bố |
| B06 | P0 | DE | Incremental Silver/Gold | Chỉ cập nhật partitions bị ảnh hưởng; partitions khác không đổi |
| B07 | P0 | DE | Data tests có ý nghĩa | Duplicate, missing hours, corrupted gzip, timestamp lỗi, required IDs và đối soát counts được kiểm tra |
| B08 | P0 | Ứng dụng | Explorer + overview bằng fixture | Lọc ngày/repo, detail, charts, loading/empty/error states và nhãn demo |
| B09 | P0 | Cả hai | Tích hợp dữ liệu thật | Ứng dụng chuyển nguồn qua cấu hình; số liệu khớp query kiểm chứng |
| B10 | P0 | DE | Tái lập môi trường | Có `.env.example`, xử lý `.env` tracked phù hợp, khóa bộ phiên bản đã chạy được, lỗi init được nhận diện |

## Sau sprint đầu

| ID | Ưu tiên | Công việc | Tiêu chí hoàn thành |
| --- | --- | --- | --- |
| B11 | P1 | Backfill 7 ngày rồi một tháng | Chạy range không sửa code, retry phần lỗi, kiểm tra completeness và rerun |
| B12 | P1 | GitHub metadata snapshots | Repo có metadata cần cho filter/ecosystem; xử lý lỗi/rate limit và timestamp snapshot |
| B13 | P1 | Growth analytics | Rolling 7/30 ngày, comparison windows, rankings có định nghĩa và xử lý ngày thiếu |
| B14 | P1 | Operations dashboard | Last success, file counts, rows/rejects, duration, freshness, test results |
| B15 | P1 | Ecosystem/Radar | Registry/category rõ; công thức momentum và phân nhóm được giải thích |
| B16 | P1 | Health/Contributor | Fact và định nghĩa contribution đủ; cohort/retention/health có kiểm chứng |
| B17 | P2 | ML baseline | Target chốt, lịch sử đủ, time split, tránh leakage, báo cáo so baseline |
| B18 | P2 | Batch predictions | Versioned predictions hiển thị trên app, có ngày cập nhật và trạng thái stale |
| B19 | P2/P3 | Công nghệ mở rộng | Chỉ xét MLflow/Iceberg/graph/cloud sau khi core gates đạt và có nhu cầu rõ |

## Kịch bản nghiệm thu quan trọng

1. Chạy một ngày đầy đủ: source files, raw, Silver, Gold và dashboard khớp nhau.
2. Chạy lại cùng ngày: kết quả cuối không đổi, không duplicate.
3. Làm thiếu một hourly file: ngày không bị công bố nhầm là complete; retry được file đó.
4. File gzip hỏng hoặc JSON lỗi: có lỗi/reject được ghi nhận, không bỏ qua âm thầm.
5. Lỗi giữa load/transform/publish: dữ liệu trước đó vẫn sử dụng được hoặc trạng thái không hoàn tất được thể hiện rõ; rerun phục hồi được.
6. Backfill ngày cũ: không làm sai partitions khác, rolling metrics liên quan được cập nhật đúng.
7. Fixture và dữ liệu thật: cùng contract, UI không cần đổi cấu trúc.
8. Feature tại T: không sử dụng event/metadata chưa có tại T; labels và time split đúng.

## Nguyên tắc ưu tiên

Correctness → rerun/idempotency → incremental/backfill → quality/modeling → analytics hữu ích → dashboard polish → ML → hạ tầng bổ sung.

Không dùng số chart, số service hoặc việc có thư mục ML làm bằng chứng nghiệm thu. Mỗi mốc cần có output kiểm chứng: run status, test result, counts, truy vấn đối soát hoặc báo cáo evaluation phù hợp.
