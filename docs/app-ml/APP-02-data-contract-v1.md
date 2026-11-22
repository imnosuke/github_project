# APP-02 — Data contract v1

Ngày: 14/11/2026. Contract version: **1.0.0-draft**.

Trạng thái: **phía ứng dụng đã chốt cách tích hợp thử bằng snapshot tĩnh**. Contract live vẫn ở `1.0.0-draft` và chờ DE xác nhận. Các quyết định cho snapshot nằm ở mục 10.

## 1. Quy ước chung

- Tên field dùng snake_case. ID repo là số nguyên dương, không dùng tên repo làm khóa vì repo có thể đổi tên.
- Ngày truyền dưới dạng `YYYY-MM-DD`; timestamps ISO 8601 UTC có hậu tố `Z`. ClickHouse dùng UTC tường minh; Parquet timestamp có timezone UTC.
- `int64` là integer signed 64-bit, counts không âm; `string`, `bool`, `date`, `timestamp[UTC]`, `list<string>` là kiểu logic. Adapter phải validate, không silently coerce giá trị lỗi thành zero.
- Mỗi lần đọc có envelope gồm `contract_version`, `data_source`, `publication_id` và `published_at`. Ứng dụng dùng `fixture` cho demo tổng hợp, `snapshot` cho đợt trích xuất tĩnh và `live` cho Gold thật. Các datasets trong một lần render phải cùng publication. `publication_id` xác định một đợt trích xuất hoặc công bố nhất quán.
- DE có thể dùng bảng/view tên khác; adapter ánh xạ về tên logic bên dưới. Breaking changes tăng major; thêm optional fields có default tăng minor; sửa tài liệu tăng patch. Consumer từ chối major chưa hỗ trợ.
- Source timezone, event date, ingestion time và publication time là các khái niệm riêng. Không lấy max event timestamp để kết luận completeness.

## 2. repository_registry

Cần registry để biết repo được theo dõi kể cả ngày không có event. Grain: một repo trong một khoảng theo dõi `[tracking_start_date, tracking_end_date]`, end inclusive hoặc null. Khóa: `(repository_id, tracking_start_date)`; các khoảng của cùng ID không chồng lấn.

| Field | Kiểu | Nullable | Ý nghĩa |
| --- | --- | --- | --- |
| repository_id | int64 | Không | ID dương, ổn định |
| repository_name | string | Không | Tên owner/repo dùng để hiển thị; không là khóa |
| tracking_start_date | date | Không | Ngày đầu thuộc scope |
| tracking_end_date | date | Có | Ngày cuối thuộc scope; null nếu còn theo dõi |
| category | string | Có | Một category chính trong v1 |
| ecosystem | string | Có | Một ecosystem chính trong v1 |

Tracked repos trong kỳ là distinct IDs có khoảng theo dõi giao với kỳ. Tính growth chỉ cho repo thuộc scope trong toàn bộ hai cửa sổ so sánh. Registry hỗ trợ lịch sử scope; không dùng trạng thái enabled hiện tại để suy ra quá khứ.

## 3. repository_daily_metrics

Grain: một repo/ngày UTC thuộc khoảng theo dõi. Khóa duy nhất `(repository_id, date)`.

Producer trả dense rows cho scope và ngày được yêu cầu. Adapter có thể densify từ sparse Gold nhưng chỉ được điền zero khi day status là complete và toàn publication được kiểm tra. Không suy ra zero chỉ vì query không có dòng.

