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
    DEFAULT_TRACKED_REPOS,
    download_gharchive_file,
    convert_json_gz_to_parquet,
    iter_date_hours,
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
            description="(Tùy chọn) Ngày bắt đầu YYYY-MM-DD nếu chạy thủ công, để trống sẽ lấy theo khung giờ logical_date (ví dụ: 2025-01-15)",
        ),
        "end_date": Param(
            default="",
            type=["null", "string"],
            description="(Tùy chọn) Ngày kết thúc YYYY-MM-DD để tải hàng loạt nhiều ngày liên tiếp (để trống nếu chỉ tải 1 ngày custom_date)",
        ),
        "custom_hour": Param(
            default=None,
            type=["null", "integer"],
            description="(Tùy chọn) Giờ cụ thể (0-23). Nếu để null khi có custom_date, pipeline sẽ tải dải giờ từ start_hour đến end_hour",
        ),
        "start_hour": Param(
            default=0,
            type="integer",
            description="Giờ bắt đầu (0-23) khi tải nhiều giờ/nhiều ngày",
        ),
        "end_hour": Param(
            default=23,
            type="integer",
            description="Giờ kết thúc (0-23) khi tải nhiều giờ/nhiều ngày",
        ),
        "hours_step": Param(
            default=1,
            type="integer",
            description="Bước nhảy giờ (1 = lấy đủ 24 giờ/ngày; 4 hoặc 6 = lấy mẫu nhẹ cho máy cá nhân)",
        ),
        "filter_default_repos": Param(
            default=True,
            type="boolean",
            description="Bật lọc chỉ giữ 50 repositories phổ biến (giảm ~98% dung lượng RAM/ổ cứng cho máy cá nhân mà vẫn đủ dữ liệu train model)",
        ),
        "max_records_per_file": Param(
            default=None,
            type=["null", "integer"],
            description="(Tùy chọn) Giới hạn số events tối đa giữ lại trên mỗi file giờ (ví dụ: 50000)",
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
        """Xác định danh sách các khung giờ (date_str, hour) cần lấy từ GH Archive."""
        params = context["params"]
        custom_date = (params.get("custom_date") or "").strip()
        end_date = (params.get("end_date") or "").strip() or custom_date
        custom_hour = params.get("custom_hour")
        filter_default_repos = bool(params.get("filter_default_repos", True))
        max_records_per_file = params.get("max_records_per_file")
        upload_raw_gz = bool(params.get("upload_raw_gz", False))

        if custom_date:
            if custom_hour is not None:
                s_hour = e_hour = int(custom_hour)
                step = 1
            else:
                s_hour = int(params.get("start_hour", 0))
                e_hour = int(params.get("end_hour", 23))
                step = int(params.get("hours_step", 1))

            targets = [
                {"date_str": d, "hour": h}
                for d, h in iter_date_hours(
                    start_date=custom_date,
                    end_date=end_date,
                    start_hour=s_hour,
                    end_hour=e_hour,
                    hours_step=step,
                )
            ]
            return {
                "date_str": targets[0]["date_str"],
                "hour": targets[0]["hour"],
                "targets": targets,
                "filter_default_repos": filter_default_repos,
                "max_records_per_file": max_records_per_file,
                "upload_raw_gz": upload_raw_gz,
            }

        dt = context.get("data_interval_start") or context.get("logical_date")
        target_dt = dt - timedelta(hours=1)
        d_str = target_dt.strftime("%Y-%m-%d")
        hr = int(target_dt.hour)

        return {
            "date_str": d_str,
            "hour": hr,
            "targets": [{"date_str": d_str, "hour": hr}],
            "filter_default_repos": filter_default_repos,
            "max_records_per_file": max_records_per_file,
            "upload_raw_gz": upload_raw_gz,
        }

    @task(task_id="download_from_gharchive")
    def task_download(target: dict) -> dict:
        """Tải một hoặc nhiều file {YYYY-MM-DD}-{H}.json.gz từ https://data.gharchive.org/"""
        targets = target.get("targets") or [{"date_str": target["date_str"], "hour": target["hour"]}]
        downloaded_items = []

        for item in targets:
            try:
                local_gz_path = download_gharchive_file(
                    date_str=item["date_str"],
                    hour=item["hour"],
                    output_dir="/opt/airflow/data/raw",
                )
                downloaded_items.append({
                    "date_str": item["date_str"],
                    "hour": item["hour"],
                    "raw_gz_path": local_gz_path,
                })
            except FileNotFoundError as exc:
                logger.warning(f"Bỏ qua file không tồn tại trên GH Archive: {exc}")
                if len(targets) == 1:
                    raise

        if not downloaded_items:
            raise RuntimeError("Không tải được bất kỳ file GH Archive nào trong khoảng yêu cầu.")

        return {
            **target,
            "raw_gz_path": downloaded_items[0]["raw_gz_path"],
            "items": downloaded_items,
        }

    @task(task_id="convert_to_parquet")
    def task_convert_parquet(meta: dict) -> dict:
        """Giải nén các file .json.gz và chuẩn hóa sang định dạng Parquet (nén Snappy)."""
        items = meta.get("items") or [
            {"date_str": meta["date_str"], "hour": meta["hour"], "raw_gz_path": meta["raw_gz_path"]}
        ]
        tracked_repos = list(DEFAULT_TRACKED_REPOS) if meta.get("filter_default_repos") else None
        max_records = meta.get("max_records_per_file")

        converted_items = []
        for item in items:
            parquet_path = convert_json_gz_to_parquet(
                raw_gz_path=item["raw_gz_path"],
                output_dir="/opt/airflow/data/parquet",
                tracked_repos=tracked_repos,
                max_records_per_file=max_records,
            )
            converted_items.append({
                **item,
                "parquet_path": parquet_path,
            })

        return {
            **meta,
            "parquet_path": converted_items[0]["parquet_path"],
            "items": converted_items,
        }

    @task(task_id="upload_to_minio_s3")
    def task_upload_minio(meta: dict) -> dict:
        """Đẩy các file Parquet lên S3 MinIO theo phân vùng year/month/day."""
        bucket_name = os.getenv("MINIO_BUCKET_NAME", "gharchive")
        items = meta.get("items") or [
            {
                "date_str": meta["date_str"],
                "hour": meta["hour"],
                "raw_gz_path": meta.get("raw_gz_path"),
                "parquet_path": meta["parquet_path"],
            }
        ]
        uploaded_items = []

        for item in items:
            item_uris = {}
            if meta.get("upload_raw_gz") and item.get("raw_gz_path"):
                raw_uri = upload_to_minio(
                    local_file_path=item["raw_gz_path"],
                    date_str=item["date_str"],
                    hour=item["hour"],
                    bucket_name=bucket_name,
                    layer_prefix="bronze/events_raw",
                )
                item_uris["bronze_raw_uri"] = raw_uri

            parquet_uri = upload_to_minio(
                local_file_path=item["parquet_path"],
                date_str=item["date_str"],
                hour=item["hour"],
                bucket_name=bucket_name,
                layer_prefix="bronze/events_parquet",
            )
            item_uris["bronze_parquet_uri"] = parquet_uri
            uploaded_items.append({**item, **item_uris})

        return {
            **meta,
            "bronze_parquet_uri": uploaded_items[-1]["bronze_parquet_uri"],
            "items": uploaded_items,
        }

    @task(task_id="load_to_clickhouse_bronze")
    def task_load_clickhouse_bronze(meta: dict) -> dict:
        """Nạp trực tiếp các file Parquet từ MinIO vào bảng ClickHouse `bronze.gharchive_events`."""
        bucket_name = os.getenv("MINIO_BUCKET_NAME", "gharchive")
        items = meta.get("items") or [{"date_str": meta["date_str"], "hour": meta["hour"]}]
        total_inserted = 0

        for item in items:
            inserted_rows = load_minio_parquet_to_bronze(
                date_str=item["date_str"],
                hour=item["hour"],
                bucket_name=bucket_name,
                layer_prefix="bronze/events_parquet",
            )
            total_inserted += inserted_rows

        return {
            **meta,
            "bronze_inserted_rows": total_inserted,
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
        if not meta:
            return "Cleaned up"
        paths_to_clean = [meta.get("raw_gz_path"), meta.get("parquet_path")]
        for item in meta.get("items") or []:
            paths_to_clean.append(item.get("raw_gz_path"))
            paths_to_clean.append(item.get("parquet_path"))
        cleanup_local_files(*paths_to_clean)
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
