"""Publish ML-04 from an explicitly approved ML-03 Gold release."""

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from apps.streamlit.data import get_adapter
from apps.streamlit.data.clickhouse_http import read_rows
from apps.streamlit.data.clickhouse_publication import require_utc
from apps.streamlit.data.clickhouse_snapshot import _is_loopback
from apps.streamlit.data.config import ClickHouseConfig
from apps.streamlit.data.prediction_publication import prediction_timestamp, validate_predictions
from ml.batch_fixture import prediction_rows
from ml.cli import ARTIFACT_VERSION
from ml.data import Inputs
from ml.features import FEATURES
from ml.observe_publication import record_observation
from ml.spec import SPEC_VERSION


def load_release(path, model_path, now):
    release = json.loads(path.read_text(encoding="utf8"))
    model_bytes = model_path.read_bytes()
    model_id = sha256(model_bytes).hexdigest()
    artifact = json.loads(model_bytes)
    run_bytes = model_path.with_name("run.json").read_bytes()
    run = json.loads(run_bytes)
    ml03 = release.get("ml03_acceptance", {})
    if (release.get("status") != "approved" or not release.get("release_id") or release.get("model_sha256") != model_id
            or not all(isinstance(ml03.get(key), str) and ml03[key].strip() for key in
                       ("gold_reconciliation", "contract_confirmation", "prospective_evaluation"))
            or ml03.get("gold_training_run_sha256") != sha256(run_bytes).hexdigest()
            or run.get("status") != "completed" or run.get("model_sha256") != model_id
            or run.get("publication", {}).get("data_source") != "live"
            or require_utc(release["approved_at"]) > now or artifact.get("artifact_version") != ARTIFACT_VERSION
            or artifact.get("spec_version") != SPEC_VERSION or tuple(artifact.get("feature_schema", ())) != FEATURES):
        raise ValueError("ML-04 requires a current ML-03 Gold approval for this model checksum and schema")
    scope = release.get("repository_ids", [])
    if len(scope) != 20 or any(type(rid) is not int or rid <= 0 for rid in scope) or len(set(scope)) != len(scope):
        raise ValueError("ML-04 release requires the approved scope of 20 unique repository IDs")
    return release, model_id, artifact["model"]


def insert(config, table, rows):
    host = f"[{config.host}]" if ":" in config.host else config.host
    scheme = "https" if config.secure else "http"
    query = f"INSERT INTO {table} FORMAT JSONEachRow\n" + "\n".join(json.dumps(row, allow_nan=False) for row in rows)
    params = urlencode({"database": config.database, "wait_end_of_query": 1})
    req = Request(f"{scheme}://{host}:{config.port}/?{params}", data=query.encode("utf8"),
                  headers={"X-ClickHouse-User": config.username, "X-ClickHouse-Key": config.password})
    with urlopen(req, timeout=config.query_timeout) as response:
        if response.read().strip():
            raise OSError("ClickHouse did not confirm the prediction insert")


def publish(data, config, release, model_id, model, observed):
    if data.publication["data_source"] != "live" or not config.secure and not _is_loopback(config.host):
        raise ValueError("ML-04 requires live Gold and HTTPS or a loopback prediction writer")
    decision = datetime.now(timezone.utc)
    anchor = decision.date() - timedelta(days=1)
    if (observed["publication_id"] != data.publication["publication_id"]
            or observed["input_fingerprint"] != data.fingerprint or require_utc(data.publication["published_at"]) > decision
            or prediction_timestamp(observed["observed_at"]) > decision):
        raise ValueError("Gold publication was not observed at the decision")

    generated = list(prediction_rows(data, model, anchor))
    scope = sorted(release["repository_ids"])
    if sorted(row["repository_id"] for row in generated) != scope:
        raise ValueError("Gold registry differs from the approved prediction scope")
    key = {"anchor_date": anchor.isoformat(), "input_publication_id": data.publication["publication_id"],
           "model_id": model_id, "feature_schema_id": sha256(json.dumps(FEATURES).encode()).hexdigest(),
           "release_id": release["release_id"]}
    batch_key = sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    params = {"database": config.database, "batch": batch_key}
    existing = read_rows(config, """
        SELECT publication_id, input_fingerprint FROM {database:Identifier}.prediction_publications
        WHERE batch_key = {batch:String} LIMIT 2 FORMAT JSONEachRow
    """, params, row_limit=2)
    if existing:
        if len(existing) != 1 or existing[0]["input_fingerprint"] != data.fingerprint:
            raise ValueError("Committed prediction batch differs from the current input")
        return existing[0]["publication_id"]

    publication_id = uuid4().hex
    rows = [{"publication_id": publication_id, **row} for row in generated]
    validate_predictions(rows, scope, publication_id)
    insert(config, "repository_predictions", rows)
    stored = read_rows(config, """
        SELECT publication_id, repository_id, status, predicted_star_events
        FROM {database:Identifier}.repository_predictions WHERE publication_id = {publication:String}
        LIMIT 21 FORMAT JSONEachRow
    """, {"database": config.database, "publication": publication_id}, row_limit=20)
    validate_predictions(stored, scope, publication_id)
    manifest = {**key, "publication_id": publication_id, "batch_key": batch_key, "input_fingerprint": data.fingerprint,
                "decision_at": decision.isoformat(timespec="microseconds"),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"), "repository_ids": scope}
    insert(config, "prediction_publications", [manifest])
    return publication_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--source-name", required=True)
    args = parser.parse_args(argv)
    release, model_id, model = load_release(args.release, args.model, datetime.now(timezone.utc))
    env = {"APP_CLICKHOUSE_" + key.removeprefix("ML04_CLICKHOUSE_"): value for key, value in os.environ.items()
           if key.startswith("ML04_CLICKHOUSE_")}
    if "APP_CLICKHOUSE_USER" not in env or "APP_CLICKHOUSE_DATABASE" not in env or not args.source_name.strip():
        parser.error("Configure the ML04_CLICKHOUSE writer user/database and a source name")
    config = ClickHouseConfig.from_env(env)
    data = Inputs.from_adapter(get_adapter("clickhouse"))
    observed = record_observation(data, args.observations, args.source_name, datetime.now(timezone.utc).isoformat())
    print(json.dumps({"publication_id": publish(data, config, release, model_id, model, observed)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
