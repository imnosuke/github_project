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

## Độ đầy đủ của số liệu PR merge

Giữ `prs_merged` và `prs_closed_unmerged` để phân tích hoạt động. Silver chỉ chấp nhận cờ JSON boolean `true` hoặc `false`. Nếu một sự kiện đóng PR thiếu cờ hợp lệ, Gold để cả hai chỉ số ở `null` cho repo/ngày tương ứng, kể cả khi các PR đóng khác cùng ngày có cờ hợp lệ. Repo/ngày có dữ liệu đầy đủ và không có PR đóng có giá trị `0` cho cả hai chỉ số.

Ở lớp phục vụ APP-02, áp dụng trạng thái `provisional` nếu một metric PR bắt buộc còn `null` trong scope của ngày. Chỉ công bố KPI toàn kỳ khi tất cả các ngày trong kỳ đạt điều kiện coverage và publication. Với truy vấn thăm dò trên kỳ chưa đầy đủ, báo kèm số repo/ngày có dữ liệu vì `sum()` trên cột nullable chỉ cộng các giá trị đã biết. [Quy tắc APP-02](APP-02-data-contract-v1.md#3-repository_daily_metrics)

Snapshot local từ 2025-01-01 đến 2025-11-16 UTC ghi nhận 236 cặp repo/ngày có số liệu PR chưa xác định trên 35 ngày đã tải đủ 24 tệp giờ. Ngày 2025-06-12 còn thiếu hai giờ nguồn và cần được xử lý như một khoảng trống coverage. Các con số này thuộc snapshot 20 repo, cần đo lại khi đối soát nguồn Gold của DE.

### Triển khai và đối soát

Chạy lại hai model từ Bronze trong môi trường dbt/ClickHouse của DE. Ví dụ với Docker Compose của repo:

```bash
docker compose exec -T airflow-webserver /opt/airflow/dbt_venv/bin/dbt build \
  --project-dir /opt/airflow/dbt_gharchive \
  --profiles-dir /opt/airflow/dbt_gharchive \
  --select stg_gharchive_events gold_repo_daily_activity
```

Sau khi build, chạy truy vấn chỉ đọc dưới đây cho khoảng ngày UTC có payload thiếu cờ merge. Mỗi cặp repo/ngày phải xuất hiện đúng một lần, có `gold_row_exists = 1` và cả hai chỉ số Gold là `NULL`. Nếu nguồn Silver không trả dòng nào, chọn lại khoảng ngày có sự kiện đóng PR thiếu cờ trước khi ghi kết quả đối soát.

```sql
SELECT s.event_date, s.repo_id, s.unknown_closes, isNotNull(g.repo_id) AS gold_row_exists,
       g.prs_merged, g.prs_closed_unmerged
FROM (
    SELECT event_date, repo_id, count() AS unknown_closes
    FROM silver.stg_gharchive_events
    WHERE event_date BETWEEN '2025-10-13' AND '2025-11-16'
      AND repo_id != 0 AND repo_full_name != ''
      AND event_type = 'PullRequestEvent' AND action = 'closed' AND pr_merged IS NULL
    GROUP BY event_date, repo_id
) AS s
LEFT JOIN gold.gold_repo_daily_activity AS g ON s.event_date = g.event_date AND s.repo_id = g.repo_id
ORDER BY s.event_date, s.repo_id
SETTINGS join_use_nulls = 1;
```

Đối soát thêm một repo/ngày đã xác minh đầy đủ để kiểm tra số đếm `true` và `false`, rồi lưu kết quả cùng publication và thời điểm truy vấn. Nếu cần bù lịch sử, ưu tiên nguồn của DE đã đối soát. Với GitHub REST timeline, ghép theo repo, số PR và thời điểm đóng. Kiểm tra lần mở lại và lần merge trước khi phân loại, giữ `null` khi chưa ghép được. [GitHub REST timeline](https://docs.github.com/en/rest/issues/timeline)


## Bàn giao nguồn Gold cho APP-07 và ML-03

Giữ một đường đọc Gold thông qua adapter của APP-02. Chế độ `clickhouse_snapshot` dùng một snapshot tham chiếu đã đối soát, truy vấn bằng ID repo và ngày, và báo lỗi nếu Gold lệch snapshot. Đây là bước kiểm thử mapping local.

Để mở adapter live, DE bàn giao Gold cùng registry, status/coverage theo giờ và publication ID nhất quán. Phía APP/ML xác nhận kiểu nullable của hai cột PR, độ đầy đủ của scope và thời điểm publication khả dụng. Đọc bằng quyền read-only, lọc ngày/phạm vi ở ClickHouse, giữ NULL cho số đếm chưa xác định và báo lỗi nguồn rõ ràng. Giữ Gold và dữ liệu mẫu ở hai đường đọc riêng để tránh ghi đè hoặc trộn nguồn trong feature/label.

## Biên bản kiểm thử APP-07/APP-11 phía ứng dụng

Đã dùng schema APP-02 trên ClickHouse 24.3.12.75 local với tài khoản chỉ được SELECT. Nạp snapshot hồi cứu của 20 repo, gồm 60 ngày complete 2025-08-14–2025-10-12 UTC và 2025-10-13 provisional, vào một publication kiểm thử. Thực hiện truy vấn qua HTTP và chạy Streamlit AppTest. Overview, Explorer và Growth đều chạy thành công. Growth 30 ngày có đủ 20 repo trong hai kỳ, và Overview ẩn KPI toàn kỳ khi chọn qua ngày provisional.

Các bước nghiệm thu còn lại với DE:

1. Chạy DAG trên staging đủ 24 giờ và retry lần nữa theo [checklist pipeline](../gharchive-streaming-staging.md). Lưu run ID, scope, checksum/coverage, số dòng Bronze, Silver và Gold trước/sau.
2. Đối soát Gold với ca 2025-01-15 cho hai repo. Bàn giao endpoint SELECT và chuỗi publication có registry, status, timestamps cùng phạm vi.
3. Chạy APP-11 trên dữ liệu live. Ghi thời gian query, freshness, cảnh báo thiếu/trễ dữ liệu và kiểm tra Explorer → Overview → Growth trong hai kỳ 30 ngày.
