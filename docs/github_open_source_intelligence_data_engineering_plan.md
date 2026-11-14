# GitHub Open Source Intelligence Platform

## Kế hoạch triển khai đồ án Data Engineering

> **Working title:** GitHub Open Source Intelligence Platform (GOSIP)\
> **Product angle:** Open Source Technology Radar + Repository Health &
> Growth Analytics\
> **Mục tiêu chính:** Xây dựng một batch-oriented data platform có khả
> năng thu thập, lưu trữ, xử lý, mô hình hóa và phục vụ dữ liệu hoạt
> động của GitHub để phân tích xu hướng công nghệ, sức khỏe repository,
> cộng đồng contributor và dự đoán các repository có tiềm năng tăng
> trưởng.

------------------------------------------------------------------------

# 1. Executive Summary

Đồ án xây dựng một **Data Engineering platform end-to-end** trên dữ liệu
public GitHub. Thay vì tập trung vào realtime streaming, hệ thống ưu
tiên **batch processing, incremental processing và backfill**, vì đây là
các bài toán rất thực tế trong Data Engineering và phù hợp với đặc tính
của nguồn dữ liệu GH Archive.

Nguồn dữ liệu chính:

-   **GH Archive**: lịch sử GitHub public events theo từng giờ.
-   **GitHub REST/GraphQL API**: bổ sung metadata cho repository, user,
    language, topic, release và các thông tin không có đầy đủ trong
    event log.
-   Có thể bổ sung các nguồn reference khác ở giai đoạn mở rộng.

Hệ thống sử dụng kiến trúc kiểu lakehouse/medallion:

``` text
                     +------------------+
                     |    GH Archive    |
                     | hourly JSON.gz   |
                     +---------+--------+
                               |
                               | batch download
                               v
                     +------------------+
                     |    Ingestion     |
                     | Python + Airflow |
                     +---------+--------+
                               |
                               v
                     +------------------+
                     | Object Storage   |
                     |      MinIO       |
                     +---------+--------+
                               |
                  +------------+-------------+
                  |                          |
                  v                          v
             Bronze Layer              Metadata API
             raw events                GitHub API
                  |                          |
                  +------------+-------------+
                               |
                               v
                     +------------------+
                     | Apache Spark     |
                     | normalize/enrich |
                     +---------+--------+
                               |
                               v
                     +------------------+
                     |   Silver Layer   |
                     | Parquet/Iceberg  |
                     +---------+--------+
                               |
                               v
                     +------------------+
                     | dbt / Spark SQL  |
                     | analytics models |
                     +---------+--------+
                               |
                               v
                     +------------------+
                     |    Gold Layer    |
                     +---------+--------+
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
        +-----------+     +-----------+    +-----------+
        |ClickHouse |     | ML/MLflow |    |Data Quality|
        +-----+-----+     +-----+-----+    +-----------+
              |                 |
              v                 v
        +-----------+     +-----------+
        | Dashboard |     | Predictions|
        | Superset  |     | / Ranking |
        +-----------+     +-----------+
```

Sản phẩm cuối không chỉ là dashboard đếm stars. Platform hướng tới trả
lời các câu hỏi có giá trị hơn:

-   Công nghệ nào đang tăng momentum?
-   Repository nào đang nổi lên nhanh nhất?
-   Repository nào có community khỏe?
-   Contributor retention của các project khác nhau như thế nào?
-   Repository có dấu hiệu bị bỏ maintenance không?
-   Những project nào có khả năng trở thành trending repository trong
    tương lai gần?

------------------------------------------------------------------------

# 2. Mục tiêu đồ án

## 2.1. Mục tiêu Data Engineering

Đồ án cần chứng minh được các năng lực:

1.  Thu thập dữ liệu từ nhiều nguồn.
2.  Quản lý raw data có partition.
3.  Xử lý dữ liệu semi-structured ở quy mô lớn.
4.  Thiết kế incremental pipeline.
5.  Hỗ trợ historical backfill.
6.  Thiết kế Bronze / Silver / Gold layers.
7.  Chuẩn hóa heterogeneous event schemas.
8.  Xây dựng dimensional/analytical data model.
9.  Data quality và observability.
10. Orchestration và dependency management.
11. Idempotency và khả năng rerun.
12. Serving data tối ưu cho analytics.
13. Xây dựng feature pipeline cho ML.
14. Container hóa và reproducible deployment.

## 2.2. Mục tiêu sản phẩm

Xây dựng một **Open Source Intelligence Platform** gồm nhiều ứng dụng
con:

-   Technology Radar.
-   Repository Explorer.
-   Repository Health Analytics.
-   Growth & Trending Analytics.
-   Contributor Analytics.
-   Ecosystem Comparison.
-   ML Trending Prediction.
-   Pipeline Operations / Data Quality Dashboard.

------------------------------------------------------------------------

# 3. Scope đề xuất

## 3.1. Không nên ingest toàn bộ GitHub ngay từ đầu

GH Archive có lượng dữ liệu rất lớn. Scope phù hợp cho đồ án là chọn một
tập repository có chủ đích.

Ví dụ 500--5,000 repositories thuộc các category:

-   Frontend.
-   Backend.
-   Database.
-   Data Engineering.
-   AI/ML.
-   DevOps.
-   Cloud.
-   Programming Languages.
-   Developer Tools.

Có thể duy trì một `repository_registry`:

  repo                category           ecosystem   enabled
  ------------------- ------------------ ----------- ---------
  facebook/react      frontend           react       true
  vuejs/core          frontend           vue         true
  sveltejs/svelte     frontend           svelte      true
  apache/spark        data-engineering   spark       true
  duckdb/duckdb       database           analytics   true
  dbt-labs/dbt-core   data-engineering   analytics   true

Điều này giúp:

-   Giảm compute.
-   Có scope rõ.
-   Dễ so sánh ecosystem.
-   Dashboard có câu chuyện cụ thể.
-   Backfill khả thi trên máy cá nhân.

## 3.2. Historical range

MVP:

-   3--6 tháng dữ liệu.

Full project:

-   12--24 tháng.

Không cần download nhiều năm ngay từ đầu.

------------------------------------------------------------------------

# 4. Data Sources

## 4.1. GH Archive --- nguồn chính

Website:

https://www.gharchive.org/

GH Archive lưu public GitHub events theo từng giờ.

Ví dụ:

``` text
2026-10-01-0.json.gz
2026-10-01-1.json.gz
...
2026-10-01-23.json.gz
```

Các event quan trọng:

``` text
PushEvent
WatchEvent
ForkEvent
IssuesEvent
IssueCommentEvent
PullRequestEvent
PullRequestReviewEvent
PullRequestReviewCommentEvent
CreateEvent
DeleteEvent
ReleaseEvent
MemberEvent
PublicEvent
```

