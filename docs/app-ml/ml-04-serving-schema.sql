CREATE TABLE IF NOT EXISTS app_serving.prediction_publications
(
    publication_id String, batch_key String, anchor_date Date, input_publication_id String,
    input_fingerprint String, model_id String, feature_schema_id String, release_id String,
    decision_at String, generated_at String, repository_ids Array(Int64)
)
ENGINE = MergeTree ORDER BY (anchor_date, generated_at, publication_id);

CREATE TABLE IF NOT EXISTS app_serving.repository_predictions
(
    publication_id String, repository_id Int64, status LowCardinality(String), predicted_star_events Nullable(Float64)
)
ENGINE = MergeTree ORDER BY (publication_id, repository_id);
