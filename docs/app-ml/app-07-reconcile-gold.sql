-- Compare the committed GH Archive snapshot with the current dbt Gold model.
-- Run after DE has processed all 24 UTC hours for the same date and repo scope.
WITH expected AS (
    SELECT 33884891 AS repo_id, 'apache/airflow' AS repository_name,
           299 AS total_events, 16 AS star_events, 8 AS fork_events
    UNION ALL
    SELECT 39464018, 'apache/superset', 217, 17, 11
), gold_day AS (
    SELECT repo_id, count(*) AS gold_rows,
           sum(total_events) AS total_events,
           sum(stars_gained) AS star_events,
           sum(forks_count) AS fork_events
    FROM gold.gold_repo_daily_activity
    WHERE event_date = '2025-01-15' AND repo_id IN (33884891, 39464018)
    GROUP BY repo_id
)
SELECT
    e.repo_id,
    e.repository_name,
    coalesce(g.gold_rows, 0) AS gold_row_count,
    e.total_events AS expected_total_events,
    CASE WHEN g.gold_rows = 1 THEN g.total_events END AS gold_total_events,
    e.star_events AS expected_star_events,
    CASE WHEN g.gold_rows = 1 THEN g.star_events END AS gold_star_events,
    e.fork_events AS expected_fork_events,
    CASE WHEN g.gold_rows = 1 THEN g.fork_events END AS gold_fork_events,
    CASE
        WHEN coalesce(g.gold_rows, 0) = 0 THEN 'missing_gold_row'
        WHEN g.gold_rows != 1 THEN 'duplicate_gold_rows'
        WHEN e.total_events = g.total_events AND e.star_events = g.star_events
             AND e.fork_events = g.fork_events THEN 'match'
        ELSE 'metric_mismatch'
    END AS result
FROM expected AS e
LEFT JOIN gold_day AS g ON e.repo_id = g.repo_id
ORDER BY e.repo_id;
