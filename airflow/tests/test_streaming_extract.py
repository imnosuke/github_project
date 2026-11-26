"""Replay the APP-07 source fixture through the streaming parser."""

from collections import Counter
import gzip
import io
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pyarrow.parquet as pq
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import gharchive_extractor as extractor


DAY = "2025-01-15"
FIXTURE = SCRIPTS.parents[1] / "apps/streamlit/data/snapshots" / f"gharchive-{DAY}/parquet"


class Response:
    def __init__(self, data, status_code=200):
        self.raw = io.BytesIO(data)
        self.status_code = status_code

    def raise_for_status(self):
        assert self.status_code == 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.raw.close()


def fixture_gzip(hour):
    rows = pq.read_table(FIXTURE / f"{DAY}-{hour}.parquet").to_pylist()
    events = [
        {"id": row["event_id"], "type": row["event_type"], "public": row.get("public", True),
         "created_at": row["created_at"], "actor": {"id": row["actor_id"], "login": row["actor_login"]},
         "repo": {"id": row["repo_id"], "name": row.get("repo_name")},
         "payload": json.loads(row["payload_json"])}
        for row in rows
    ]
    return gzip.compress("\n".join(map(json.dumps, events)).encode())


def test_twenty_four_hours_retry_and_missing_source(monkeypatch):
    sources = {hour: fixture_gzip(hour) for hour in range(24)}
    objects = {}
    s3 = Mock()
    monkeypatch.setattr(extractor, "get_s3_client", lambda: s3)
    monkeypatch.setattr(extractor, "ensure_bucket_exists", lambda *_: None)
    monkeypatch.delenv("GHARCHIVE_MAX_RECORDS_PER_FILE", raising=False)

    def upload(stream, bucket, key):
        objects[bucket, key] = stream.read()

    s3.upload_fileobj.side_effect = upload
    monkeypatch.setattr(extractor.requests, "get", lambda url, **_: Response(sources[int(url.rsplit("-", 1)[1].split(".")[0])]))
    for hour in range(24):
        extractor.stream_https_to_minio_parquet(DAY, hour, bucket_name="test")
    assert len(objects) == 24
    counts = Counter()
    for payload in objects.values():
        for row in pq.read_table(io.BytesIO(payload)).to_pylist():
            counts[row["repo_id"], row["event_type"]] += 1
    assert sum(counts.values()) == 516
    assert [counts[rid, "WatchEvent"] for rid in (33884891, 39464018)] == [16, 17]
    assert [counts[rid, "ForkEvent"] for rid in (33884891, 39464018)] == [8, 11]

    before = dict(objects)
    s3.upload_fileobj.side_effect = OSError("simulated upload failure")
    with pytest.raises(OSError, match="simulated upload failure"):
        extractor.stream_https_to_minio_parquet(DAY, 0, bucket_name="test")
    assert objects == before
    s3.upload_fileobj.side_effect = upload
    extractor.stream_https_to_minio_parquet(DAY, 0, bucket_name="test")
    assert objects == before
    s3.delete_object.assert_not_called()

    monkeypatch.setattr(extractor.requests, "get", lambda *_args, **_kwargs: Response(b"", 404))
    with pytest.raises(FileNotFoundError):
        extractor.stream_https_to_minio_parquet(DAY, 0, bucket_name="test")
    assert objects == before