### Vai trò

GH Archive dùng cho:

-   Historical activity.
-   Incremental daily ingestion.
-   Backfill.
-   Event analytics.
-   Contributor activity.
-   Stars/forks/activity growth.

------------------------------------------------------------------------

## 4.2. GitHub REST API

Documentation:

https://docs.github.com/en/rest

Dùng để enrich:

-   Repository metadata.
-   Description.
-   Topics.
-   Primary language.
-   Languages.
-   License.
-   Default branch.
-   Archived status.
-   Fork status.
-   Created date.
-   Current stars/forks/watchers.
-   Releases.
-   Contributors khi cần.

Không nên dùng API làm nguồn event history chính vì rate limit.

------------------------------------------------------------------------

## 4.3. GitHub GraphQL API

Documentation:

https://docs.github.com/en/graphql

Có thể dùng khi cần query metadata phức tạp hoặc nhiều nested resources.

MVP có thể chỉ dùng REST API để giảm complexity.

------------------------------------------------------------------------

# 5. Event Model

Raw event chung:

``` json
{
  "id": "event-id",
  "type": "WatchEvent",
  "actor": {
    "id": 123,
    "login": "developer"
  },
  "repo": {
    "id": 456,
    "name": "owner/repository"
  },
  "payload": {},
  "public": true,
  "created_at": "2026-10-20T12:00:00Z"
}
```

Khó khăn quan trọng: `payload` phụ thuộc vào `event.type`.

Ví dụ:

``` text
WatchEvent.payload
ForkEvent.payload
PushEvent.payload
PullRequestEvent.payload
IssuesEvent.payload
```

có schema khác nhau.

Đây là một trong những bài toán transformation chính của project.

------------------------------------------------------------------------

# 6. Kiến trúc tổng thể

## 6.1. Logical architecture

``` text
                       DATA SOURCES
             +-------------+-------------+
             |                           |
       +-----v------+               +----v-----+
       | GH Archive |               | GitHub   |
       | JSON.gz    |               | REST API |
       +-----+------+               +----+-----+
             |                           |
             +-------------+-------------+
                           |
                           v
                  +-----------------+
                  | INGESTION LAYER |
                  | Python/Airflow  |
                  +--------+--------+
                           |
                           v
                  +-----------------+
                  | OBJECT STORAGE  |
                  | MinIO / S3 API  |
                  +--------+--------+
                           |
            +--------------+--------------+
            |                             |
            v                             v
       +----------+                  +----------+
       | BRONZE   |                  | METADATA |
       | raw      |                  | snapshots|
       +----+-----+                  +----+-----+
            |                             |
            +--------------+--------------+
                           |
                           v
                  +-----------------+
                  | PROCESSING      |
                  | Apache Spark    |
                  +--------+--------+
                           |
                           v
                  +-----------------+
                  | SILVER          |
                  | normalized data |
                  +--------+--------+
                           |
                           v
                  +-----------------+
                  | TRANSFORMATION  |
                  | dbt / Spark SQL |
                  +--------+--------+
                           |
                           v
                  +-----------------+
                  | GOLD            |
                  | analytics marts |
                  +--------+--------+
                           |
           +---------------+----------------+
           |               |                |
           v               v                v
     +-----------+   +-----------+    +-----------+
     |ClickHouse |   | MLflow    |    | Quality   |
     |analytics  |   | models    |    | checks    |
     +-----+-----+   +-----+-----+    +-----------+
           |               |
           v               v
     +-----------+   +-----------+
     | Superset  |   | Prediction|
     | Dashboard |   | tables    |
     +-----------+   +-----------+
```

------------------------------------------------------------------------

# 7. Tech Stack

## 7.1. Core stack

  -----------------------------------------------------------------------
  Layer                   Technology              Vai trò
  ----------------------- ----------------------- -----------------------
  Source                  GH Archive              Historical GitHub
                                                  events

  Metadata                GitHub REST API         Repository metadata

  Ingestion               Python                  Downloader/API client

  Orchestration           Apache Airflow          Scheduling, DAG,
                                                  backfill

  Object Storage          MinIO                   S3-compatible data lake

  Processing              Apache Spark            Large-scale transform

  Storage format          Parquet                 Columnar storage

  Optional table format   Apache Iceberg          ACID/table
                                                  metadata/schema
                                                  evolution

  Transformation          dbt                     Gold analytical
                                                  models/tests/docs

  Analytics DB            ClickHouse              OLAP serving

  Dashboard               Apache Superset         BI/analytics

  ML                      scikit-learn/XGBoost    Prediction

  Experiment tracking     MLflow                  ML lifecycle

  Data quality            dbt tests + custom      Validation
                          checks                  

  Infra                   Docker Compose          Local deployment

  Version control         GitHub                  Source code/CI
  -----------------------------------------------------------------------

## 7.2. Stack tối giản nếu thời gian hạn chế

``` text
Python
Airflow
MinIO
Spark
Parquet
PostgreSQL
dbt
Superset
Docker Compose
```

Có thể thay ClickHouse bằng PostgreSQL ở MVP.

## 7.3. Stack nâng cao

``` text
Python
Airflow
MinIO
Spark
Apache Iceberg
dbt
ClickHouse
Superset
MLflow
Great Expectations
Prometheus/Grafana
Docker Compose
```

Không nên triển khai stack nâng cao ngay từ tuần đầu.

------------------------------------------------------------------------

# 8. Data Lake Design

## 8.1. Bronze

Raw hoặc gần raw nhất.

``` text
s3://github-intelligence/
└── bronze/
    ├── gharchive/
    │   └── year=2026/
    │       └── month=10/
    │           └── day=20/
    │               ├── hour=00/
    │               ├── hour=01/
    │               └── ...
    └── github_api/
        └── repository_snapshot/
            └── snapshot_date=2026-10-20/
```

Yêu cầu:

-   Không mutate raw data.
-   Có ingestion metadata.
-   Có checksum/file size.
-   Có source timestamp.
-   Có ingestion timestamp.

## 8.2. Silver

Normalized datasets:

``` text
silver/
├── events/
├── repositories/
├── actors/
├── pushes/
├── commits/
├── stars/
├── forks/
├── issues/
├── issue_comments/
├── pull_requests/
├── pull_request_reviews/
└── releases/
```

Các bảng Silver phải:

-   Typed.
-   Deduplicated.
-   Standardized timestamps.
-   Có stable IDs.
-   Partition hợp lý.
-   Loại bỏ records không thuộc tracked repositories nếu scope giới hạn.

## 8.3. Gold

