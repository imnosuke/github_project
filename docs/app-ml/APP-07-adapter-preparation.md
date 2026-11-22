# APP-07 — Chuẩn bị interface và cấu hình ClickHouse

Ngày: 14/11/2026. Trạng thái: **chuẩn bị local**, chưa tích hợp hoặc nghiệm thu dữ liệu thật.

## Phạm vi đã thực hiện

- UI/analytics/Explorer chỉ gọi `DataAdapter`; không truy cập `adapter.tables` hoặc manifest `envelope` của fixture.
- Bổ sung `publication()`, `date_bounds()`, `latest_complete_date()`, `day_status(start, end)`, `repository_catalog()` và `overview(start, end)` vào protocol. Giữ list/detail/time-series/growth hiện có.
- Adapter gắn với một publication nhất quán. Ngày UTC inclusive; status frames và catalog trả về cho caller; catalog dùng metadata mới nhất. Overview trả tracked count theo registry giao kỳ, totals hoặc null, trend có gap cho ngày thiếu/chưa complete.
- Phép tính Overview được chuyển nguyên vào fixture adapter; không đổi định nghĩa metric hoặc completeness. Filters, sorting và presentation vẫn nằm trong UI.
- Có cấu hình server-side qua environment, kiểm tra host/port/TLS/timeouts/user/database; password không nằm trong repr hoặc thông báo validation.
- Không thêm ClickHouse driver, không mở connection/query, không ánh xạ sparse Gold hoặc tự điền zero. `APP_DATA_SOURCE=clickhouse` kiểm tra cấu hình rồi báo rõ live adapter chưa implement; không fallback sang fixture.

## Cấu hình chạy

Xem `apps/streamlit/.env.example`. File mẫu **không tự được load**: export các biến trong shell/server process trước khi chạy Streamlit. `APP_DATA_SOURCE=fixture` vẫn là mặc định.

| Biến | Mặc định / quy tắc |
| --- | --- |
| APP_CLICKHOUSE_HOST | Bắt buộc khi chọn clickhouse; hostname/IP, không chứa URL/credentials |
| APP_CLICKHOUSE_SECURE | true; chỉ true/false, không phân biệt hoa thường |
| APP_CLICKHOUSE_PORT | 8443 nếu TLS; 8123 nếu không TLS; 1–65535 |
| APP_CLICKHOUSE_USER | default; live cần tài khoản reader riêng |
| APP_CLICKHOUSE_PASSWORD | Rỗng; cung cấp bằng cấu hình bí mật phía server |
| APP_CLICKHOUSE_DATABASE | gold |
| APP_CLICKHOUSE_CONNECT_TIMEOUT | 5 giây, số hữu hạn dương |
| APP_CLICKHOUSE_QUERY_TIMEOUT | 30 giây, số hữu hạn dương |

Chưa có kết nối nên chưa có bằng chứng quyền read-only. Khi triển khai live, DE phải cấp tài khoản chỉ đọc và xác minh quyền, query limits, publication consistency cùng serving mapping. Không đưa credential vào UI hoặc commit file môi trường thực.

Host và port là hai biến riêng: host không nhận `localhost:8123` hoặc URL; IPv6 dùng địa chỉ thuần như `::1`. `APP_DATA_SOURCE=clickhouse` là lựa chọn backend, còn publication contract sau này vẫn dùng `data_source=live`.

## Quy ước interface

- `publication()` trả contract/source/publication ID/time và `expected_complete_through` (null nếu chưa cấu hình SLA). `date_bounds()` trả hai ngày ISO hoặc null khi không có status; `latest_complete_date()` trả ngày complete mới nhất hoặc null.
- `day_status(start, end)` trả các status rows trong kỳ inclusive, giữ đủ cột contract; không tự tạo status complete cho ngày không có row.
- `repository_catalog()` trả một dòng/repo theo registry interval mới nhất, gồm các cột registry và `primary_language` từ metadata mới nhất theo `observed_at`; metadata rỗng vẫn giữ repo với language null.
- `overview(start, end)` trả `tracked_repositories`, `totals` và `trend`. Totals gồm total/star/fork events và active repositories, hoặc null khi kỳ không complete; trend có date và ba event metrics, giữ gap theo status.
- Kết quả thuộc caller; sửa DataFrame hoặc topics trong detail không được thay đổi publication nội bộ. UI vẫn chịu trách nhiệm filters, sorting và trình bày.

