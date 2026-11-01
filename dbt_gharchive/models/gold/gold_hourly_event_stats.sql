{{
    config(
        materialized='table',
        engine='MergeTree()',
        order_by='(event_date, event_hour, event_type)'
    )
}}

SELECT
    event_date,
    event_hour,
    event_type,

    count() AS total_events,
    countIf(is_bot = false) AS human_events,
    countIf(is_bot = true) AS bot_events,
    uniqExact(actor_id) AS unique_actors,
    uniqExact(repo_id) AS unique_repositories
FROM {{ ref('stg_gharchive_events') }}
GROUP BY
    event_date,
    event_hour,
    event_type

