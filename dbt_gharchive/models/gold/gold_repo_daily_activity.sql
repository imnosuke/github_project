{{
    config(
        materialized='table',
        engine='MergeTree()',
        order_by='(event_date, total_events, repo_id)'
    )
}}

WITH valid_repo_events AS (
    SELECT *, event_type = 'PullRequestEvent' AND action = 'closed' AS is_pr_close
    FROM {{ ref('stg_gharchive_events') }}
    WHERE repo_id != 0 AND repo_full_name != ''
)

SELECT
    event_date,
    repo_id,
    anyLast(repo_full_name) AS repo_full_name,
    anyLast(repo_owner) AS repo_owner,
    anyLast(repo_short_name) AS repo_short_name,
    anyLast(org_login) AS org_login,

    count() AS total_events,
    uniqExact(actor_id) AS unique_contributors,
    uniqExactIf(actor_id, is_bot = false) AS unique_human_contributors,

    -- Thống kê Stars & Forks
    countIf(event_type = 'WatchEvent') AS stars_gained,
    countIf(event_type = 'ForkEvent') AS forks_count,

    -- Thống kê Code Push & Commits
    countIf(event_type = 'PushEvent') AS push_events_count,
    sumIf(push_commit_count, event_type = 'PushEvent') AS total_commits_pushed,

    -- Thống kê Pull Requests
    countIf(event_type = 'PullRequestEvent' AND action = 'opened') AS prs_opened,
    if(
        countIf(is_pr_close AND isNull(pr_merged)) = 0,
        countIf(is_pr_close AND pr_merged = true),
        NULL
    ) AS prs_merged,
    if(
        countIf(is_pr_close AND isNull(pr_merged)) = 0,
        countIf(is_pr_close AND pr_merged = false),
        NULL
    ) AS prs_closed_unmerged,

    -- Thống kê Issues
    countIf(event_type = 'IssuesEvent' AND action = 'opened') AS issues_opened,
    countIf(event_type = 'IssuesEvent' AND action = 'closed') AS issues_closed,
    countIf(event_type = 'IssueCommentEvent') AS issue_comments_count,

    min(event_timestamp) AS first_event_at,
    max(event_timestamp) AS last_event_at
FROM valid_repo_events
GROUP BY
    event_date,
    repo_id
