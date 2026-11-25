{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='event_date',
        engine='MergeTree()',
        order_by='(event_date, total_events, actor_id)'
    )
}}

WITH valid_actor_events AS (
    SELECT *
    FROM {{ ref('stg_gharchive_events') }}
    WHERE actor_id != 0
    {% if is_incremental() %}
      {% set target_dates = var('target_dates', '') %}
      {% if target_dates != '' %}
        AND event_date IN (
            {% for d in target_dates.split(',') %}
              toDate('{{ d.strip() }}'){% if not loop.last %}, {% endif %}
            {% endfor %}
        )
      {% else %}
        AND event_date >= (
            SELECT coalesce(max(event_date), toDate('1970-01-01')) FROM {{ this }}
        )
      {% endif %}
    {% endif %}
)

SELECT
    event_date,
    actor_id,
    anyLast(actor_login) AS actor_login,
    anyLast(is_bot) AS is_bot,

    count() AS total_events,
    uniqExact(repo_id) AS distinct_repos_interacted,

    countIf(event_type = 'PushEvent') AS push_events_count,
    sumIf(push_commit_count, event_type = 'PushEvent') AS total_commits_pushed,
    countIf(event_type = 'PullRequestEvent' AND action = 'opened') AS prs_opened,
    countIf(event_type = 'PullRequestReviewEvent') AS pr_reviews_submitted,
    countIf(event_type = 'IssuesEvent' AND action = 'opened') AS issues_opened,
    countIf(event_type = 'IssueCommentEvent') AS comments_made,
    countIf(event_type = 'WatchEvent') AS repos_starred,

    min(event_timestamp) AS first_active_at,
    max(event_timestamp) AS last_active_at
FROM valid_actor_events
GROUP BY
    event_date,
    actor_id