| Field | Kiểu | Nullable | Định nghĩa |
| --- | --- | --- | --- |
| repository_id | int64 | Không | FK tới registry có hiệu lực tại date |
| date | date | Không | Ngày xảy ra event theo UTC |
| total_events | int64 | Có | Số events hợp lệ sau dedup, mọi loại event |
| star_events | int64 | Có | Số WatchEvent; không phải total/net stars |
| fork_events | int64 | Có | Số ForkEvent |
| push_events | int64 | Có | Số PushEvent |
| commits_pushed | int64 | Có | Tổng payload.size của PushEvent; không phải distinct commits |
| prs_opened | int64 | Có | PullRequestEvent có action opened |
| prs_merged | int64 | Có | PullRequestEvent action closed và merged=true |
| prs_closed_unmerged | int64 | Có | PullRequestEvent action closed và merged=false |
| issues_opened | int64 | Có | IssuesEvent action opened |
| issues_closed | int64 | Có | IssuesEvent action closed |
| issue_comments | int64 | Có | Số IssueCommentEvent |
| unique_actors | int64 | Có | Distinct actor_id > 0 của mọi event, gồm bot |
| unique_human_actors | int64 | Có | Distinct actor_id > 0 không có login kết thúc bằng [bot], không phân biệt hoa/thường |
| active_contributors | int64 | Có | Reserved optional metric; v1 để null cho tới khi có contract contribution được DE xác nhận |

Các field phải hiện diện; nullable không có nghĩa được bỏ tên cột. Complete day: event counts và actor counts bắt buộc non-null, trừ `commits_pushed` được null nếu payload không đủ/không hỗ trợ và `active_contributors` chưa có định nghĩa. Missing day: mọi metric null. Provisional day: có thể có observed counts nhưng không dùng làm KPI hoàn chỉnh hoặc growth ranking. Null nghĩa không biết, zero nghĩa biết chắc không phát sinh.

Mọi event counts v1 gồm cả bot. Tên `unique_human_actors` chỉ phản ánh heuristic hậu tố login, không bảo đảm phân biệt mọi automation. Không gắn nhãn mọi actor là contributor. `commits_pushed` có thể đếm lại cùng commit ở nhiều push, không là code contribution độc nhất; thiếu payload.size không được giả thành zero mà không có quality policy.

## 4. repository_metadata

Grain/key: `(repository_id, snapshot_date)`. Snapshot là quan sát GitHub API tại một thời điểm, không tự khẳng định metadata đã đúng từ đầu ngày.

| Field | Kiểu | Nullable | Ý nghĩa |
| --- | --- | --- | --- |
| repository_id | int64 | Không | ID repo trong registry |
| snapshot_date | date | Không | Ngày UTC của lần snapshot |
| observed_at | timestamp[UTC] | Không | Thời điểm quan sát thực |
| repository_name | string | Không | owner/repo tại snapshot |
| description | string | Có | Mô tả, null nếu không có |
| primary_language | string | Có | Language chính |
| topics | list<string> | Có | Null: chưa biết; []: đã biết không có topics |
| license | string | Có | SPDX ID nếu có |
| archived | bool | Có | Trạng thái archive |
| is_fork | bool | Có | Repo là fork hay không |
| created_at | timestamp[UTC] | Có | Ngày tạo repo |
| current_stars | int64 | Có | Snapshot total stars; không cộng dồn theo ngày |
| current_forks | int64 | Có | Snapshot total forks; không cộng dồn theo ngày |

Category/ecosystem lấy từ registry, không gán nhầm thành GitHub API fields. Một row/ngày: nếu refresh nhiều lần, chọn observation cuối ngày và giữ `observed_at` thực. UI v1 hiển thị snapshot mới nhất kèm ngày và ghi rõ metadata hiện tại; không gọi filter language là phân loại lịch sử. ML sau này chỉ join snapshot `observed_at <= cutoff`; nếu cần nhiều snapshot/ngày phải đổi grain bằng phiên bản contract thích hợp.

Metadata là dataset optional cho MVP: được trả rỗng và UI dùng tên từ registry, ẩn filter không có dữ liệu. Không tạo snapshot giả khi fetch lỗi. Metadata mới không được làm thay đổi registry history âm thầm.

## 5. daily_data_status

Grain/key: một ngày UTC cho scope registry và publication hiện tại. Đây là dataset cần thiết để phân biệt zero với missing.

| Field | Kiểu | Nullable | Ý nghĩa |
| --- | --- | --- | --- |
| date | date | Không | Ngày UTC |
| status | string | Không | complete / provisional / missing |
| expected_files | int64 | Không | 24 file giờ cho full day GH Archive |
| processed_files | int64 | Không | Số giờ distinct đã validate và xử lý tới Gold, từ 0 đến 24 |
| quality_passed | bool | Không | Các required quality gates đã pass |
| published_at | timestamp[UTC] | Có | Thời điểm Gold được công bố |
| reason | string | Có | Giải thích thiếu/chưa complete |

