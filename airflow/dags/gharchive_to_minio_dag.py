"""
Airflow DAG: Pipeline Medallion (Bronze -> Silver -> Gold) cho dữ liệu GH Archive:
1. Tải dữ liệu GH Archive (https://www.gharchive.org/) theo từng giờ (@hourly)
2. Giải nén, chuyển đổi sang định dạng Parquet và đẩy lên S3 MinIO (bronze/events_parquet)
3. Nạp trực tiếp từ MinIO Parquet vào ClickHouse tầng Bronze (`bronze.gharchive_events`)
4. Chạy dbt (`dbt run` & `dbt test`) để biến đổi dữ liệu sang tầng Silver và Gold trên ClickHouse
"""
from datetime import datetime, timedelta
import json
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
    iter_date_hours,
    stream_https_raw_gz_to_minio,
    stream_https_to_minio_parquet,
)
from clickhouse_loader import load_minio_parquet_to_bronze
from app02_publisher import publish, read_registry, scope_key

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
            description="(Tùy chọn) Để trống cho DAG chuẩn. Dùng CLI riêng khi cần lấy mẫu giới hạn record.",
        ),
        "upload_raw_gz": Param(
            default=False,
            type="boolean",
            description="Có lưu thêm bản gốc .json.gz vào MinIO hay không?",
        ),
        "dbt_full_refresh": Param(
            default=False,
            type="boolean",
            description="Bật True ở lần init đầu tiên (hoặc khi cần rebuild toàn bộ lịch sử); để False ở các ngày sau để chỉ transform incremental đúng ngày mới nạp.",
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
        registry_path = os.getenv("APP02_REGISTRY_FILE")
        registry = read_registry(registry_path) if registry_path else None

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
            if not targets:
                raise ValueError("No finished GH Archive hours in requested range")
            return {
                "date_str": targets[0]["date_str"],
                "hour": targets[0]["hour"],
                "targets": targets,
                "filter_default_repos": filter_default_repos,
                "max_records_per_file": max_records_per_file,
                "upload_raw_gz": upload_raw_gz,
                "app02_registry": registry,
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
            "app02_registry": registry,
        }

    @task(task_id="stream_gharchive_to_minio_s3")
    def task_stream_to_minio(target: dict) -> dict:
        """
        Stream trực tiếp từ HTTPS GH Archive, giải nén Gzip và đóng gói Parquet
        ngay trên RAM (io.BytesIO) rồi đẩy thẳng lên S3 MinIO (0 byte ghi xuống ổ cứng).
        """
        bucket_name = os.getenv("MINIO_BUCKET_NAME", "gharchive")
        targets = target.get("targets") or [{"date_str": target["date_str"], "hour": target["hour"]}]
        tracked_repos = list(DEFAULT_TRACKED_REPOS) if target.get("filter_default_repos") else None
        registry = target.get("app02_registry")
        repo_ids = {row["repository_id"] for row in registry} if registry else None
        layer = f"bronze/events_parquet/{scope_key(registry)}" if registry else "bronze/events_parquet"
        if target.get("max_records_per_file") is not None or os.getenv("GHARCHIVE_MAX_RECORDS_PER_FILE", "").strip():
            raise ValueError("Record caps belong in the sample extractor, outside the canonical DAG")

        uploaded_items = []
        for item in targets:
            item_uris = {}
            if target.get("upload_raw_gz"):
                raw_uri = stream_https_raw_gz_to_minio(
                    date_str=item["date_str"],
                    hour=item["hour"],
                    bucket_name=bucket_name,
                    layer_prefix="bronze/events_raw",
                )
                item_uris["bronze_raw_uri"] = raw_uri

            res = stream_https_to_minio_parquet(
                date_str=item["date_str"],
                hour=item["hour"],
                bucket_name=bucket_name,
                layer_prefix=layer,
                tracked_repos=tracked_repos,
                tracked_repository_ids=repo_ids,
            )
            item_uris["bronze_parquet_uri"] = res["s3_uri"]
            item_uris["records"] = res["records"]
            item_uris["size_mb"] = res["size_mb"]
            uploaded_items.append({
                "date_str": item["date_str"],
                "hour": item["hour"],
                **item_uris,
            })

        if not uploaded_items:
            raise RuntimeError("Không stream được bất kỳ file GH Archive nào lên MinIO trong khoảng yêu cầu.")

        return {
            **target,
            "bronze_parquet_uri": uploaded_items[-1]["bronze_parquet_uri"],
            "items": uploaded_items,
            "parquet_layer": layer,
        }

    @task(task_id="load_to_clickhouse_bronze")
    def task_load_clickhouse_bronze(meta: dict) -> dict:
        """Nạp trực tiếp các file Parquet từ MinIO vào bảng ClickHouse `bronze.gharchive_events`."""
        bucket_name = os.getenv("MINIO_BUCKET_NAME", "gharchive")
        items = meta.get("items") or [{"date_str": meta["date_str"], "hour": meta["hour"]}]
        total_inserted = 0
        registry = meta.get("app02_registry")
        repo_ids = {row["repository_id"] for row in registry} if registry else None

        for item in items:
            inserted_rows = load_minio_parquet_to_bronze(
                date_str=item["date_str"],
                hour=item["hour"],
                bucket_name=bucket_name,
                layer_prefix=meta.get("parquet_layer", "bronze/events_parquet"),
                repository_ids=repo_ids,
            )
            if inserted_rows != item["records"]:
                raise RuntimeError(f"Bronze count differs from uploaded Parquet for {item['date_str']}-{item['hour']}")
            total_inserted += inserted_rows

        return {
            **meta,
            "bronze_inserted_rows": total_inserted,
        }

    @task(task_id="dbt_transform_silver_gold")
    def task_dbt_transform(meta: dict, **context) -> dict:
        """
        Chạy `dbt run` và `dbt test` để cập nhật tầng Silver và Gold trên ClickHouse.
        - Lần init đầu tiên (chưa có bảng hoặc bật `dbt_full_refresh=True`): transform toàn bộ dữ liệu.
        - Các lần chạy sau: chỉ transform incremental đúng các ngày vừa nạp (`target_dates`), cực nhanh và không tốn RAM.
        """
        dbt_bin = "/opt/airflow/dbt_venv/bin/dbt"
        if not os.path.exists(dbt_bin):
            dbt_bin = "dbt"

        params = context.get("params") or {}
        full_refresh = bool(params.get("dbt_full_refresh", False))

        items = meta.get("items") or [{"date_str": meta["date_str"], "hour": meta["hour"]}]
        target_dates_str = ",".join(sorted({item["date_str"] for item in items if item.get("date_str")}))
        dbt_vars = json.dumps({"target_dates": target_dates_str})

        run_args = ["run"]
        if full_refresh:
            run_args.append("--full-refresh")

        for subcmd in (run_args, ["test"]):
            cmd = [
                dbt_bin,
                *subcmd,
                "--project-dir",
                DBT_PROJECT_DIR,
                "--profiles-dir",
                DBT_PROJECT_DIR,
                "--vars",
                dbt_vars,
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

    @task(task_id="publish_app02_gold", multiple_outputs=True)
    def task_publish_app02(meta: dict, **context) -> dict:
        registry = meta.get("app02_registry")
        if registry is None:
            return {"enabled": False}
        publication = publish(registry, meta["items"], context["run_id"],
                              os.getenv("APP02_SCHEMA_PATH", "/opt/airflow/app-02-serving-schema.sql"),
                              window_days=int(os.getenv("APP02_WINDOW_DAYS", "61")))
        logger.info("APP-02 published %s from run %s", publication["publication_id"], context["run_id"])
        return {"enabled": True, **publication}

    # Luồng thực thi (Pipeline Dependency): Direct HTTPS -> RAM Parquet -> MinIO S3 -> ClickHouse
    target_info = resolve_target_datetime()
    uploaded_meta = task_stream_to_minio(target_info)
    bronze_meta = task_load_clickhouse_bronze(uploaded_meta)
    task_publish_app02(task_dbt_transform(bronze_meta))


gharchive_medallion_pipeline()
