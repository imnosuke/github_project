"""Record the first verified observation of a committed ClickHouse publication."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from apps.streamlit.data import get_adapter
from ml.data import Inputs, utc_timestamp
from ml.publication_files import commit_exclusive


def record_observation(data, output, source_name, observed_at):
    publication = data.publication
    if publication["data_source"] != "live":
        raise ValueError("Availability observation requires a ClickHouse publication")
    observed = utc_timestamp(observed_at)
    if observed < utc_timestamp(publication["published_at"]):
        raise ValueError("Publication advertises a time later than observation")
    identity = {"source_name": source_name, "publication_id": publication["publication_id"]}
    identifier = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf8")).hexdigest()
    target = output / f"{identifier}.json"
    result = {
        **identity, "data_source": publication["data_source"], "contract_version": publication["contract_version"],
        "declared_published_at": publication["published_at"],
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "date_bounds": [data.lower, data.upper], "input_fingerprint": data.fingerprint,
        "evidence_kind": "first_successful_endpoint_read",
    }
    try:
        commit_exclusive(target, json.dumps(result, indent=2) + "\n")
    except FileExistsError:
        previous = json.loads(target.read_text(encoding="utf8"))
        if previous["input_fingerprint"] != data.fingerprint or any(previous[key] != value for key, value in identity.items()):
            raise ValueError("Publication contents changed under a committed ID") from None
        return previous
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-name", required=True, help="Stable name of the endpoint, e.g. localhost-replay")
    args = parser.parse_args(argv)
    if not args.source_name.strip():
        parser.error("--source-name must not be empty")
    data = Inputs.from_adapter(get_adapter("clickhouse"))
    observed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = record_observation(data, args.output, args.source_name, observed)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