``` text
gold/
├── repository_daily_metrics/
├── repository_weekly_metrics/
├── repository_monthly_metrics/
├── contributor_daily_activity/
├── contributor_monthly_metrics/
├── contributor_cohorts/
├── ecosystem_daily_metrics/
├── repository_health/
├── repository_growth/
├── technology_momentum/
└── ml_features/
```

------------------------------------------------------------------------

# 9. Data Model

## 9.1. Dimensions

### dim_repository

``` text
repository_id
repository_name
owner_login
description
primary_language
topics
license
created_at
archived
fork
category
ecosystem
snapshot_date
```

### dim_actor

``` text
actor_id
actor_login
first_seen_at
last_seen_at
```

### dim_date

``` text
date
day
week
month
quarter
year
day_of_week
is_weekend
```

### dim_event_type

``` text
event_type_id
event_type_name
event_category
```

## 9.2. Facts

### fact_github_event

``` text
event_id
repository_id
actor_id
event_type
created_at
event_date
```

### fact_star

``` text
event_id
repository_id
actor_id
starred_at
```

### fact_fork

``` text
event_id
repository_id
actor_id
fork_repository_id
created_at
```

### fact_pull_request_event

``` text
event_id
repository_id
actor_id
pull_request_id
action
created_at
merged
```

### fact_issue_event

``` text
event_id
repository_id
actor_id
issue_id
action
created_at
```

------------------------------------------------------------------------

# 10. Gold Metrics

## 10.1. repository_daily_metrics

``` text
repository_id
date

event_count
push_events
commit_count

new_stars
new_forks

issues_opened
issues_closed

prs_opened
prs_closed
prs_merged

active_contributors
new_contributors

releases
```

## 10.2. Rolling metrics

``` text
stars_7d
stars_30d

star_velocity_7d
star_velocity_30d

contributors_7d
contributors_30d

commit_velocity_7d
commit_velocity_30d

fork_velocity_30d
issue_activity_30d
pr_activity_30d
```

------------------------------------------------------------------------

# 11. Application 1 --- Technology Radar

## Mục tiêu

Trả lời:

> Công nghệ/open-source ecosystem nào đang có developer momentum?

Categories:

``` text
ADOPT
TRIAL
ASSESS
WATCH
```

Có thể tính Technology Momentum Score:

``` text
momentum_score =
      w1 * normalized_star_growth
    + w2 * normalized_contributor_growth
    + w3 * normalized_commit_growth
    + w4 * normalized_fork_growth
    + w5 * normalized_repository_activity
```

Ví dụ weight ban đầu:

``` text
star growth         30%
contributor growth  25%
commit growth       20%
fork growth         15%
activity            10%
```

Dashboard:

-   Momentum ranking.
-   Momentum over time.
-   Fastest growing ecosystem.
-   Emerging projects.
-   Language trend.
-   Category comparison.

------------------------------------------------------------------------

# 12. Application 2 --- Repository Explorer

Trang detail cho từng repository.

Ví dụ:

``` text
Repository: duckdb/duckdb

Current metrics
------------------------
Stars gained 30d
Forks gained 30d
Active contributors
Commits 30d
PR merge rate
Issue close rate
Release frequency

Growth
------------------------
7d / 30d / 90d trends

Community
------------------------
New contributors
Returning contributors
Contributor concentration

Health
------------------------
Health score
Maintenance score
Bus factor proxy
```

Charts:

-   Stars gained over time.
-   Contributor activity.
-   Commit activity.
-   Issue opened/closed.
-   PR opened/merged.
-   Release timeline.

------------------------------------------------------------------------

# 13. Application 3 --- Repository Health Score

Health dimensions:

## Activity

-   Commits.
-   Push frequency.
-   Releases.
-   Active days.

## Community

-   Active contributors.
-   New contributors.
-   Returning contributors.
-   Contributor retention.

## Collaboration

-   PR merge rate.
-   Review activity.
-   Issue interaction.

## Maintenance

-   Issue close rate.
-   PR close/merge rate.
-   Release recency.

## Concentration Risk

Ví dụ:

``` text
top_1_contributor_share
top_5_contributor_share
```

Health score:

``` text
health_score =
    activity_score
  + community_score
  + collaboration_score
  + maintenance_score
  - concentration_risk
```

Cần document rõ đây là **project-defined heuristic**, không phải chuẩn
chính thức của GitHub.

------------------------------------------------------------------------

# 14. Application 4 --- Contributor Analytics

Metrics:

``` text
monthly_active_contributors
new_contributors
returning_contributors
contributor_growth
contributor_retention
contribution_frequency
```

## Cohort analysis

Cohort = tháng contributor xuất hiện lần đầu.

``` text
             M0    M1    M2    M3

2026-01      100   45    31    24
2026-02      120   50    36
2026-03       90   41
```

Ứng dụng:

-   So sánh community stickiness.
-   Tìm repository thu hút contributor tốt.
-   Tìm repository phụ thuộc vào core maintainers.

------------------------------------------------------------------------

# 15. Application 5 --- Ecosystem Comparison

Cho phép so sánh:

``` text
React vs Vue vs Svelte

Spark vs Flink

PostgreSQL vs DuckDB

TensorFlow vs PyTorch
```

Metrics:

-   Stars gained.
-   Contributors.
-   Commit activity.
-   Fork growth.
-   PR activity.
-   Issue activity.
-   Releases.
-   Momentum score.
-   Health score.

Quan trọng: ưu tiên **growth/velocity** thay vì total count để tránh
bias cho project lâu đời.

------------------------------------------------------------------------

# 16. Application 6 --- Trending Repository Detection

## Rule-based version

MVP có thể chưa cần ML:

``` text
trending_score =
      star_velocity_7d
    + contributor_growth_7d
    + fork_velocity_7d
    + activity_acceleration
```

So sánh:

``` text
velocity_7d vs velocity_previous_7d
```

để tìm acceleration.

## ML version

Features:

``` text
stars_7d
stars_30d
star_growth_rate
star_acceleration

forks_7d
fork_growth_rate

contributors_7d
contributors_30d
new_contributors

commits_7d
commits_30d

issues_30d
prs_30d
merge_rate

repo_age
language
category
```

Target có thể định nghĩa:

``` text
will_be_top_growth_repo_next_30d
```

hoặc regression:

``` text
future_star_growth_30d
```

Models:

-   Logistic Regression baseline.
-   Random Forest.
-   XGBoost/LightGBM nếu được phép.

Evaluation:

-   Precision@K.
-   Recall.
-   ROC-AUC cho classification.
-   MAE/RMSE cho regression.
-   Time-based train/test split.

Không random split time-series data.

------------------------------------------------------------------------

# 17. Application 7 --- Data Platform Operations Dashboard