- `complete`: 24/24 giờ tới Gold, required quality gates pass, publication nhất quán; bắt buộc published_at. Không yêu cầu reject count tuyệt đối bằng zero, nhưng reject policy và quality gate phải rõ.
- `provisional`: có kết quả một phần hoặc ngày chưa đóng; không đạt complete. Có thể 24 file nhưng quality chưa pass; UI hiển thị cảnh báo.
- `missing`: chưa có output Gold usable; processed_files vẫn có thể >0 nếu xử lý một phần trước đó nhưng chưa publish được.
- Thiếu status row cho ngày cần đọc là lỗi completeness/unknown; UI không điền zero, ranking không hợp lệ.
- Global complete áp dụng cho toàn scope, không chỉ một repo. Nếu DE triển khai per-repo failures phải bổ sung scope/status phù hợp trước khi công bố complete.

Freshness và completeness độc lập. Cấu hình app `expected_complete_through` xác định ngày phải hoàn tất theo SLA đã thống nhất. `latest_complete_date < expected_complete_through` thì stale; ngày thiếu giữa range vẫn phải kiểm tra riêng. Chưa có SLA được DE xác nhận nên live không được tự báo healthy; fixture đặt expectation rõ trong manifest. Đề xuất lịch bàn giao: hourly refresh, hoàn tất ngày D sau khi đủ file và tests; giờ cutoff cụ thể chờ DE chốt.

## 6. Growth và aggregation

Anchor `T` là ngày complete người dùng chọn. Với N=7 hoặc 30:

- Current: `[T-N+1, T]`, previous: `[T-2N+1, T-N]`, đều inclusive theo ngày UTC.
- `current = sum(star_events)`; `previous = sum(star_events)` của kỳ tương ứng.
- `absolute_delta = current - previous`.
- Nếu previous > 0: `growth_pct = 100 * absolute_delta / previous`.
- Nếu cả hai = 0: growth_pct = 0, trạng thái no_activity.
- Nếu previous = 0 và current > 0: growth_pct = null, trạng thái new_activity; không dùng infinity.
- Thiếu scope history, status không complete hoặc metric null: growth_pct và delta không công bố như kết quả hợp lệ; trạng thái insufficient_history hoặc incomplete_data.

Ranking v1 mặc định theo `current` giảm dần, sau đó `absolute_delta` giảm dần, cuối cùng repository_id tăng dần; ghi nhãn “star events trong kỳ”, không gọi đây là ML trending score. Có thể sort growth_pct riêng cho các repo previous >0. Window không hợp lệ bị loại khỏi ranking và có số repo bị loại/cảnh báo.

Event counts có thể cộng theo repo/ngày. Unique actors/contributors không cộng qua ngày hoặc repo để gọi là unique cả kỳ. Active repos đếm distinct IDs có total_events >0 trong kỳ complete; tracked repos lấy registry. Không trộn `current_stars` snapshot với star_events trong rolling sums.

## 7. Mapping Gold hiện tại và gaps

Nguồn đọc kiểm tra: `dbt_gharchive/models/gold/gold_repo_daily_activity.sql`.

| Contract | Gold hiện tại | Xử lý/gap |
| --- | --- | --- |
| repository_id, date | repo_id, event_date | Rename; validate ID/date |
| total_events | total_events | Map trực tiếp sau xác minh dedup |
| star_events, fork_events | stars_gained, forks_count | Rename, giữ semantics event counts |
| push_events, commits_pushed | push_events_count, total_commits_pushed | Rename; cần quality policy payload.size |
| prs_opened, prs_merged, prs_closed_unmerged | Cùng tên | Map |
| issues_opened, issues_closed | Cùng tên | Map |
| issue_comments | issue_comments_count | Rename |
| unique_actors | unique_contributors | Cần sửa/recompute loại actor_id=0; không map mù |
| unique_human_actors | unique_human_contributors | Cần loại actor_id=0, giữ heuristic bot |
| active_contributors | Không có đúng semantics | Null, không alias từ unique_contributors |
| registry | Không có | DE bổ sung, phía fixture có thể tạo trước |
| metadata snapshots | Không có | DE API enrichment; optional/rỗng ở MVP |
| daily_data_status | Không có | DE bổ sung từ manifest/control tables và quality checks |
| envelope/publication | Không có | DE thống nhất publish nhất quán hoặc adapter cơ chế snapshot an toàn |

