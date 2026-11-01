"""
Airflow DAG: Pipeline Medallion (Bronze -> Silver -> Gold) cho dữ liệu GH Archive:
1. Tải dữ liệu GH Archive (https://www.gharchive.org/) theo từng giờ (@hourly)
2. Giải nén, chuyển đổi sang định dạng Parquet và đẩy lên S3 MinIO (bronze/events_parquet)
3. Nạp trực tiếp từ MinIO Parquet vào ClickHouse tầng Bronze (`bronze.gharchive_events`)
4. Chạy dbt (`dbt run` & `dbt test`) để biến đổi dữ liệu sang tầng Silver và Gold trên ClickHouse
"""
from datetime import datetime, timedelta
import logging
import os
import subprocess
import sys

from airflow.decorators import dag, task
from airflow.models.param import Param

# Đảm bảo thư mục scripts nằm trong sys.path
SCRIPTS_DIR = "/opt/airflow/scripts"
if SCRIPTS_DIR not in sys.path:
    sys.path.append(SCRIPTS_DIR)

from gharchive_extractor import (
    download_gharchive_file,
    convert_json_gz_to_parquet,
    upload_to_minio,
    cleanup_local_files,
)
from clickhouse_loader import load_minio_parquet_to_bronze

logger = logging.getLogger("gharchive_medallion_dag")

DEFAULT_ARGS = {
    "owner": "data-engineer",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
}

DBT_PROJECT_DIR = "/opt/airflow/dbt_gharchive"