Đây là một ứng dụng con rất đáng làm vì chứng minh tư duy DE.

Hiển thị:

``` text
Last successful ingestion
Files expected / downloaded
Rows processed
Rows rejected
Pipeline duration
Data freshness
Duplicate count
Schema errors
Partition status
```

Ví dụ:

``` text
2026-10-20

Expected GH Archive files: 24
Downloaded:                24
Valid:                     24

Events read:               72,302,121
Relevant events:            1,820,314
Rejected:                         312

Pipeline duration:              18m42s
Status:                        HEALTHY
```

------------------------------------------------------------------------

# 18. Incremental Processing

Mỗi DAG run xử lý một logical date.

``` text
github_daily_pipeline
    logical_date = 2026-10-20
```

Tasks:

``` text
determine_files
      |
      v
download_24_hours
      |
      v
validate_raw_files
      |
      v
process_bronze
      |
      v
build_silver
      |
      v
refresh_metadata
      |
      v
build_gold
      |
      v
run_quality_tests
      |
      v
publish_serving_tables
```

Chỉ xử lý partition tương ứng.

------------------------------------------------------------------------

# 19. Backfill

Đây nên là một feature chính của project.

Ví dụ:

``` text
airflow dags backfill github_daily_pipeline \
  --start-date 2026-01-01 \
  --end-date 2026-06-30
```

Mỗi logical date độc lập:

``` text
2026-01-01 -> partitions 2026-01-01
2026-01-02 -> partitions 2026-01-02
...
```

Yêu cầu:

-   Idempotent.
-   Không duplicate.
-   Safe rerun.
-   Có checkpoint/status.
-   Không overwrite unrelated partitions.

Demo tốt:

1.  Ban đầu warehouse có tháng 06--10.
2.  Dashboard thiếu lịch sử đầu năm.
3.  Trigger backfill tháng 01--05.
4.  Pipeline xử lý historical partitions.
5.  Dashboard tự có historical trends.

------------------------------------------------------------------------

# 20. Idempotency

Nếu DAG ngày `2026-10-20` chạy hai lần:

``` text
run #1
run #2
```

kết quả cuối phải giống nhau.

Các chiến lược:

-   Deterministic partition paths.
-   Deduplicate theo event ID.
-   Atomic partition replacement.
-   MERGE/upsert khi cần.
-   Không append mù vào Gold table.
-   Track processed files.

------------------------------------------------------------------------

# 21. Metadata / Control Tables

## ingestion_run

``` text
run_id
source
logical_date
started_at
finished_at
status
files_expected
files_downloaded
rows_read
rows_written
error_message
```

## source_file

``` text
source_file_id
url
logical_date
hour
checksum
file_size
downloaded_at
processing_status
```

## repository_registry

``` text
repository_id
repository_name
category
ecosystem
enabled
tracking_start_date
```

## data_quality_result

``` text
run_id
test_name
table_name
status
observed_value
expected_value
created_at
```

------------------------------------------------------------------------

# 22. Data Quality

## Bronze checks

-   File exists.
-   File size \> 0.
-   gzip readable.
-   JSON parse success rate.
-   24 hourly files expected/day.

## Silver checks

``` text
event_id IS NOT NULL
repository_id IS NOT NULL
created_at IS NOT NULL
```

-   Unique event ID.
-   Valid event type.
-   Valid timestamps.
-   No impossible future timestamps.

## Gold checks

``` text
new_stars >= 0
new_forks >= 0
active_contributors >= 0
commits >= 0
```

Logical checks:

``` text
prs_merged <= prs_closed + acceptable_edge_cases
```

## Freshness

``` text
max(event_date) >= expected_processing_date
```

## Volume anomaly

Compare:

``` text
today_event_count
vs
rolling_7d_average
```

Alert nếu lệch quá lớn.

------------------------------------------------------------------------

# 23. Schema Evolution

GH Archive payload có thể thay đổi.

Thiết kế:

-   Bronze giữ raw payload.
-   Silver chỉ extract fields cần.
-   Unknown fields không làm pipeline fail.
-   Nullable columns cho optional fields.
-   Có schema version nếu cần.

Nếu dùng Iceberg:

-   Schema evolution dễ quản lý hơn.
-   Partition evolution.
-   Snapshot/time travel là bonus.

Iceberg nên là stretch goal, không phải blocker.

------------------------------------------------------------------------

# 24. Partition Strategy

Bronze:

``` text
year/month/day/hour
```

Silver events:

``` text
event_date
```

Một số event-specific table:

``` text
event_date
```

Gold:

``` text
date
```

Không partition theo `repository_id` nếu số repo lớn và file nhỏ vì dễ
tạo small-file problem.

------------------------------------------------------------------------

# 25. File Format

Raw:

``` text
JSON.gz
```

Processed:

``` text
Parquet + Snappy
```

Lợi ích:

-   Columnar.
-   Predicate pushdown.
-   Compression.
-   Spark-friendly.
-   Analytics-friendly.

------------------------------------------------------------------------

# 26. Orchestration với Airflow

DAGs đề xuất:

## github_daily_ingestion

``` text
download
validate
register files
```

## github_daily_transform

``` text
bronze_to_silver
silver_quality
```

## github_daily_analytics

``` text
dbt_run
dbt_test
publish_clickhouse
```

## github_metadata_refresh

Chạy daily hoặc weekly.

``` text
repository_registry
      |
      v
GitHub API
      |
      v
repository_snapshot
```

## github_ml_training

Chạy weekly hoặc manual.

``` text
build_features
train
evaluate
register_model
```

------------------------------------------------------------------------

# 27. Spark Jobs

## Job 1 --- Filter tracked repositories

Input:

``` text
GH Archive raw events
```

Filter:

``` text
repo.name IN repository_registry
```

Output:

``` text
bronze/relevant_events
```

## Job 2 --- Normalize common events

Extract:

``` text
event_id
event_type
actor_id
actor_login
repo_id
repo_name
created_at
payload
```

## Job 3 --- Event-specific normalization

``` text
WatchEvent       -> silver/stars
ForkEvent        -> silver/forks
PushEvent        -> silver/pushes
IssuesEvent      -> silver/issues
PullRequestEvent -> silver/pull_requests
ReleaseEvent     -> silver/releases
```

## Job 4 --- Daily aggregation

Generate repository/day metrics.

------------------------------------------------------------------------

# 28. dbt Models

Suggested structure:

``` text
dbt/
├── models/
│   ├── staging/
│   │   ├── stg_events.sql
│   │   ├── stg_repositories.sql
│   │   └── stg_actors.sql
│   │
│   ├── intermediate/
│   │   ├── int_repository_activity.sql
│   │   ├── int_contributor_activity.sql
│   │   └── int_growth_metrics.sql
│   │
│   └── marts/
│       ├── mart_repository_daily.sql
│       ├── mart_repository_health.sql
│       ├── mart_ecosystem_trends.sql
│       ├── mart_contributor_cohort.sql
│       └── mart_ml_features.sql
```

