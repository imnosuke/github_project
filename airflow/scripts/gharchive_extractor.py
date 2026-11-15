"""
Script xử lý tải dữ liệu GH Archive (https://data.gharchive.org/),
giải nén, chuẩn hóa sang định dạng Parquet và đẩy lên S3 MinIO.
"""
import argparse
import gzip
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Any, Iterable, List, Optional, Set, Tuple

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
    - hours_step=1: lấy đủ 24 giờ/ngày (chuẩn completeness 24/24).
    - hours_step>1: lấy mẫu cách giờ (ví dụ step=4 -> 6 giờ/ngày) để chạy nhanh trên máy cá nhân.
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

    targets: List[Tuple[str, int]] = []
    cur = s_date
    while cur <= e_date:
        d_str = cur.isoformat()
        for h in range(s_hour, e_hour + 1, step):
            targets.append((d_str, h))
        cur += timedelta(days=1)
    return targets


def build_gharchive_filename(date_str: str, hour: int) -> str:
    """
    Tạo tên file chuẩn của GH Archive: {YYYY-MM-DD}-{H}.json.gz
    Lưu ý: hour từ 0..23 KHÔNG có số 0 đứng trước (ví dụ: 2024-01-01-0.json.gz, 2024-01-01-15.json.gz)
    """
    return f"{date_str}-{int(hour)}.json.gz"