Gold hiện sparse: repo/ngày không event không có dòng. Gold dùng full table rebuild và `anyLast` metadata; chưa có publication protocol. Không suy ra full day complete từ việc có bảng hoặc count >0. Tên repo hiện tại có thể dùng để đề xuất seed registry, nhưng không đủ chứng minh scope/history.

## 8. Sample records

Các sample dưới đây là **dữ liệu tổng hợp**; dùng ID/tên minh họa, không phải dữ liệu đo từ GitHub. Metric objects không lặp envelope; tất cả thuộc publication `fixture-001`.

```json
{
  "contract_version": "1.0.0-draft",
  "data_source": "fixture",
  "publication_id": "fixture-001",
  "published_at": "2026-11-02T03:00:00Z"
}
```

Registry và metadata:

```json
{
  "repository_registry": [{"repository_id": 1001, "repository_name": "example/alpha", "tracking_start_date": "2026-08-01", "tracking_end_date": null, "category": "data-engineering", "ecosystem": "analytics"}],
  "repository_metadata": [{"repository_id": 1001, "snapshot_date": "2026-11-01", "observed_at": "2026-11-01T23:00:00Z", "repository_name": "example/alpha", "description": "Synthetic demo repository", "primary_language": "Python", "topics": ["analytics"], "license": "MIT", "archived": false, "is_fork": false, "created_at": "2025-01-01T00:00:00Z", "current_stars": 200, "current_forks": 30}]
}
```

Complete day và daily metric row:

```json
{
  "daily_data_status": [{"date": "2026-11-01", "status": "complete", "expected_files": 24, "processed_files": 24, "quality_passed": true, "published_at": "2026-11-02T03:00:00Z", "reason": null}],
  "repository_daily_metrics": [{"repository_id": 1001, "date": "2026-11-01", "total_events": 10, "star_events": 3, "fork_events": 1, "push_events": 2, "commits_pushed": 5, "prs_opened": 1, "prs_merged": 1, "prs_closed_unmerged": 0, "issues_opened": 1, "issues_closed": 0, "issue_comments": 1, "unique_actors": 7, "unique_human_actors": 6, "active_contributors": null}]
}
```

Complete zero day dùng cùng schema: mọi event/actor count bằng 0, commits_pushed bằng 0 nếu được hỗ trợ, active_contributors null. Missing day phải có đủ tên field nhưng tất cả metrics null; status missing, quality_passed false, published_at null nếu chưa publish. Provisional observed counts không được dùng cho ranking.

Sample trên chỉ minh họa một ngày, chưa đủ 60 ngày cho growth 30d; APP-03 tạo fixture nhiều ngày và edge cases theo contract.

## 9. Validation và bàn giao

Consumer kiểm tra keys unique, IDs dương, types, null policy, registry coverage, status coverage và publication consistency. Counts không âm; unique_human_actors <= unique_actors <= total_events; prs_merged + prs_closed_unmerged là subset total_events, không cộng với prs_opened để suy ra distinct PRs. Counts các loại event đã liệt kê không vượt total_events khi cộng vì là các nhóm event/action tách biệt; commits không phải event count.

Producer chịu trách nhiệm dedup, file completeness, payload quality, Gold correctness và published consistency. Consumer chịu trách nhiệm window/aggregation correctness, UI labels, validation và không biến missing thành zero.

### Cần DE xác nhận trước live

- [ ] Schema/types/grain và cơ chế sparse → dense.
- [ ] Registry history và thời điểm bắt đầu theo dõi.
- [ ] Quy tắc loại actor ID không hợp lệ, bot heuristic và commits quality policy.
- [ ] Manifest/status và required quality gates.
- [ ] Publication consistency khi dbt rebuild; connection read-only và mapping tên dataset.
- [ ] Refresh cadence, SLA và expected_complete_through.
- [ ] Metadata availability và snapshot semantics.

