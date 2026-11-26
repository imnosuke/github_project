"""Run and publish ML-04 predictions from synthetic fixtures only."""

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from apps.streamlit.data import get_adapter
from ml.cli import ARTIFACT_VERSION
from ml.data import Inputs, utc_timestamp
from ml.features import FEATURES, Ineligible, feature_row
from ml.publication_files import commit_exclusive
from ml.spec import HORIZON_DAYS, SPEC_VERSION, sample_window
from ml.training import predict


def load_fixture_model(directory):
    report = json.loads((directory / "run.json").read_text(encoding="utf8"))
    model_bytes = (directory / "model.json").read_bytes()
    model_id = hashlib.sha256(model_bytes).hexdigest()
    artifact = json.loads(model_bytes)
    if (
        report["status"] != "completed" or report["publication"]["data_source"] != "fixture"
        or report["model_sha256"] != model_id or artifact["artifact_version"] != ARTIFACT_VERSION
        or artifact["spec_version"] != SPEC_VERSION or tuple(artifact["feature_schema"]) != FEATURES
    ):
        raise ValueError("ML-04 offline batch requires a valid completed fixture model")
    return model_id, artifact["model"]


def publish_fixture(data, model_id, model, anchor, decision_at, output):
    if data.publication["data_source"] != "fixture":
        raise ValueError("ML-04 offline batch requires fixture input")
    decision = utc_timestamp(decision_at)
    if utc_timestamp(data.publication["published_at"]) > decision:
        raise ValueError("Input publication was unavailable at decision_at")
    if decision < sample_window(anchor).feature_cutoff_exclusive:
        raise ValueError("decision_at must be on or after the anchor's feature cutoff")
    now = datetime.now(timezone.utc)
    if decision > now:
        raise ValueError("decision_at cannot be in the future")
    anchor_key = anchor.isoformat()
    if not data.lower <= anchor_key <= data.upper:
        raise ValueError("Anchor outside fixture coverage")
    schema_id = hashlib.sha256(json.dumps(FEATURES).encode("utf8")).hexdigest()
    key = {"anchor_date": anchor_key, "input_publication_id": data.publication["publication_id"],
           "model_id": model_id, "feature_schema_id": schema_id}
    batch_id = hashlib.sha256(json.dumps(key, sort_keys=True).encode("utf8")).hexdigest()
    destination = output / f"{batch_id}.json"

    def existing():
        report = json.loads(destination.read_text(encoding="utf8"))
        if report["key"] != key or report["input_fingerprint"] != data.fingerprint:
            raise ValueError("Committed publication ID does not match this fixture")
        return report

    if destination.exists():
        return existing()
    generated = now.isoformat().replace("+00:00", "Z")
    rows = []
    for repo_id in sorted(data.scope):
        if not data.in_scope(repo_id, anchor_key):
            continue
        try:
            features = feature_row(data, repo_id, anchor)
        except Ineligible as exc:
            status = "insufficient_history" if str(exc) in {"out_of_scope", "insufficient_history"} else "incomplete_features"
            value = None
        else:
            status = "ready"
            value = float(predict(model, pd.DataFrame([features]))[0])
        rows.append({**key, "prediction_publication_id": batch_id, "repository_id": repo_id,
                     "horizon_days": HORIZON_DAYS, "decision_at": decision.isoformat().replace("+00:00", "Z"),
                     "generated_at": generated,
                     "status": status, "predicted_star_events": value})
    if not rows:
        raise ValueError("No repositories were active at the anchor")
    report = {"data_source": "fixture", "key": key, "publication_id": batch_id, "generated_at": generated,
              "input_fingerprint": data.fingerprint, "rows": rows}

    try:
        commit_exclusive(destination, json.dumps(report, allow_nan=False) + "\n")
    except FileExistsError:
        return existing()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--anchor", required=True, type=date.fromisoformat)
    parser.add_argument("--decision-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    data = Inputs.from_adapter(get_adapter("fixture", args.fixture))
    model_id, model = load_fixture_model(args.run)
    result = publish_fixture(data, model_id, model, args.anchor, args.decision_at, args.output)
    print(json.dumps({"data_source": "fixture", "publication_id": result["publication_id"], "rows": len(result["rows"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
