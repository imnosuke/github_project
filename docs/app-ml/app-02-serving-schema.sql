-- Isolated APP-02 serving schema. The producer writes the manifest last.
CREATE DATABASE IF NOT EXISTS app_serving;

CREATE TABLE IF NOT EXISTS app_serving.app_publications
(
    publication_id String,
    contract_version String,
    published_at String,
    expected_complete_through Nullable(Date),
    start_date Date,
    end_date Date
)
ENGINE = MergeTree ORDER BY (published_at, publication_id);

CREATE TABLE IF NOT EXISTS app_serving.repository_registry
(
    publication_id String, repository_id Int64, repository_name String,
    tracking_start_date Date, tracking_end_date Nullable(Date),
    category Nullable(String), ecosystem Nullable(String)
)
ENGINE = MergeTree ORDER BY (publication_id, repository_id, tracking_start_date);

CREATE TABLE IF NOT EXISTS app_serving.repository_metadata
(
    publication_id String, repository_id Int64, snapshot_date Date, observed_at String,
    repository_name String, description Nullable(String), primary_language Nullable(String),
    topics Nullable(String), license Nullable(String), archived Nullable(Bool), is_fork Nullable(Bool),
    created_at Nullable(String), current_stars Nullable(Int64), current_forks Nullable(Int64)
)
ENGINE = MergeTree ORDER BY (publication_id, repository_id, snapshot_date);

CREATE TABLE IF NOT EXISTS app_serving.daily_data_status
(
    publication_id String, date Date, status LowCardinality(String),
    expected_files Int64, processed_files Int64, quality_passed Bool,
    published_at Nullable(String), reason Nullable(String)
)
ENGINE = MergeTree ORDER BY (publication_id, date);

CREATE TABLE IF NOT EXISTS app_serving.repository_daily_metrics
(
    publication_id String, repository_id Int64, date Date,
    total_events Nullable(Int64), star_events Nullable(Int64), fork_events Nullable(Int64),
    push_events Nullable(Int64), commits_pushed Nullable(Int64),
    prs_opened Nullable(Int64), prs_merged Nullable(Int64), prs_closed_unmerged Nullable(Int64),
    issues_opened Nullable(Int64), issues_closed Nullable(Int64), issue_comments Nullable(Int64),
    unique_actors Nullable(Int64), unique_human_actors Nullable(Int64), active_contributors Nullable(Int64)
)
ENGINE = MergeTree ORDER BY (publication_id, date, repository_id);
