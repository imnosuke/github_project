{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='event_date',
        engine='ReplacingMergeTree(_ingested_at)',
        order_by='(event_date, event_type, event_id)'
    )
}}

WITH deduplicated_bronze AS (
    SELECT
        event_id,
        event_type,
        public AS is_public,

        -- Chuẩn hóa thời gian
        parseDateTimeBestEffortOrZero(created_at, 'UTC') AS event_timestamp,
        toDate(parseDateTimeBestEffortOrZero(created_at, 'UTC')) AS event_date,
        toHour(parseDateTimeBestEffortOrZero(created_at, 'UTC')) AS event_hour,

        -- Chuẩn hóa thông tin Actor (Lập trình viên)
        ifNull(actor_id, 0) AS actor_id,
        ifNull(nullIf(actor_login, ''), 'anonymous') AS actor_login,
        endsWith(lower(ifNull(actor_login, '')), '[bot]') AS is_bot,

        -- Chuẩn hóa thông tin Repository (owner/repo)
        ifNull(repo_id, 0) AS repo_id,
        ifNull(repo_name, '') AS repo_full_name,
        splitByChar('/', ifNull(repo_name, ''))[1] AS repo_owner,
        if(
            length(splitByChar('/', ifNull(repo_name, ''))) >= 2,
            splitByChar('/', ifNull(repo_name, ''))[2],
            ''
        ) AS repo_short_name,

        -- Chuẩn hóa thông tin Organization
        org_id,
        nullIf(org_login, '') AS org_login,

        -- Bóc tách các trường nghiệp vụ từ payload_json ngay khi đọc streaming để không giữ chuỗi JSON nặng trong RAM khi khử trùng
        nullIf(JSONExtractString(payload_json, 'action'), '') AS action,
        nullIf(JSONExtractString(payload_json, 'ref'), '') AS git_ref,
        nullIf(JSONExtractString(payload_json, 'ref_type'), '') AS git_ref_type,

        -- Thông tin PushEvent
        JSONExtractInt(payload_json, 'size') AS push_commit_count,
        JSONExtractInt(payload_json, 'distinct_size') AS push_distinct_commit_count,

        -- Thông tin PullRequestEvent
        JSONExtractInt(payload_json, 'pull_request', 'number') AS pr_number,
        nullIf(JSONExtractString(payload_json, 'pull_request', 'title'), '') AS pr_title,
        nullIf(JSONExtractString(payload_json, 'pull_request', 'state'), '') AS pr_state,
        CASE JSONExtractRaw(payload_json, 'pull_request', 'merged')
            WHEN 'true' THEN true
            WHEN 'false' THEN false
            ELSE NULL
        END AS pr_merged,

        -- Thông tin IssuesEvent
        JSONExtractInt(payload_json, 'issue', 'number') AS issue_number,
        nullIf(JSONExtractString(payload_json, 'issue', 'title'), '') AS issue_title,
        nullIf(JSONExtractString(payload_json, 'issue', 'state'), '') AS issue_state,

        -- Metadata truy vết
        _source_file,
        _ingested_at
    FROM {{ source('bronze', 'gharchive_events') }}
    WHERE event_id != ''
    {% if is_incremental() %}
      {% set target_dates = var('target_dates', '') %}
      {% if target_dates != '' %}
        AND toDate(parseDateTimeBestEffortOrZero(created_at, 'UTC')) IN (
            {% for d in target_dates.split(',') %}
              toDate('{{ d.strip() }}'){% if not loop.last %}, {% endif %}
            {% endfor %}
        )
      {% else %}
        AND toDate(parseDateTimeBestEffortOrZero(created_at, 'UTC')) >= (
            SELECT coalesce(max(event_date), toDate('1970-01-01')) FROM {{ this }}
        )
      {% endif %}
    {% endif %}
    ORDER BY _ingested_at DESC
    LIMIT 1 BY event_id
)

SELECT
    event_id,
    event_type,
    is_public,
    event_timestamp,
    event_date,
    event_hour,
    actor_id,
    actor_login,
    is_bot,
    repo_id,
    repo_full_name,
    repo_owner,
    repo_short_name,
    org_id,
    org_login,
    action,
    git_ref,
    git_ref_type,
    push_commit_count,
    push_distinct_commit_count,
    pr_number,
    pr_title,
    pr_state,
    pr_merged,
    issue_number,
    issue_title,
    issue_state,
    _source_file,
    _ingested_at
FROM deduplicated_bronze

