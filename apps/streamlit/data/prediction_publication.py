"""Read committed prediction batches without changing the analytics publication."""

from datetime import datetime, timedelta
import math

from .clickhouse_http import read_rows
from .clickhouse_publication import require_date


def prediction_timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("Prediction timestamp must be UTC")
    return stamp


def validate_predictions(rows, repository_ids, publication_id):
    ids = [int(row["repository_id"]) for row in rows]
    scope = [int(rid) for rid in repository_ids]
    if (not scope or len(scope) > 50_000 or any(rid <= 0 for rid in scope)
            or len(set(scope)) != len(scope) or sorted(ids) != sorted(scope)):
        raise ValueError("Prediction scope differs from the manifest")
    result = []
    for row, rid in zip(rows, ids):
        if row["publication_id"] != publication_id:
            raise ValueError("Prediction row belongs to another publication")
        status, value = row["status"], row["predicted_star_events"]
        if status == "ready":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid prediction")
        elif status not in {"insufficient_history", "incomplete_features"} or value is not None:
            raise ValueError("Invalid prediction status")
        result.append({"repository_id": rid, "status": status, "predicted_star_events": value})
    return result


def read_prediction_publication(config, anchor, release_id):
    params = {"database": config.database, "anchor": anchor, "release": release_id}
    manifests = read_rows(config, """
        SELECT * FROM {database:Identifier}.prediction_publications
        WHERE anchor_date = {anchor:Date} AND release_id = {release:String}
        ORDER BY generated_at DESC, publication_id DESC LIMIT 1 FORMAT JSONEachRow
    """, params, row_limit=1)
    if not manifests:
        return None
    manifest = manifests[0]
    if require_date(manifest["anchor_date"]) != anchor or manifest["release_id"] != release_id:
        raise ValueError("Unexpected prediction manifest")
    decision = prediction_timestamp(manifest["decision_at"])
    if (prediction_timestamp(manifest["generated_at"]) < decision
            or (decision.date() - timedelta(days=1)).isoformat() != anchor):
        raise ValueError("Prediction predates its decision")
    params["publication"] = manifest["publication_id"]
    rows = read_rows(config, """
        SELECT publication_id, repository_id, status, predicted_star_events
        FROM {database:Identifier}.repository_predictions WHERE publication_id = {publication:String}
        LIMIT 50001 FORMAT JSONEachRow
    """, params, row_limit=50_000)
    return {**manifest, "rows": validate_predictions(rows, manifest["repository_ids"], manifest["publication_id"])}