Tests:

``` yaml
unique
not_null
relationships
accepted_values
```

------------------------------------------------------------------------

# 29. ClickHouse Serving Layer

ClickHouse phù hợp cho:

-   Time-series aggregation.
-   Dashboard queries.
-   Ranking.
-   Large analytical scans.

Tables:

``` text
repository_daily_metrics
repository_health
ecosystem_daily_metrics
contributor_monthly_metrics
technology_momentum
trending_predictions
```

Nếu scope nhỏ, PostgreSQL đủ cho MVP.

------------------------------------------------------------------------

# 30. Dashboard Structure

## Dashboard 1 --- Executive Overview

KPIs:

``` text
Tracked repositories
Events processed
Active contributors
Stars gained 30d
Fastest growing ecosystem
Top emerging repository
```

Charts:

-   Activity trend.
-   Top growth repositories.
-   Ecosystem momentum.
-   Language activity.

## Dashboard 2 --- Technology Radar

-   Momentum ranking.
-   Category filters.
-   Ecosystem comparison.
-   Growth scatter plot.
-   Radar classification.

## Dashboard 3 --- Repository Health

-   Health score.
-   Activity.
-   Community.
-   Maintenance.
-   Contributor concentration.

## Dashboard 4 --- Contributor Analytics

-   MAU contributors.
-   New/returning.
-   Cohort retention.
-   Top contributors.
-   Concentration.

## Dashboard 5 --- Trending

-   Trending score.
-   ML probability.
-   Growth acceleration.
-   Emerging repos.

## Dashboard 6 --- Data Platform Health

-   DAG status.
-   Freshness.
-   Row counts.
-   Quality tests.
-   Processing time.

------------------------------------------------------------------------

# 31. ML Pipeline

``` text
Gold analytics
      |
      v
Feature generation
      |
      v
Point-in-time dataset
      |
      v
Train / validation / test
      |
      v
Model training
      |
      v
MLflow
      |
      v
Batch prediction
      |
      v
trending_predictions
      |
      v
Dashboard
```

Quan trọng: tránh data leakage.

Feature tại ngày `T` chỉ được dùng dữ liệu `<= T`.

Target có thể dựa vào growth từ:

``` text
T+1 ... T+30
```

------------------------------------------------------------------------

# 32. Repository Ranking

Có thể xây nhiều score độc lập:

``` text
growth_score
health_score
community_score
momentum_score
trending_probability
```

Không nên gộp mọi thứ thành một score duy nhất.

Ví dụ:

  Repository     Growth   Health   Community   Trend Prob.
  ------------ -------- -------- ----------- -------------
  repo A             92       73          81          0.91
  repo B             61       94          90          0.42
  repo C             85       51          44          0.83

Điều này cho insight tốt hơn.

------------------------------------------------------------------------

# 33. Optional Graph Analytics

Stretch goal.

Graph:

``` text
Developer --contributes_to--> Repository
Repository --uses_language--> Language
Repository --belongs_to--> Ecosystem
```

Có thể dùng Neo4j.

Use cases:

-   Contributor overlap.
-   Repository similarity.
-   Ecosystem communities.
-   Influential developers.
-   Cross-ecosystem contributors.

Không nên ưu tiên trước core pipeline.

------------------------------------------------------------------------

# 34. Project Repository Structure

``` text
github-intelligence/
│
├── README.md
├── docker-compose.yml
├── Makefile
├── .env.example
│
├── airflow/
│   ├── dags/
│   └── plugins/
│
├── ingestion/
│   ├── gharchive/
│   └── github_api/
│
├── spark/
│   ├── jobs/
│   ├── common/
│   └── tests/
│
├── dbt/
│   ├── models/
│   ├── tests/
│   ├── macros/
│   └── seeds/
│
├── ml/
│   ├── features/
│   ├── training/
│   ├── inference/
│   └── evaluation/
│
├── infra/
│   ├── minio/
│   ├── clickhouse/
│   ├── airflow/
│   └── superset/
│
├── dashboards/
│
├── tests/
│
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── metrics.md
│   ├── runbook.md
│   └── adr/
│
└── scripts/
```

------------------------------------------------------------------------

# 35. Development Phases

## Phase 0 --- Discovery & Design

### Tasks

-   [ ] Chốt project problem statement.
-   [ ] Chốt repository categories.
-   [ ] Chọn 100 repositories cho prototype.
-   [ ] Khảo sát GH Archive schema.
-   [ ] Khảo sát GitHub API.
-   [ ] Xác định metrics.
-   [ ] Vẽ architecture.
-   [ ] Thiết kế data model.
-   [ ] Thiết kế partition strategy.
-   [ ] Viết ADR cho lựa chọn công nghệ.

### Deliverable

-   Architecture diagram.
-   Data dictionary.
-   Source analysis.
-   Project backlog.

------------------------------------------------------------------------

## Phase 1 --- Local Infrastructure

### Tasks

-   [ ] Docker Compose.
-   [ ] MinIO.
-   [ ] Airflow.
-   [ ] Spark.
-   [ ] PostgreSQL/ClickHouse.
-   [ ] Superset.
-   [ ] Network/volumes.
-   [ ] `.env.example`.
-   [ ] Health checks.
-   [ ] Makefile.

Commands mong muốn:

``` text
make up
make down
make bootstrap
make test
```

### Definition of Done

Clone repository → chạy một số command → toàn bộ stack hoạt động.

------------------------------------------------------------------------

## Phase 2 --- GH Archive Ingestion

### Tasks

-   [ ] Build URL generator.
-   [ ] Download hourly file.
-   [ ] Retry.
-   [ ] Timeout.
-   [ ] Checksum.
-   [ ] Validate gzip.
-   [ ] Store MinIO.
-   [ ] Register source file.
-   [ ] Airflow daily DAG.
-   [ ] Rerun-safe logic.

### Definition of Done

Một logical date có thể ingest đủ 24 files và biết file nào thành
công/thất bại.

------------------------------------------------------------------------

## Phase 3 --- Repository Filtering

### Tasks

-   [ ] Tạo repository registry.
-   [ ] Load registry.
-   [ ] Spark đọc raw files.
-   [ ] Filter target repositories.
-   [ ] Persist relevant events.
-   [ ] Metrics rows in/out.
-   [ ] Unit tests.

### Definition of Done

Có thể xử lý một ngày GH Archive và chỉ giữ events thuộc scope.