@dag(
    dag_id="gharchive_to_minio_hourly",
    description="Pipeline GH Archive -> MinIO Parquet -> ClickHouse (Bronze -> dbt Silver -> dbt Gold)",
    schedule="@hourly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["gharchive", "minio", "clickhouse", "dbt", "medallion"],
    params={
        "custom_date": Param(
            default="",
            type=["null", "string"],
            description="(Tùy chọn) Nhập ngày cụ thể YYYY-MM-DD nếu chạy thủ công, để trống sẽ lấy theo khung giờ logical_date (ví dụ: 2025-01-15)",
        ),
        "custom_hour": Param(
            default=None,
            type=["null", "integer"],
            description="(Tùy chọn) Nhập giờ cụ thể (0-23) nếu chạy thủ công, để trống sẽ lấy theo giờ logical_date",
        ),
        "upload_raw_gz": Param(
            default=False,
            type="boolean",
            description="Có lưu thêm bản gốc .json.gz vào MinIO hay không?",
        ),
    },
)
def gharchive_medallion_pipeline():

    @task(task_id="resolve_target_datetime")
    def resolve_target_datetime(**context) -> dict:
        """Xác định ngày (YYYY-MM-DD) và giờ (0-23) cần lấy từ GH Archive."""
        params = context["params"]
        custom_date = params.get("custom_date")
        custom_hour = params.get("custom_hour")

        if custom_date and custom_hour is not None:
            return {
                "date_str": str(custom_date).strip(),
                "hour": int(custom_hour),
                "upload_raw_gz": bool(params.get("upload_raw_gz", False)),
            }

        dt = context.get("data_interval_start") or context.get("logical_date")
        target_dt = dt - timedelta(hours=1)

        return {
            "date_str": target_dt.strftime("%Y-%m-%d"),
            "hour": int(target_dt.hour),
            "upload_raw_gz": bool(params.get("upload_raw_gz", False)),
        }

    @task(task_id="download_from_gharchive")
    def task_download(target: dict) -> dict:
        """Tải file {YYYY-MM-DD}-{H}.json.gz từ https://data.gharchive.org/"""
        local_gz_path = download_gharchive_file(
            date_str=target["date_str"],
            hour=target["hour"],
            output_dir="/opt/airflow/data/raw",
        )
        return {
            **target,
            "raw_gz_path": local_gz_path,
        }

    @task(task_id="convert_to_parquet")
    def task_convert_parquet(meta: dict) -> dict:
        """Giải nén file .json.gz và chuẩn hóa sang định dạng Parquet (nén Snappy)."""
        parquet_path = convert_json_gz_to_parquet(
            raw_gz_path=meta["raw_gz_path"],
            output_dir="/opt/airflow/data/parquet",
        )
        return {
            **meta,
            "parquet_path": parquet_path,
        }

    @task(task_id="upload_to_minio_s3")
    def task_upload_minio(meta: dict) -> dict:
        """Đẩy file Parquet lên S3 MinIO theo phân vùng year/month/day."""
        bucket_name = os.getenv("MINIO_BUCKET_NAME", "gharchive")
        uploaded_uris = {}

        if meta.get("upload_raw_gz"):
            raw_uri = upload_to_minio(
                local_file_path=meta["raw_gz_path"],
                date_str=meta["date_str"],
                hour=meta["hour"],
                bucket_name=bucket_name,
                layer_prefix="bronze/events_raw",
            )
            uploaded_uris["bronze_raw_uri"] = raw_uri

        parquet_uri = upload_to_minio(
            local_file_path=meta["parquet_path"],
            date_str=meta["date_str"],
            hour=meta["hour"],
            bucket_name=bucket_name,
            layer_prefix="bronze/events_parquet",
        )
        uploaded_uris["bronze_parquet_uri"] = parquet_uri

        return {
            **meta,
            **uploaded_uris,
        }

    @task(task_id="load_to_clickhouse_bronze")
    def task_load_clickhouse_bronze(meta: dict) -> dict:
        """Nạp trực tiếp file Parquet từ MinIO vào bảng ClickHouse `bronze.gharchive_events`."""
        inserted_rows = load_minio_parquet_to_bronze(
            date_str=meta["date_str"],
            hour=meta["hour"],
            bucket_name=os.getenv("MINIO_BUCKET_NAME", "gharchive"),
            layer_prefix="bronze/events_parquet",
        )
        return {
            **meta,
            "bronze_inserted_rows": inserted_rows,
        }

    @task(task_id="dbt_transform_silver_gold")
    def task_dbt_transform(meta: dict) -> dict:
        """Chạy `dbt run` và `dbt test` để cập nhật tầng Silver và Gold trên ClickHouse."""
        dbt_bin = "/opt/airflow/dbt_venv/bin/dbt"
        if not os.path.exists(dbt_bin):
            dbt_bin = "dbt"

        for subcmd in (["run"], ["test"]):
            cmd = [
                dbt_bin,
                *subcmd,
                "--project-dir",
                DBT_PROJECT_DIR,
                "--profiles-dir",
                DBT_PROJECT_DIR,
            ]
            logger.info(f"Đang thực thi lệnh dbt: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=DBT_PROJECT_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
            logger.info(result.stdout)
            if result.returncode != 0:
                logger.error(result.stderr)
                raise RuntimeError(f"Lệnh {' '.join(cmd)} thất bại với mã lỗi {result.returncode}")

        return meta

    @task(task_id="cleanup_temp_files", trigger_rule="all_done")
    def task_cleanup(meta: dict) -> str:
        """Xóa các file tạm (.json.gz và .parquet) trên container sau khi pipeline chạy xong."""
        cleanup_local_files(
            meta.get("raw_gz_path"),
            meta.get("parquet_path"),
        )
        return meta.get("bronze_parquet_uri", "Cleaned up")

    # Luồng thực thi (Pipeline Dependency)
    target_info = resolve_target_datetime()
    downloaded_meta = task_download(target_info)
    parquet_meta = task_convert_parquet(downloaded_meta)
    uploaded_meta = task_upload_minio(parquet_meta)
    bronze_meta = task_load_clickhouse_bronze(uploaded_meta)
    dbt_meta = task_dbt_transform(bronze_meta)
    task_cleanup(dbt_meta)


gharchive_medallion_pipeline()
