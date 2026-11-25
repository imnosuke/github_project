{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='event_date',
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
{% if is_incremental() %}
  {% set target_dates = var('target_dates', '') %}
  {% if target_dates != '' %}
    WHERE event_date IN (
        {% for d in target_dates.split(',') %}
          toDate('{{ d.strip() }}'){% if not loop.last %}, {% endif %}
        {% endfor %}
    )
  {% else %}
    WHERE event_date >= (
        SELECT coalesce(max(event_date), toDate('1970-01-01')) FROM {{ this }}
    )
  {% endif %}
{% endif %}
GROUP BY
    event_date,
    event_hour,
    event_type