------------------------------------------------------------------------

## Phase 4 --- Silver Normalization

### Tasks

-   [ ] Common event schema.
-   [ ] WatchEvent parser.
-   [ ] ForkEvent parser.
-   [ ] PushEvent parser.
-   [ ] IssuesEvent parser.
-   [ ] PullRequestEvent parser.
-   [ ] ReleaseEvent parser.
-   [ ] Deduplication.
-   [ ] Timestamp normalization.
-   [ ] Partition output.
-   [ ] Schema tests.

### Definition of Done

Có các Silver tables typed và query được.

------------------------------------------------------------------------

## Phase 5 --- Metadata Enrichment

### Tasks

-   [ ] GitHub API client.
-   [ ] Authentication bằng environment secret.
-   [ ] Rate-limit handling.
-   [ ] Repository metadata fetch.
-   [ ] Topic/language/license.
-   [ ] Snapshot history.
-   [ ] Airflow metadata DAG.
-   [ ] API error retry.

### Definition of Done

Mỗi tracked repository có metadata snapshot.

------------------------------------------------------------------------

## Phase 6 --- Gold Analytics

### Tasks

-   [ ] repository_daily_metrics.
-   [ ] rolling 7d.
-   [ ] rolling 30d.
-   [ ] growth metrics.
-   [ ] contributor metrics.
-   [ ] ecosystem metrics.
-   [ ] health metrics.
-   [ ] dbt tests.
-   [ ] dbt docs.

### Definition of Done

Dashboard không cần query raw/Silver.

------------------------------------------------------------------------

## Phase 7 --- Backfill Engine

### Tasks

-   [ ] Logical-date based processing.
-   [ ] Partition idempotency.
-   [ ] Backfill historical range.
-   [ ] Retry failed dates.
-   [ ] Prevent duplicate rows.
-   [ ] Track status.
-   [ ] Measure processing performance.

### Definition of Done

Có thể backfill một tháng bất kỳ bằng command/DAG mà không sửa code.

------------------------------------------------------------------------

## Phase 8 --- Serving Layer

### Tasks

-   [ ] ClickHouse schema.
-   [ ] Load Gold marts.
-   [ ] Incremental publish.
-   [ ] Query benchmarks.
-   [ ] Index/order key design.
-   [ ] Dashboard connection.

### Definition of Done

Các dashboard query phổ biến có latency chấp nhận được.

------------------------------------------------------------------------

## Phase 9 --- Dashboard

### Tasks

-   [ ] Executive overview.
-   [ ] Technology Radar.
-   [ ] Repository Explorer.
-   [ ] Repository Health.
-   [ ] Contributor Analytics.
-   [ ] Ecosystem Comparison.
-   [ ] Trending.
-   [ ] Pipeline Health.

### Definition of Done

Dashboard kể được một câu chuyện hoàn chỉnh, không chỉ là tập hợp chart.

------------------------------------------------------------------------

## Phase 10 --- ML

### Tasks

-   [ ] Define target.
-   [ ] Feature table.
-   [ ] Point-in-time correctness.
-   [ ] Time split.
-   [ ] Baseline model.
-   [ ] Advanced model.
-   [ ] Evaluation.
-   [ ] MLflow tracking.
-   [ ] Batch inference.
-   [ ] Prediction table.
-   [ ] Dashboard integration.

### Definition of Done

Prediction được tạo từ chính Gold layer và xuất hiện trên dashboard.

------------------------------------------------------------------------

## Phase 11 --- Quality & Observability

### Tasks

-   [ ] Bronze checks.
-   [ ] Silver tests.
-   [ ] Gold tests.
-   [ ] Freshness.
-   [ ] Volume anomaly.
-   [ ] Pipeline metrics.
-   [ ] Failure handling.
-   [ ] Operational dashboard.

------------------------------------------------------------------------

## Phase 12 --- Finalization

### Tasks

-   [ ] README.
-   [ ] Architecture documentation.
-   [ ] Data dictionary.
-   [ ] Metric definitions.
-   [ ] Runbook.
-   [ ] Demo script.
-   [ ] Seed/demo data.
-   [ ] Reproducible setup.
-   [ ] Presentation.
-   [ ] Final report.

------------------------------------------------------------------------

# 36. Suggested 10-Week Timeline

## Week 1 --- Design

-   Requirements.
-   Dataset exploration.
-   Architecture.
-   Data model.
-   Repository registry.

## Week 2 --- Infrastructure + Ingestion

-   Docker.
-   MinIO.
-   Airflow.
-   GH Archive downloader.

## Week 3 --- Spark Bronze/Silver

-   Raw parsing.
-   Repository filtering.
-   Event normalization.

## Week 4 --- Metadata + Data Quality

-   GitHub API.
-   Repository snapshots.
-   Validation.

## Week 5 --- Gold Modeling

-   dbt.
-   Daily metrics.
-   Rolling metrics.
-   Growth metrics.

## Week 6 --- Backfill + Idempotency

-   Historical processing.
-   Rerun.
-   Failure recovery.

## Week 7 --- Analytics Serving

-   ClickHouse.
-   Superset.
-   Core dashboards.

## Week 8 --- Advanced Analytics

-   Health score.
-   Momentum.
-   Contributor cohorts.
-   Ecosystem comparison.

## Week 9 --- ML

-   Feature pipeline.
-   Model.
-   MLflow.
-   Predictions.

## Week 10 --- Polish

-   Tests.
-   Performance.
-   Documentation.
-   Demo.
-   Slides/report.

------------------------------------------------------------------------

# 37. MVP vs Stretch Goals

## MVP --- bắt buộc

``` text
GH Archive
    |
Airflow
    |
MinIO
    |
Spark
    |
Silver
    |
dbt
    |
Gold
    |
PostgreSQL/ClickHouse
    |
Superset
```

Features:

-   Daily ingestion.
-   Historical backfill.
-   Incremental processing.
-   4--6 event types.
-   Repository daily metrics.
-   Growth analytics.
-   Dashboard.
-   Data quality.

## Strong Version

Thêm:

-   GitHub API enrichment.
-   Contributor cohort.
-   Repository health.
-   Technology momentum.
-   ClickHouse.
-   ML prediction.
-   MLflow.

## Stretch

Thêm:

-   Iceberg.
-   Graph analytics.
-   Neo4j.
-   Prometheus/Grafana.
-   CI/CD.
-   Cloud deployment.

------------------------------------------------------------------------

# 38. Những thứ không nên làm quá sớm

Không nên bắt đầu bằng:

-   Kafka.
-   Flink.
-   Kubernetes.
-   Neo4j.
-   Iceberg.
-   Great Expectations.
-   MLflow.
-   Deep Learning.

