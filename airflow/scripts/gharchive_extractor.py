"""
Script xử lý tải dữ liệu GH Archive (https://data.gharchive.org/),
giải nén, chuẩn hóa sang định dạng Parquet và đẩy lên S3 MinIO.
"""
import argparse
import gzip
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any

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
) -> str:
    """
    Giải nén file .json.gz của GH Archive và chuyển đổi sang định dạng Parquet (nén Snappy).
    Tách các trường quan trọng (id, type, actor, repo, org, created_at, public) thành cột chuẩn,
    và giữ nguyên trường `payload` (vốn có cấu trúc biến động theo từng loại sự kiện) ở dạng JSON string
    để tránh xung đột schema và giúp truy vấn cực nhanh trên Trino/Spark/DuckDB.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    base_name = os.path.basename(raw_gz_path).replace(".json.gz", ".parquet")
    parquet_path = os.path.join(output_dir, base_name)

    logger.info(f"Đang giải nén và chuyển đổi {raw_gz_path} -> {parquet_path} ...")

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
                try:
                    record: Dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue

                actor = record.get("actor") or {}
                repo = record.get("repo") or {}
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
                    "repo_name": repo.get("name"),
                    "org_id": org.get("id"),
                    "org_login": org.get("login"),
                    "payload_json": json.dumps(payload, ensure_ascii=False),
                })

                total_records += 1
                if len(batch_rows) >= batch_size:
                    _flush_batch(batch_rows)
                    batch_rows.clear()

        if batch_rows:
            _flush_batch(batch_rows)
            batch_rows.clear()
    finally:
        writer.close()

    parquet_size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
    logger.info(
        f"Hoàn tất chuyển đổi Parquet: {parquet_path} | "
        f"Tổng số events: {total_records:,} | Dung lượng: {parquet_size_mb:.2f} MB"
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
    parser = argparse.ArgumentParser(description="Chạy độc lập script tải GH Archive -> Parquet -> MinIO")
    parser.add_argument("--date", required=True, help="Ngày cần tải (YYYY-MM-DD), ví dụ: 2025-01-15")
    parser.add_argument("--hour", required=True, type=int, help="Giờ cần tải (0-23), ví dụ: 14")
    parser.add_argument("--keep-raw", action="store_true", help="Upload thêm cả file gốc .json.gz lên phân vùng bronze/")
    args = parser.parse_args()

    raw_file = download_gharchive_file(args.date, args.hour)
    if args.keep_raw:
        upload_to_minio(raw_file, args.date, args.hour, layer_prefix="bronze/events_raw")

    parquet_file = convert_json_gz_to_parquet(raw_file)
    upload_to_minio(parquet_file, args.date, args.hour, layer_prefix="bronze/events_parquet")
    cleanup_local_files(raw_file, parquet_file)