## Kiểm tra và giới hạn

Bộ test kiểm tra UI cả ba trang bằng wrapper chỉ có public methods, không có `tables`/`envelope`; regression suite giữ kiểm tra metrics, missing/provisional và short history. Thêm kiểm tra cấu hình lỗi, redaction và không fallback khi yêu cầu ClickHouse. Đây là automated QA; không thay thế browser review hoặc đối soát Gold.

## Hai vòng review và điều chỉnh

1. **Gemini 3.8 Flash:** không báo lỗi nghiêm trọng; đề nghị sửa kiểu trả về `Publication`, README còn hướng dẫn `source=live`/`adapter.envelope`, ignore file môi trường local và bổ sung test ngày đảo ngược. Các điểm này đã được điều chỉnh; `.gitignore` chỉ ngăn file chưa tracked, không thay đổi file đã tracked.
2. **Codex:** phát hiện host có port/malformed host vẫn qua validation, và xác nhận `repository_detail()` có thể trả topics chia sẻ bộ nhớ với fixture, trái cam kết caller ownership vừa bổ sung. Đã validate hostname/IP (gồm IPv6), tách port riêng và deep-copy detail. Thêm regression tests cho hai lỗi, ownership của catalog/overview và metadata optional rỗng.

Sau review, xử lý thêm adapter cũ trong Streamlit cache: đưa phiên bản interface vào cache key và xử lý lỗi publication trong nhánh tải dữ liệu có nút thử lại. Bổ sung regression test cho adapter không tương thích.

Kết quả cuối: `python3 -m pytest apps/streamlit/tests -q` — **44 passed in 5.17s**. `git diff --check` không có lỗi. Không chạy browser review hoặc truy vấn ClickHouse trong lượt chuẩn bị này.

## Việc còn lại để hoàn tất APP-07

DE xác nhận APP-02; bàn giao registry, status, publication, metadata và mapping Gold; implement live adapter có query ngày/pagination/limits; kiểm tra schema/completeness/freshness; đối soát một ngày rồi nhiều tuần lịch sử. APP-07 trong plan vẫn chưa hoàn tất.

## Ca đối soát Gold ngày 2025-01-15 UTC

Chạy [truy vấn chỉ đọc](app-07-reconcile-gold.sql) trên ClickHouse sau khi DE xác nhận đủ 24 giờ cho hai repo. Snapshot đi kèm chứa Parquet theo giờ, bảng tổng hợp và manifest. [Dữ liệu đối soát](../../apps/streamlit/data/snapshots/gharchive-2025-01-15/manifest.json)

| Repository ID | Repo | Total events | Star events | Fork events |
| --- | --- | ---: | ---: | ---: |
| 33884891 | `apache/airflow` | 299 | 16 | 8 |
| 39464018 | `apache/superset` | 217 | 17 | 11 |

Mapping ban đầu từ `gold.gold_repo_daily_activity` sang APP-02 dùng `repo_id` → `repository_id`, `event_date` → `date`, `total_events` → `total_events`, `stars_gained` → `star_events` và `forks_count` → `fork_events`. Mỗi repo phải có đúng một dòng Gold cho ngày đó và kết quả phải là `match`. Nếu lệch, kiểm tra đủ giờ, scope, chuyển đổi UTC và dedup `event_id` từ Bronze qua Silver trước khi chỉnh mapping.

Khi bàn giao, ghi kết quả hai hàng cùng tên view/schema, publication hoặc thời điểm query và bằng chứng độ phủ 24 giờ. Phía ứng dụng cần địa chỉ ClickHouse, tài khoản chỉ đọc qua kênh cấu hình phía server và mapping các bảng registry, status, publication trước khi bật adapter live.

### Thử nghiệm qua HTTP trên máy local

ClickHouse 24.3.12.75 UTC đã nạp 516 event từ 24 tệp giờ vào Bronze, giữ 516 event ở Silver và tạo hai hàng Gold. Truy vấn đối soát trả `match` cho cả hai repo. Chế độ `clickhouse_snapshot` cho phép Streamlit đọc metrics từ Gold qua tài khoản chỉ đọc và kiểm tra chúng với snapshot một ngày trước khi hiển thị. Các bảng registry, metadata và status vẫn đến từ snapshot tham chiếu. [Cấu hình chạy](../../apps/streamlit/README.md#thử-đọc-gold-trên-clickhouse-local)