Các công nghệ trên không xấu, nhưng có thể làm scope nổ.

Ưu tiên:

``` text
correct pipeline
>
idempotency
>
incremental processing
>
backfill
>
data quality
>
good data model
>
useful analytics
>
extra infrastructure
```

------------------------------------------------------------------------

# 39. Các câu hỏi kỹ thuật đồ án nên trả lời được

## Ingestion

-   Nếu một hourly file download fail thì sao?
-   Làm sao biết một ngày đủ 24 files?
-   Rerun có download lại không?
-   Làm sao detect corrupted file?

## Processing

-   Vì sao dùng Spark?
-   Partition như thế nào?
-   Vì sao dùng Parquet?
-   Làm sao xử lý duplicate?
-   Làm sao xử lý schema khác nhau giữa event types?

## Storage

-   Vì sao cần Bronze/Silver/Gold?
-   Vì sao raw data immutable?
-   Vì sao MinIO thay vì database?

## Orchestration

-   Airflow logical date được dùng thế nào?
-   Backfill hoạt động ra sao?
-   Task nào retry được?
-   Dependency giữa các task?

## Modeling

-   Fact và dimension là gì?
-   Vì sao dashboard query Gold?
-   Metric nào additive/non-additive?

## Quality

-   Pipeline biết dữ liệu sai bằng cách nào?
-   Freshness kiểm tra ra sao?
-   Volume anomaly xử lý thế nào?

## ML

-   Feature được build ở đâu?
-   Làm sao tránh leakage?
-   Vì sao time split thay random split?

------------------------------------------------------------------------

# 40. Demo Scenario

Một demo 8--12 phút có thể đi như sau.

## Step 1 --- Giới thiệu vấn đề

> Có hàng triệu open-source repositories. Total stars không đủ để biết
> công nghệ nào thực sự đang tăng trưởng hoặc community nào khỏe.

## Step 2 --- Show architecture

Giải thích:

``` text
GH Archive -> Lake -> Spark -> Gold -> Analytics/ML
```

## Step 3 --- Show Airflow

Mở DAG:

``` text
github_daily_pipeline
```

Show task graph.

## Step 4 --- Show MinIO

``` text
bronze/year=...
silver/...
gold/...
```

## Step 5 --- Show backfill

Trigger historical date/range.

## Step 6 --- Show data quality

Show successful tests.

## Step 7 --- Dashboard

Ví dụ:

> "Trong 30 ngày gần nhất, repository X có total stars thấp hơn Y nhưng
> growth velocity cao gấp 4 lần."

## Step 8 --- Repository health

So sánh hai repository.

## Step 9 --- ML

Show emerging repositories prediction.

## Step 10 --- Kết luận

Nhấn mạnh:

-   Reproducible.
-   Incremental.
-   Backfillable.
-   Tested.
-   Analytics-ready.
-   ML-ready.

------------------------------------------------------------------------

# 41. Evaluation Criteria đề xuất

Nếu tự đánh giá project:

  Area                       Weight
  ------------------------ --------
  Data ingestion                10%
  Storage/lake design           10%
  Batch processing              15%
  Incremental + backfill        15%
  Data modeling                 10%
  Data quality                  10%
  Analytics usefulness          10%
  Dashboard                      5%
  ML                             5%
  Reproducibility                5%
  Documentation/demo             5%

Điều này cố tình đặt trọng tâm vào **Data Engineering**, không phải ML.

------------------------------------------------------------------------

# 42. Performance Experiments

Một phần báo cáo có thể benchmark:

## JSON vs Parquet

Đo:

-   Storage size.
-   Scan time.
-   Aggregation time.

## Partition pruning

Query:

``` text
one day
vs
one month
```

## PostgreSQL vs ClickHouse

Query:

``` text
top repositories by star growth over 90 days
```

## Spark parallelism

Đo processing time với số partitions khác nhau.

Phần này rất tốt cho báo cáo vì cho thấy quyết định công nghệ có
evidence.

------------------------------------------------------------------------

# 43. Failure Scenarios nên test

-   Missing hourly file.
-   Corrupted gzip.
-   Duplicate event.
-   GitHub API rate limit.
-   API timeout.
-   Spark job fail giữa chừng.
-   Gold build fail.
-   DAG rerun.
-   Historical partition đã tồn tại.
-   Unknown event type.
-   Missing optional payload field.

------------------------------------------------------------------------

# 44. Security / Configuration

Không commit:

``` text
GitHub token
password
secret key
```

Dùng:

``` text
.env
Airflow Connection
Docker secret
```

Repository chỉ có:

``` text
.env.example
```

------------------------------------------------------------------------

# 45. Testing Strategy

## Unit tests

-   URL builder.
-   Event parser.
-   Score functions.
-   Date partition logic.

## Integration tests

``` text
sample GH Archive
    ->
Spark transform
    ->
expected Silver
```

## Data tests

dbt:

``` text
not_null
unique
relationships
accepted_values
```

## End-to-end smoke test

``` text
sample day
   ->
ingestion
   ->
Silver
   ->
Gold
   ->
serving
```

------------------------------------------------------------------------

# 46. Documentation Assets

Nên có:

``` text
docs/
├── architecture.md
├── source-data.md
├── data-model.md
├── metrics.md
├── data-quality.md
├── backfill.md
├── operations.md
├── ml.md
└── demo.md
```

## ADR

Architecture Decision Records:

``` text
ADR-001: Why batch instead of streaming
ADR-002: Why MinIO
ADR-003: Why Parquet
ADR-004: Why Spark
ADR-005: Why ClickHouse
ADR-006: Partition strategy
```

Đây là điểm cộng lớn về engineering maturity.

------------------------------------------------------------------------

# 47. Key Design Decisions

## Batch-first thay vì realtime

Lý do:

-   Use case không cần sub-second latency.
-   GH Archive naturally hỗ trợ hourly historical files.
-   Backfill quan trọng hơn realtime.
-   Giảm operational complexity.
-   Cho phép tập trung vào correctness.

## Không dùng Kafka trong MVP

Kafka chỉ hợp lý nếu sau này muốn:

-   Live GitHub Events.
-   Near-real-time dashboard.
-   Hybrid batch/stream architecture.

Không cần thêm Kafka chỉ để stack trông phức tạp.

## ML là downstream consumer

ML không được trở thành core của project.

Core:

``` text
reliable data platform
```

ML:

``` text
one application consuming trusted Gold data
```

------------------------------------------------------------------------

# 48. Product Narrative

Tên kỹ thuật:

> GitHub Open Source Intelligence Platform

Tên demo/product có thể là:

-   OpenPulse
-   RepoPulse
-   OSS Radar
-   GitPulse
-   OpenSource Radar
-   RepoScope
-   OSScope

