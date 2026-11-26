"""
Script xử lý stream dữ liệu trực tiếp từ GH Archive (https://data.gharchive.org/)
lên S3 MinIO hoàn toàn trên RAM (io.BytesIO) mà không ghi file tạm xuống ổ cứng:
- Giải nén luồng Gzip on-the-fly từ HTTPS response
- Chuẩn hóa schema và đóng gói Snappy Parquet trên RAM
- Đẩy thẳng buffer Parquet (và tùy chọn bản gốc .json.gz) lên S3 MinIO theo Hive Partitioning
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import gzip
import io
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import boto3
from botocore.client import Config
import pyarrow as pa
import pyarrow.parquet as pq
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("gharchive_pipeline")

GHARCHIVE_BASE_URL = "https://data.gharchive.org"

# Danh sách 50 repositories mặc định cho chế độ lọc nhẹ trên máy cá nhân (Tracked Scope)
DEFAULT_TRACKED_REPOS: Tuple[str, ...] = (
    "apache/airflow",
    "apache/spark",
    "apache/kafka",
    "apache/superset",
    "apache/iceberg",
    "ClickHouse/ClickHouse",
    "dbt-labs/dbt-core",
    "minio/minio",
    "duckdb/duckdb",
    "trinodb/trino",
    "pola-rs/polars",
    "pandas-dev/pandas",
    "numpy/numpy",
    "scikit-learn/scikit-learn",
    "pytorch/pytorch",
    "tensorflow/tensorflow",
    "huggingface/transformers",
    "langchain-ai/langchain",
    "vllm-project/vllm",
    "ollama/ollama",
    "ggml-org/llama.cpp",
    "openai/whisper",
    "microsoft/DeepSpeed",
    "ray-project/ray",
    "mlflow/mlflow",
    "streamlit/streamlit",
    "gradio-app/gradio",
    "fastapi/fastapi",
    "pydantic/pydantic",
    "sqlalchemy/sqlalchemy",
    "prefecthq/prefect",
    "dagster-io/dagster",
    "airbytehq/airbyte",
    "DataDog/datadog-agent",
    "prometheus/prometheus",
    "grafana/grafana",
    "elastic/elasticsearch",
    "redis/redis",
    "postgres/postgres",
    "kubernetes/kubernetes",
    "docker/compose",
    "astral-sh/uv",
    "astral-sh/ruff",
    "microsoft/vscode",
    "facebook/react",
    "vercel/next.js",
    "vuejs/core",
    "sveltejs/svelte",
    "rust-lang/rust",
    "golang/go",
)

PARQUET_SCHEMA = pa.schema([
    ("event_id", pa.string()),
    ("event_type", pa.string()),
    ("public", pa.bool_()),
    ("created_at", pa.string()),
    ("actor_id", pa.int64()),
    ("actor_login", pa.string()),
    ("repo_id", pa.int64()),
    ("repo_name", pa.string()),
    ("org_id", pa.int64()),
    ("org_login", pa.string()),
    ("payload_json", pa.string()),
])


def parse_repo_filter(
    tracked_repos: Optional[Iterable[str]] = None,
    use_default_if_env_enabled: bool = True,
) -> Optional[Set[str]]:
    """
    Chuẩn hóa danh sách repo cần lọc (chữ thường 'owner/repo').
    Trả về None nếu không bật lọc (giữ toàn bộ sự kiện).
    """
    if tracked_repos:
        cleaned = {str(r).strip().lower() for r in tracked_repos if str(r).strip()}
        return cleaned or None

    env_repos = os.getenv("GHARCHIVE_TRACKED_REPOS", "").strip()
    if env_repos:
        cleaned = {r.strip().lower() for r in env_repos.split(",") if r.strip()}
        return cleaned or None

    if use_default_if_env_enabled and os.getenv("GHARCHIVE_FILTER_DEFAULT_REPOS", "false").lower() in ("1", "true", "yes"):
        return {r.lower() for r in DEFAULT_TRACKED_REPOS}

    return None


def iter_date_hours(
    start_date: str,
    end_date: Optional[str] = None,
    start_hour: int = 0,
    end_hour: int = 23,
    hours_step: int = 1,
) -> List[Tuple[str, int]]:
    """
    Sinh danh sách các cặp (date_str, hour) theo khoảng ngày và khung giờ.
    Nếu ngày cần lấy trùng với ngày hiện tại theo giờ UTC, tự động giới hạn giờ tối đa
    đến khung giờ UTC đã hoàn tất gần nhất (now_utc.hour - 1) để tránh lỗi HTTP 404 ở các giờ tương lai.
    """
    s_date = date.fromisoformat(start_date.strip())
    e_date = date.fromisoformat((end_date or start_date).strip())
    if s_date > e_date:
        raise ValueError(f"start_date ({start_date}) không được lớn hơn end_date ({end_date})")

    s_hour = max(0, min(23, int(start_hour)))
    e_hour = max(0, min(23, int(end_hour)))
    if s_hour > e_hour:
        raise ValueError(f"start_hour ({s_hour}) không được lớn hơn end_hour ({e_hour})")
    step = max(1, int(hours_step))

    now_utc = datetime.now(timezone.utc)
    today_utc = now_utc.date()
    latest_completed_utc_hour = max(0, now_utc.hour - 1)

    targets: List[Tuple[str, int]] = []
    cur = s_date
    while cur <= e_date:
        d_str = cur.isoformat()
        effective_end_hour = min(e_hour, latest_completed_utc_hour) if cur == today_utc and s_hour != e_hour else e_hour
        for h in range(s_hour, effective_end_hour + 1, step):
            targets.append((d_str, h))
        cur += timedelta(days=1)
    return targets


def build_gharchive_filename(date_str: str, hour: int) -> str:
    """
    Tạo tên file chuẩn của GH Archive: {YYYY-MM-DD}-{H}.json.gz
    Lưu ý: hour từ 0..23 KHÔNG có số 0 đứng trước (ví dụ: 2025-01-01-0.json.gz, 2025-01-01-15.json.gz)
    """
    return f"{date_str}-{int(hour)}.json.gz"


def get_s3_client():
    """Khởi tạo Boto3 S3 Client kết nối tới MinIO."""
    endpoint_url = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket_exists(s3_client, bucket_name: str):
    """Kiểm tra và tạo bucket trên MinIO nếu chưa tồn tại."""
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except Exception:
        logger.info(f"Bucket '{bucket_name}' chưa tồn tại. Đang khởi tạo...")
        s3_client.create_bucket(Bucket=bucket_name)


def stream_https_raw_gz_to_minio(
    date_str: str,
    hour: int,
    bucket_name: str = None,
    layer_prefix: str = "bronze/events_raw",
) -> str:
    """
    Stream trực tiếp file gốc .json.gz từ HTTPS GH Archive thẳng lên S3 MinIO
    mà không ghi xuống ổ cứng local. Xóa object cũ trước khi ghi đè để đảm bảo idempotency.
    """
    bucket = bucket_name or os.getenv("MINIO_BUCKET_NAME", "gharchive")
    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client, bucket)

    filename = build_gharchive_filename(date_str, hour)
    year, month, day = date_str.split("-")
    s3_key = f"{layer_prefix}/year={year}/month={month}/day={day}/{filename}"
    url = f"{GHARCHIVE_BASE_URL}/{filename}"

    headers = {"User-Agent": "Airflow-GHArchive-MinIO-Pipeline/1.0"}
    logger.info(f"Đang stream trực tiếp bản gốc {url} -> s3://{bucket}/{s3_key} ...")

    with requests.get(url, headers=headers, stream=True, timeout=120) as response:
        if response.status_code == 404:
            raise FileNotFoundError(
                f"Không tìm thấy dữ liệu GH Archive trên server cho thời điểm {filename} (HTTP 404)."
            )
        response.raise_for_status()
        response.raw.decode_content = False
        s3_client.upload_fileobj(response.raw, bucket, s3_key)

    s3_uri = f"s3://{bucket}/{s3_key}"
    logger.info(f"Stream raw .json.gz lên MinIO hoàn tất: {s3_uri}")
    return s3_uri


def stream_https_to_minio_parquet(
    date_str: str,
    hour: int,
    bucket_name: str = None,
    layer_prefix: str = "bronze/events_parquet",
    batch_size: int = 50000,
    tracked_repos: Optional[Iterable[str]] = None,
    max_records_per_file: Optional[int] = None,
    tracked_repository_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    """
    Đọc stream trực tiếp từ HTTPS GH Archive, giải nén Gzip và đóng gói Parquet
    ngay trên RAM (io.BytesIO), sau đó upload lên S3 MinIO
    (0 byte ghi xuống ổ cứng).
    """
    bucket = bucket_name or os.getenv("MINIO_BUCKET_NAME", "gharchive")
    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client, bucket)

    filename = build_gharchive_filename(date_str, hour)
    parquet_filename = filename.replace(".json.gz", ".parquet")
    year, month, day = date_str.split("-")
    s3_key = f"{layer_prefix}/year={year}/month={month}/day={day}/{parquet_filename}"
    url = f"{GHARCHIVE_BASE_URL}/{filename}"

    repo_filter = parse_repo_filter(tracked_repos) if tracked_repository_ids is None else None
    if max_records_per_file is None:
        env_max = os.getenv("GHARCHIVE_MAX_RECORDS_PER_FILE", "").strip()
        if env_max.isdigit() and int(env_max) > 0:
            max_records_per_file = int(env_max)

    headers = {"User-Agent": "Airflow-GHArchive-MinIO-Pipeline/1.0"}
    logger.info(
        f"Đang stream HTTPS -> RAM Parquet -> MinIO: {url} -> s3://{bucket}/{s3_key} "
        f"(repo_filter={len(repo_filter) if repo_filter else 'ALL'}, "
        f"max_records={max_records_per_file or 'UNLIMITED'}) ..."
    )

    parquet_buffer = io.BytesIO()
    writer = pq.ParquetWriter(parquet_buffer, PARQUET_SCHEMA, compression="snappy")
    total_records = 0
    scanned_records = 0
    batch_rows = []

    def _flush_batch(rows):
        if not rows:
            return
        table = pa.Table.from_pylist(rows, schema=PARQUET_SCHEMA)
        writer.write_table(table)

    try:
        with requests.get(url, headers=headers, stream=True, timeout=120) as response:
            if response.status_code == 404:
                raise FileNotFoundError(
                    f"Không tìm thấy dữ liệu GH Archive trên server cho thời điểm {filename} (HTTP 404)."
                )
            response.raise_for_status()
            response.raw.decode_content = False

            with gzip.GzipFile(fileobj=response.raw, mode="rb") as gz_stream:
                for raw_line in gz_stream:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    scanned_records += 1
                    try:
                        record: Dict[str, Any] = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Invalid JSON in {filename}, record {scanned_records}") from exc

                    repo = record.get("repo") or {}
                    repo_name = repo.get("name")
                    if tracked_repository_ids is not None:
                        if repo.get("id") not in tracked_repository_ids:
                            continue
                        if not (repo_name and record.get("id") and record.get("type")):
                            raise ValueError(f"Invalid scoped event in {filename}, record {scanned_records}")
                        stamp = datetime.fromisoformat(record.get("created_at") or "")
                        if stamp.tzinfo is None or stamp.astimezone(timezone.utc).strftime("%Y-%m-%d") != date_str:
                            raise ValueError(f"Scoped event outside the source day: {filename}")
                    if repo_filter is not None:
                        if not repo_name or str(repo_name).lower() not in repo_filter:
                            continue

                    actor = record.get("actor") or {}
                    org = record.get("org") or {}
                    payload = record.get("payload") or {}

                    batch_rows.append({
                        "event_id": str(record.get("id", "")),
                        "event_type": record.get("type"),
                        "public": bool(record.get("public", True)),
                        "created_at": record.get("created_at"),
                        "actor_id": actor.get("id"),
                        "actor_login": actor.get("login"),
                        "repo_id": repo.get("id"),
                        "repo_name": repo_name,
                        "org_id": org.get("id"),
                        "org_login": org.get("login"),
                        "payload_json": json.dumps(payload, ensure_ascii=False),
                    })

                    total_records += 1
                    if len(batch_rows) >= batch_size:
                        _flush_batch(batch_rows)
                        batch_rows.clear()

                    if max_records_per_file and total_records >= max_records_per_file:
                        logger.info(
                            f"Đã đạt giới hạn {max_records_per_file:,} events cho {filename}, đóng stream HTTP sớm."
                        )
                        break

        if not scanned_records:
            raise ValueError(f"Empty GH Archive source: {filename}")
        if batch_rows:
            _flush_batch(batch_rows)
            batch_rows.clear()
        elif total_records == 0:
            writer.write_table(pa.Table.from_pylist([], schema=PARQUET_SCHEMA))
    finally:
        writer.close()

    parquet_buffer.seek(0)
    size_mb = parquet_buffer.getbuffer().nbytes / (1024 * 1024)
    logger.info(
        f"Upload buffer Parquet ({size_mb:.2f} MB | {total_records:,}/{scanned_records:,} events) "
        f"lên s3://{bucket}/{s3_key} ..."
    )
    s3_client.upload_fileobj(parquet_buffer, bucket, s3_key)
    s3_uri = f"s3://{bucket}/{s3_key}"
    logger.info(f"Stream trực tiếp lên MinIO hoàn tất: {s3_uri}")
    return {
        "s3_uri": s3_uri,
        "s3_key": s3_key,
        "records": total_records,
        "size_mb": round(size_mb, 2),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stream trực tiếp dữ liệu GH Archive từ HTTPS -> RAM Parquet -> S3 MinIO (0 byte ghi xuống ổ cứng)"
    )
    parser.add_argument("--date", required=True, help="Ngày bắt đầu cần tải (YYYY-MM-DD), ví dụ: 2025-01-01")
    parser.add_argument("--end-date", help="Ngày kết thúc (YYYY-MM-DD, tùy chọn, mặc định bằng --date)")
    parser.add_argument("--hour", type=int, help="Giờ đơn lẻ cần tải (0-23). Nếu bỏ trống sẽ dùng --start-hour đến --end-hour")
    parser.add_argument("--start-hour", type=int, default=0, help="Giờ bắt đầu trong ngày (0-23, mặc định: 0)")
    parser.add_argument("--end-hour", type=int, default=23, help="Giờ kết thúc trong ngày (0-23, mặc định: 23)")
    parser.add_argument("--hours-step", type=int, default=1, help="Bước nhảy giờ (mặc định 1 = cả 24h; đặt 6 để lấy mẫu 4 khung giờ/ngày)")
    parser.add_argument("--filter-default-repos", action="store_true", help="Chỉ giữ sự kiện của 50 repo phổ biến mặc định")
    parser.add_argument("--repos", help="Danh sách owner/repo cách nhau dấu phẩy để lọc")
    parser.add_argument("--max-records", type=int, default=None, help="Giới hạn số dòng tối đa mỗi file Parquet")
    parser.add_argument("--target-total-mb", type=float, default=None, help="Tổng dung lượng Parquet mục tiêu trên MinIO (MB, ví dụ: 500)")
    parser.add_argument("--skip-existing", action="store_true", help="Bỏ qua nếu file Parquet của khung giờ đó đã tồn tại trên MinIO")
    parser.add_argument("--keep-raw", action="store_true", help="Stream thêm cả file gốc .json.gz lên phân vùng bronze/events_raw trên MinIO")
    args = parser.parse_args()

    s_hour = args.hour if args.hour is not None else args.start_hour
    e_hour = args.hour if args.hour is not None else args.end_hour
    targets = iter_date_hours(
        start_date=args.date,
        end_date=args.end_date,
        start_hour=s_hour,
        end_hour=e_hour,
        hours_step=args.hours_step,
    )

    custom_repos = None
    if args.repos:
        custom_repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    elif args.filter_default_repos:
        custom_repos = list(DEFAULT_TRACKED_REPOS)

    bucket_name = os.getenv("MINIO_BUCKET_NAME", "gharchive")
    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client, bucket_name)

    def _current_minio_total_mb() -> float:
        objs = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="samples/gharchive/parquet/").get("Contents", [])
        return sum(o["Size"] for o in objs) / (1024 * 1024)

    logger.info(
        f"[DIRECT HTTPS -> S3] Bắt đầu stream tối đa {len(targets)} khung giờ thẳng lên MinIO bucket '{bucket_name}'..."
    )
    for idx, (d_str, hr) in enumerate(targets, 1):
        if args.target_total_mb is not None:
            cur_mb = _current_minio_total_mb()
            if cur_mb >= args.target_total_mb:
                logger.info(
                    f"Đã đạt tổng dung lượng trên MinIO: {cur_mb:.2f} MB >= {args.target_total_mb:.2f} MB. Dừng tải thêm."
                )
                break

        year, month, day = d_str.split("-")
        s3_key = f"samples/gharchive/parquet/year={year}/month={month}/day={day}/{d_str}-{int(hr)}.parquet"
        if args.skip_existing:
            try:
                head = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
                if head.get("ContentLength", 0) > 1024:
                    logger.info(
                        f"[{idx}/{len(targets)}] Bỏ qua s3://{bucket_name}/{s3_key} vì đã tồn tại trên MinIO ({head['ContentLength']/(1024*1024):.2f} MB)."
                    )
                    continue
            except Exception:
                pass

        try:
            if args.keep_raw:
                stream_https_raw_gz_to_minio(d_str, hr, bucket_name=bucket_name, layer_prefix="samples/gharchive/raw")

            stream_https_to_minio_parquet(
                date_str=d_str,
                hour=hr,
                bucket_name=bucket_name,
                layer_prefix="samples/gharchive/parquet",
                tracked_repos=custom_repos,
                max_records_per_file=args.max_records,
            )
        except FileNotFoundError as e:
            logger.warning(f"Bỏ qua khung giờ {d_str}-{hr}: {e}")

    objs = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="samples/gharchive/parquet/").get("Contents", [])
    logger.info(
        f"Hoàn tất Direct HTTPS -> S3! Tổng số objects trên MinIO: {len(objs)} files | "
        f"Tổng dung lượng: {_current_minio_total_mb():.2f} MB"
    )
