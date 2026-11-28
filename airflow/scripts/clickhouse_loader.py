"""
Script kết nối ClickHouse, khởi tạo cấu trúc Medallion (Bronze, Silver, Gold databases)
và nạp trực tiếp file Parquet từ MinIO (S3) vào bảng Bronze `bronze.gharchive_events`.
"""
import logging
import os
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("clickhouse_loader")


def execute_clickhouse_sql(sql: str, database: str = "default") -> str:
    """Thực thi câu lệnh SQL trên ClickHouse thông qua giao thức HTTP (cổng 8123)."""
    ch_host = os.getenv("CLICKHOUSE_HOST", "clickhouse")
    ch_port = os.getenv("CLICKHOUSE_PORT", "8123")
    ch_user = os.getenv("CLICKHOUSE_USER", "default")
    ch_password = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse")

    url = f"http://{ch_host}:{ch_port}/"
    params = {"database": database}

    response = requests.post(
        url,
        params=params,
        data=sql.encode("utf-8"),
        auth=(ch_user, ch_password),
        timeout=300,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"ClickHouse SQL Error (HTTP {response.status_code}): {response.text}\nSQL: {sql}"
        )
    return response.text.strip()


def init_medallion_databases_and_bronze_table():
    """
    Khởi tạo 3 database tương ứng 3 tầng: bronze, silver, gold
    và tạo bảng raw `bronze.gharchive_events` để chứa dữ liệu từ Parquet.
    """
    for db_name in ("bronze", "silver", "gold"):
        execute_clickhouse_sql(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        logger.info(f"Đã đảm bảo database '{db_name}' tồn tại trên ClickHouse.")

    create_bronze_table_sql = """
    CREATE TABLE IF NOT EXISTS bronze.gharchive_events
    (
        event_id       String,
        event_type     LowCardinality(String),
        public         Bool,
        created_at     String,
        actor_id       Nullable(Int64),
        actor_login    Nullable(String),
        repo_id        Nullable(Int64),
        repo_name      Nullable(String),
        org_id         Nullable(Int64),
        org_login      Nullable(String),
        payload_json   String,
        _source_file   LowCardinality(String) DEFAULT '',
        _ingested_at   DateTime DEFAULT now()
    )
    ENGINE = ReplacingMergeTree(_ingested_at)
    ORDER BY (event_id, created_at)
    """
    execute_clickhouse_sql(create_bronze_table_sql, database="bronze")
    logger.info("Bảng 'bronze.gharchive_events' đã sẵn sàng.")


def load_minio_parquet_to_bronze(
    date_str: str,
    hour: int,
    bucket_name: str = None,
    layer_prefix: str = "bronze/events_parquet",
    repository_ids=None,
) -> int:
    """
    Sử dụng hàm `s3()` tích hợp của ClickHouse để đọc trực tiếp file Parquet từ MinIO
    và nạp thẳng vào bảng `bronze.gharchive_events`.
    """
    init_medallion_databases_and_bronze_table()

    bucket = bucket_name or os.getenv("MINIO_BUCKET_NAME", "gharchive")
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "http://minio:9000").rstrip("/")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")

    year, month, day = date_str.split("-")
    filename = f"{date_str}-{int(hour)}.parquet"
    s3_http_url = (
        f"{minio_endpoint}/{bucket}/{layer_prefix}/"
        f"year={year}/month={month}/day={day}/{filename}"
    )

    logger.info(f"Đang nạp dữ liệu Parquet từ MinIO vào ClickHouse Bronze: {s3_http_url}")

    # Cách 1: Xóa đồng bộ dữ liệu cũ của cùng _source_file trước khi INSERT lại để chống trùng file ngay tại tầng Bronze
    delete_sql = f"""
    ALTER TABLE bronze.gharchive_events
    DELETE WHERE _source_file = '{filename}'
    SETTINGS mutations_sync = 1
    """
    execute_clickhouse_sql(delete_sql, database="bronze")

    insert_sql = f"""
    INSERT INTO bronze.gharchive_events
    (
        event_id,
        event_type,
        public,
        created_at,
        actor_id,
        actor_login,
        repo_id,
        repo_name,
        org_id,
        org_login,
        payload_json,
        _source_file,
        _ingested_at
    )
    SELECT
        ifNull(event_id, '') AS event_id,
        ifNull(event_type, 'Unknown') AS event_type,
        ifNull(public, true) AS public,
        ifNull(created_at, '') AS created_at,
        actor_id,
        actor_login,
        repo_id,
        repo_name,
        org_id,
        org_login,
        ifNull(payload_json, '{{}}') AS payload_json,
        '{filename}' AS _source_file,
        now() AS _ingested_at
    FROM s3(
        '{s3_http_url}',
        '{minio_access_key}',
        '{minio_secret_key}',
        'Parquet'
    )
    """
    execute_clickhouse_sql(insert_sql, database="bronze")

    scope_filter = "" if repository_ids is None else " AND repo_id IN (" + ",".join(str(int(rid)) for rid in sorted(repository_ids)) + ")"
    count_str = execute_clickhouse_sql(
        f"SELECT count() FROM bronze.gharchive_events WHERE _source_file = '{filename}'{scope_filter}",
        database="bronze",
    )
    inserted_rows = int(count_str or 0)
    logger.info(
        f"Đã nạp thành công {inserted_rows:,} dòng từ '{filename}' vào bảng bronze.gharchive_events!"
    )
    return inserted_rows