Value proposition:

> A batch data platform that transforms public GitHub activity into
> actionable insights about open-source growth, community health and
> technology momentum.

------------------------------------------------------------------------

# 49. Final Recommended Scope

Nếu nhóm 2--4 người và có khoảng 8--12 tuần, scope hợp lý nhất:

## Data

-   500--1,000 repositories.
-   6--12 tháng.
-   6 event types chính.

## Pipeline

-   Airflow.
-   MinIO.
-   Spark.
-   Parquet.
-   dbt.
-   ClickHouse/PostgreSQL.

## Applications

1.  Technology Radar.
2.  Repository Explorer.
3.  Growth Analytics.
4.  Repository Health.
5.  Contributor Analytics.
6.  Pipeline Health.

## ML

Một model duy nhất:

> Predict 30-day repository growth / emerging repository.

## Engineering features

-   Incremental processing.
-   Backfill.
-   Idempotency.
-   Data quality.
-   Metadata tracking.
-   Docker Compose.
-   Automated tests.

Đây là scope đủ sâu nhưng vẫn có khả năng hoàn thành.

------------------------------------------------------------------------

# 50. Priority Backlog

## P0 --- phải có

-   [ ] GH Archive ingestion.
-   [ ] MinIO raw storage.
-   [ ] Airflow orchestration.
-   [ ] Spark normalization.
-   [ ] Incremental partitions.
-   [ ] Backfill.
-   [ ] Idempotency.
-   [ ] Repository daily metrics.
-   [ ] dbt tests.
-   [ ] Dashboard.
-   [ ] Docker Compose.
-   [ ] Documentation.

## P1 --- nên có

-   [ ] GitHub metadata API.
-   [ ] Contributor metrics.
-   [ ] Growth velocity.
-   [ ] Ecosystem comparison.
-   [ ] Repository health.
-   [ ] Pipeline health dashboard.
-   [ ] ClickHouse.

## P2 --- nếu còn thời gian

-   [ ] ML trending prediction.
-   [ ] MLflow.
-   [ ] Iceberg.
-   [ ] Advanced anomaly detection.

## P3 --- stretch

-   [ ] Neo4j.
-   [ ] Graph analytics.
-   [ ] Cloud deployment.
-   [ ] CI/CD.
-   [ ] Near-realtime ingestion.

------------------------------------------------------------------------

# 51. Suggested First Sprint

Để tránh over-engineering, sprint đầu chỉ cần chứng minh vertical slice:

``` text
1 day GH Archive
      |
      v
Python downloader
      |
      v
MinIO
      |
      v
Spark
      |
      v
WatchEvent + PushEvent
      |
      v
repository_daily_metrics
      |
      v
PostgreSQL
      |
      v
one simple dashboard
```

Tasks:

-   [ ] Chọn 50 repositories.
-   [ ] Download 1 ngày GH Archive.
-   [ ] Upload raw files vào MinIO.
-   [ ] Spark filter repositories.
-   [ ] Normalize `WatchEvent`.
-   [ ] Normalize `PushEvent`.
-   [ ] Aggregate theo repo/day.
-   [ ] Load vào PostgreSQL.
-   [ ] Vẽ chart top repo theo stars gained.
-   [ ] Đưa flow vào Airflow.

Sau khi vertical slice chạy end-to-end mới mở rộng số event, historical
range và các service khác.

------------------------------------------------------------------------

# 52. Definition of Project Success

Project được xem là thành công khi có thể chứng minh:

> Từ một ngày/range bất kỳ trong quá khứ, hệ thống có thể tự động lấy
> GitHub event data, validate, lưu raw data, xử lý incremental,
> normalize heterogeneous events, xây analytical datasets, chạy quality
> checks, publish vào analytics database và cập nhật dashboard mà không
> cần thao tác thủ công.

Ngoài ra:

> Hệ thống có thể backfill dữ liệu lịch sử một cách idempotent và các
> ứng dụng analytics/ML chỉ phụ thuộc vào curated Gold layer.

Đây là hai tiêu chí quan trọng nhất của toàn bộ đồ án.

------------------------------------------------------------------------

# 53. North-star Demo

Demo lý tưởng:

``` text
                     Historical GitHub
                            |
                            v
                      [ Airflow DAG ]
                            |
              +-------------+-------------+
              |                           |
              v                           v
         [ MinIO ]                   [ Run metadata ]
              |
              v
          [ Spark ]
              |
              v
       Bronze -> Silver
              |
              v
           [ dbt ]
              |
              v
            Gold
              |
       +------+-------+
       |              |
       v              v
 [ ClickHouse ]    [ MLflow ]
       |              |
       v              v
 [ Superset ]   [ Predictions ]
       |
       v

"Which open-source technologies are gaining momentum,
 and which repositories are healthy enough to sustain it?"
```

Câu hỏi cuối này có thể dùng làm **central research/product question**
của đồ án.

------------------------------------------------------------------------

# 54. Tài nguyên tham khảo chính

-   GH Archive: https://www.gharchive.org/
-   GitHub REST API: https://docs.github.com/en/rest
-   GitHub GraphQL API: https://docs.github.com/en/graphql
-   Apache Airflow: https://airflow.apache.org/
-   Apache Spark: https://spark.apache.org/
-   MinIO: https://min.io/
-   Apache Parquet: https://parquet.apache.org/
-   Apache Iceberg: https://iceberg.apache.org/
-   dbt: https://www.getdbt.com/
-   ClickHouse: https://clickhouse.com/
-   Apache Superset: https://superset.apache.org/
-   MLflow: https://mlflow.org/
-   Great Expectations: https://greatexpectations.io/

------------------------------------------------------------------------

# 55. Kết luận

Đề tài nên được nhìn như một **mini production-grade analytical data
platform**, không phải một dashboard GitHub.

Trọng tâm kỹ thuật:

``` text
Data ingestion
      +
Data lake
      +
Batch processing
      +
Incremental computation
      +
Historical backfill
      +
Idempotency
      +
Data modeling
      +
Data quality
      +
Analytics serving
```

Các ứng dụng như Technology Radar, Repository Health, Contributor
Analytics và Trending Prediction là lớp chứng minh rằng pipeline tạo ra
dữ liệu có giá trị.

Nếu phải ưu tiên, thứ tự nên là:

``` text
Pipeline correctness
    >
Backfill & idempotency
    >
Data model
    >
Data quality
    >
Useful analytics
    >
Dashboard polish
    >
ML
    >
Extra technologies
```

Điều này giữ cho đồ án đúng trọng tâm **Data Engineering**, đồng thời
vẫn tạo được một sản phẩm cuối đủ trực quan và thú vị để demo.