def download_gharchive_file(date_str: str, hour: int, output_dir: str = "/opt/airflow/data/raw") -> str:
    """
    Tải file .json.gz từ GH Archive về thư mục local tạm thời.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = build_gharchive_filename(date_str, hour)
    url = f"{GHARCHIVE_BASE_URL}/{filename}"
    local_path = os.path.join(output_dir, filename)

    headers = {
        "User-Agent": "Airflow-GHArchive-MinIO-Pipeline/1.0"
    }

    logger.info(f"Đang tải dữ liệu từ: {url}")
    with requests.get(url, headers=headers, stream=True, timeout=120) as response:
        if response.status_code == 404:
            raise FileNotFoundError(f"Không tìm thấy dữ liệu GH Archive trên server cho thời điểm {filename} (HTTP 404).")
        response.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                if chunk:
                    f.write(chunk)

    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    logger.info(f"Tải thành công: {local_path} ({file_size_mb:.2f} MB)")
    return local_path


def convert_json_gz_to_parquet(
    raw_gz_path: str,
    output_dir: str = "/opt/airflow/data/parquet",
    batch_size: int = 50000,
    tracked_repos: Optional[Iterable[str]] = None,
    max_records_per_file: Optional[int] = None,
) -> str:
    """
    Giải nén file .json.gz của GH Archive và chuyển đổi sang định dạng Parquet (nén Snappy).
    Tách các trường quan trọng (id, type, actor, repo, org, created_at, public) thành cột chuẩn,
    và giữ nguyên trường `payload` (vốn có cấu trúc biến động theo từng loại sự kiện) ở dạng JSON string
    để tránh xung đột schema và giúp truy vấn cực nhanh trên Trino/Spark/DuckDB.

    Hỗ trợ lọc theo `tracked_repos` hoặc giới hạn `max_records_per_file` để tiết kiệm RAM/ổ cứng trên máy cá nhân.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    base_name = os.path.basename(raw_gz_path).replace(".json.gz", ".parquet")
    parquet_path = os.path.join(output_dir, base_name)

    repo_filter = parse_repo_filter(tracked_repos)
    if max_records_per_file is None:
        env_max = os.getenv("GHARCHIVE_MAX_RECORDS_PER_FILE", "").strip()
        if env_max.isdigit() and int(env_max) > 0:
            max_records_per_file = int(env_max)

    logger.info(
        f"Đang giải nén và chuyển đổi {raw_gz_path} -> {parquet_path} "
        f"(repo_filter={len(repo_filter) if repo_filter else 'ALL'}, "
        f"max_records={max_records_per_file or 'UNLIMITED'}) ..."
    )

    schema = pa.schema([
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

    writer = pq.ParquetWriter(parquet_path, schema, compression="snappy")
    total_records = 0
    scanned_records = 0
    batch_rows = []

    def _flush_batch(rows):
        if not rows:
            return
        table = pa.Table.from_pylist(rows, schema=schema)
        writer.write_table(table)

    try:
        with gzip.open(raw_gz_path, "rt", encoding="utf-8", errors="replace") as gz_file:
            for line in gz_file:
                line = line.strip()
                if not line:
                    continue
                scanned_records += 1
                try:
                    record: Dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue

                repo = record.get("repo") or {}
                repo_name = repo.get("name")
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
                    logger.info(f"Đã đạt giới hạn {max_records_per_file:,} events/file, dừng đọc sớm.")
                    break

        if batch_rows:
            _flush_batch(batch_rows)
            batch_rows.clear()
        elif total_records == 0:
            # Đảm bảo file Parquet hợp lệ với 0 dòng nếu không có sự kiện khớp bộ lọc
            writer.write_table(pa.Table.from_pylist([], schema=schema))
    finally:
        writer.close()

    parquet_size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
    logger.info(
        f"Hoàn tất chuyển đổi Parquet: {parquet_path} | "
        f"Giữ lại: {total_records:,}/{scanned_records:,} events | Dung lượng: {parquet_size_mb:.2f} MB"
    )
    return parquet_path


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


def upload_to_minio(
    local_file_path: str,
    date_str: str,
    hour: int,
    bucket_name: str = None,
    layer_prefix: str = "bronze/events_parquet",
) -> str:
    """
    Đẩy file Parquet (hoặc Raw) lên S3 MinIO theo cấu trúc Hive Partitioning:
    s3://<bucket>/<layer_prefix>/year=YYYY/month=MM/day=DD/YYYY-MM-DD-H.parquet
    """
    bucket = bucket_name or os.getenv("MINIO_BUCKET_NAME", "gharchive")
    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client, bucket)

    year, month, day = date_str.split("-")
    filename = os.path.basename(local_file_path)
    s3_key = f"{layer_prefix}/year={year}/month={month}/day={day}/{filename}"

    logger.info(f"Đang upload {local_file_path} lên s3://{bucket}/{s3_key} ...")
    s3_client.upload_file(local_file_path, bucket, s3_key)

    s3_uri = f"s3://{bucket}/{s3_key}"
    logger.info(f"Upload hoàn tất: {s3_uri}")
    return s3_uri


def cleanup_local_files(*file_paths: str):
    """Dọn dẹp các file tạm trên ổ cứng sau khi đã đẩy lên MinIO."""
    for path in file_paths:
        if path and os.path.exists(path):
            os.remove(path)
            logger.info(f"Đã xóa file tạm: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chạy độc lập script tải GH Archive -> Parquet -> MinIO (hỗ trợ khoảng ngày)")
    parser.add_argument("--date", help="Ngày bắt đầu cần tải (YYYY-MM-DD), ví dụ: 2025-01-15")
    parser.add_argument("--end-date", help="Ngày kết thúc (YYYY-MM-DD, tùy chọn, mặc định bằng --date)")
    parser.add_argument("--hour", type=int, help="Giờ đơn lẻ cần tải (0-23). Nếu bỏ trống sẽ dùng --start-hour đến --end-hour")
    parser.add_argument("--start-hour", type=int, default=0, help="Giờ bắt đầu trong ngày (0-23, mặc định: 0)")
    parser.add_argument("--end-hour", type=int, default=23, help="Giờ kết thúc trong ngày (0-23, mặc định: 23)")
    parser.add_argument("--hours-step", type=int, default=1, help="Bước nhảy giờ (mặc định 1 = cả 24h; đặt 4 hoặc 6 để lấy mẫu nhẹ cho máy cá nhân)")
    parser.add_argument("--filter-default-repos", action="store_true", help="Chỉ giữ sự kiện của 50 repo phổ biến mặc định để nhẹ máy")
    parser.add_argument("--repos", help="Danh sách owner/repo cách nhau dấu phẩy để lọc")
    parser.add_argument("--max-records", type=int, default=None, help="Giới hạn số dòng tối đa mỗi file Parquet")
    parser.add_argument("--keep-raw", action="store_true", help="Upload thêm cả file gốc .json.gz lên phân vùng bronze/")
    parser.add_argument("--local-only", action="store_true", help="Chỉ tải và chuyển sang Parquet ở local, không đẩy lên MinIO")
    parser.add_argument("--output-dir", default="/opt/airflow/data", help="Thư mục gốc lưu dữ liệu tạm (raw & parquet)")
    args = parser.parse_args()

    if not args.date:
        parser.error("Cần truyền --date YYYY-MM-DD")

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

    raw_dir = os.path.join(args.output_dir, "raw")
    parquet_dir = os.path.join(args.output_dir, "parquet")

    logger.info(f"Bắt đầu xử lý {len(targets)} khung giờ từ {targets[0]} đến {targets[-1]}...")
    for d_str, hr in targets:
        raw_file = None
        parquet_file = None
        try:
            raw_file = download_gharchive_file(d_str, hr, output_dir=raw_dir)
            if args.keep_raw and not args.local_only:
                upload_to_minio(raw_file, d_str, hr, layer_prefix="bronze/events_raw")

            parquet_file = convert_json_gz_to_parquet(
                raw_file,
                output_dir=parquet_dir,
                tracked_repos=custom_repos,
                max_records_per_file=args.max_records,
            )
            if not args.local_only:
                upload_to_minio(parquet_file, d_str, hr, layer_prefix="bronze/events_parquet")
        except FileNotFoundError as e:
            logger.warning(f"Bỏ qua khung giờ {d_str}-{hr}: {e}")
        finally:
            if not args.local_only:
                cleanup_local_files(raw_file, parquet_file)
            elif raw_file:
                cleanup_local_files(raw_file)