Prediction contract nằm ở ML-04.

## 10. Quyết định phía ứng dụng cho snapshot tĩnh

Phạm vi là tích hợp thử file trích xuất từ GitHub hoặc GH Archive khi DE bàn giao. UI ghi rõ nguồn snapshot và thời điểm trích xuất. Mỗi đợt trích xuất có một `publication_id` cố định. Các file dùng chung trong một lần đọc thuộc cùng publication.

| Mục | Quyết định cho snapshot |
| --- | --- |
| Schema và scope | Dùng GitHub `repository_id` thật, ngày UTC và khóa `(repository_id, date)` cho metrics theo ngày. Registry dùng danh sách repo cố định của đợt trích xuất. Nếu thiếu lịch sử theo dõi, chỉ dùng phạm vi repo và ngày có bằng chứng từ đợt trích xuất. |
| Độ phủ và giá trị zero | Dùng `provisional` nếu biết dữ liệu trong ngày chỉ có một phần. Thiếu bằng chứng độ phủ thì UI hiển thị `unknown` theo quy tắc thiếu status row ở mục 5. Dùng `missing` khi có bằng chứng ngày đó chưa có output usable. Chỉ điền `0` cho repo thuộc scope vào ngày `complete` có bằng chứng đủ 24 giờ, qua kiểm tra chất lượng và thuộc cùng publication. Loại các ngày chưa complete khỏi KPI hoàn chỉnh và cửa sổ growth. |
| Metric | Ưu tiên đối soát `total_events`, `star_events` (`WatchEvent`) và `fork_events` (`ForkEvent`) từ event gốc hoặc aggregate có định nghĩa rõ. Nếu snapshot có lấy mẫu, số đếm chỉ mô tả dữ liệu trong mẫu. Chỉ dùng actor, commits, PR và issue khi có đủ trường và áp dụng được định nghĩa ở mục 3. Metric thiếu bằng chứng để `null` trong kết quả tích hợp thử. Một ngày chỉ đạt contract khi đáp ứng đầy đủ null policy ở mục 3. |
| Metadata | Nếu có GitHub API snapshot, giữ `observed_at` từ lần quan sát thực. `current_stars` và `current_forks` chỉ là số đếm tại thời điểm quan sát. Khi thiếu metadata, dùng tên từ registry và ẩn bộ lọc phụ thuộc metadata. |
| Freshness và phục vụ dữ liệu | Đọc file theo snapshot. Giữ `expected_complete_through` chưa xác định cho tới khi có SLA được xác nhận. Việc chọn view ClickHouse, phân quyền chỉ đọc và kiểm tra tính nhất quán khi dbt rebuild thuộc APP-07 live. |

### Thông tin kèm file và cách kiểm tra

Manifest bàn giao ghi nguồn, khoảng ngày/giờ UTC thực sự có mặt, danh sách GitHub repo ID hoặc bộ lọc đã dùng, cách lấy mẫu/giới hạn dòng nếu có, và thời điểm trích xuất. Với file tổng hợp, ghi thêm định nghĩa các metric. Dùng manifest để kiểm tra scope và độ phủ trước khi diễn giải một repo/ngày thiếu dòng.

- Khi có file, kiểm tra schema, ID, khóa trùng và phạm vi, rồi đối soát các metric có đủ dữ liệu cho một vài repo/ngày. Metadata API hoặc event lấy mẫu dùng được để thử đường đọc và trạng thái dữ liệu một phần.
- Một ngày đủ 24 giờ trên toàn scope, qua quality gates và có metrics đúng contract là ca đối soát đầu tiên cho APP-07. Growth 30 ngày cần hai cửa sổ liền nhau, tổng cộng 60 ngày complete cho repo được xét.
- Kết quả snapshot ghi theo bằng chứng thực tế. Các mục xác nhận live ở mục 9 vẫn chờ DE. ML-03 giữ yêu cầu Gold thật và bằng chứng dữ liệu đã có tại thời điểm dự báo.
