"""
Script tự động khởi tạo trên Apache Superset:
1. Đảm bảo các database & bảng tầng Gold tồn tại trên ClickHouse
2. Tạo kết nối Database 'ClickHouse Gold Lakehouse'
3. Đăng ký các bảng Gold & Silver làm Datasets và nạp đầy đủ metadata cột
4. Tự động tạo 5 Biểu đồ (Charts/Slices) mẫu
5. Tự động ghép 5 Biểu đồ vào Dashboard 'GitHub Archive - Lakehouse Gold Analytics'
"""
import json
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("superset_bootstrap")


def ensure_clickhouse_gold_tables(ch_host: str, ch_port: int, ch_user: str, ch_password: str):
    """
    Đảm bảo database `gold` và cấu trúc 3 bảng Gold tồn tại trên ClickHouse
    (để ngay cả khi dbt chưa kịp chạy lần đầu, Superset vẫn lấy được đầy đủ cột cho Dashboard).
    """
    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host=ch_host,
        port=int(ch_port),
        username=ch_user,
        password=ch_password,
    )

    for db_name in ("bronze", "silver", "gold"):
        client.command(f"CREATE DATABASE IF NOT EXISTS {db_name}")

    client.command("""
    CREATE TABLE IF NOT EXISTS gold.gold_repo_daily_activity
    (
        event_date Date,
        repo_id Int64,
        repo_full_name String,
        repo_owner String,
        repo_short_name String,
        org_login Nullable(String),
        total_events UInt64,
        unique_contributors UInt64,
        unique_human_contributors UInt64,
        stars_gained UInt64,
        forks_count UInt64,
        push_events_count UInt64,
        total_commits_pushed Int64,
        prs_opened UInt64,
        prs_merged UInt64,
        prs_closed_unmerged UInt64,
        issues_opened UInt64,
        issues_closed UInt64,
        issue_comments_count UInt64,
        first_event_at DateTime,
        last_event_at DateTime
    )
    ENGINE = MergeTree()
    ORDER BY (event_date, total_events, repo_id)
    """)

    client.command("""
    CREATE TABLE IF NOT EXISTS gold.gold_actor_activity
    (
        event_date Date,
        actor_id Int64,
        actor_login String,
        is_bot UInt8,
        total_events UInt64,
        distinct_repos_interacted UInt64,
        push_events_count UInt64,
        total_commits_pushed Int64,
        prs_opened UInt64,
        pr_reviews_submitted UInt64,
        issues_opened UInt64,
        comments_made UInt64,
        repos_starred UInt64,
        first_active_at DateTime,
        last_active_at DateTime
    )
    ENGINE = MergeTree()
    ORDER BY (event_date, total_events, actor_id)
    """)

    client.command("""
    CREATE TABLE IF NOT EXISTS gold.gold_hourly_event_stats
    (
        event_date Date,
        event_hour UInt8,
        event_type LowCardinality(String),
        total_events UInt64,
        human_events UInt64,
        bot_events UInt64,
        unique_actors UInt64,
        unique_repositories UInt64
    )
    ENGINE = MergeTree()
    ORDER BY (event_date, event_hour, event_type)
    """)
    logger.info("Đã kiểm tra và đảm bảo các bảng tầng Gold trên ClickHouse sẵn sàng.")


def upsert_slice(db, Slice, slice_name: str, viz_type: str, dataset, params_dict: dict):
    """Tạo hoặc cập nhật một Chart (Slice) trên Superset."""
    full_params = {
        "datasource": f"{dataset.id}__table",
        "viz_type": viz_type,
        "adhoc_filters": [],
        **params_dict,
    }
    existing = (
        db.session.query(Slice)
        .filter_by(slice_name=slice_name, datasource_id=dataset.id, datasource_type="table")
        .one_or_none()
    )
    if not existing:
        slc = Slice(
            slice_name=slice_name,
            datasource_id=dataset.id,
            datasource_type="table",
            viz_type=viz_type,
            params=json.dumps(full_params),
        )
        db.session.add(slc)
        db.session.commit()
        logger.info(f"Đã tạo Chart: {slice_name} (ID={slc.id})")
        return slc
    else:
        existing.viz_type = viz_type
        existing.params = json.dumps(full_params)
        db.session.commit()
        logger.info(f"Đã cập nhật Chart: {slice_name} (ID={existing.id})")
        return existing


def build_dashboard_position_json(dashboard_title: str, slices: list) -> str:
    """
    Tạo cấu trúc JSON bố cục lưới (Grid Layout) chuẩn của Superset cho 5 biểu đồ:
    - Hàng 1: [Big Number: Tổng sự kiện (width 4)] + [Pie: Phân bố loại sự kiện (width 4)] + [Pie: Human vs Bot (width 4)]
    - Hàng 2: [Bảng: Top 20 Repositories (width 6)] + [Bảng: Top Active Developers (width 6)]
    """
    s_total, s_event_pie, s_bot_pie, s_top_repos, s_top_actors = slices

    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {
            "type": "ROOT",
            "id": "ROOT_ID",
            "children": ["GRID_ID"],
        },
        "HEADER_ID": {
            "id": "HEADER_ID",
            "type": "HEADER",
            "meta": {"text": dashboard_title},
        },
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": ["ROW-KPI-1", "ROW-TABLES-2"],
            "parents": ["ROOT_ID"],
        },
        "ROW-KPI-1": {
            "type": "ROW",
            "id": "ROW-KPI-1",
            "children": ["CHART-KPI-TOTAL", "CHART-PIE-EVENTS", "CHART-PIE-BOT"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "CHART-KPI-TOTAL": {
            "type": "CHART",
            "id": "CHART-KPI-TOTAL",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-KPI-1"],
            "meta": {
                "chartId": s_total.id,
                "sliceName": s_total.slice_name,
                "width": 4,
                "height": 45,
            },
        },
        "CHART-PIE-EVENTS": {
            "type": "CHART",
            "id": "CHART-PIE-EVENTS",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-KPI-1"],
            "meta": {
                "chartId": s_event_pie.id,
                "sliceName": s_event_pie.slice_name,
                "width": 4,
                "height": 45,
            },
        },
        "CHART-PIE-BOT": {
            "type": "CHART",
            "id": "CHART-PIE-BOT",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-KPI-1"],
            "meta": {
                "chartId": s_bot_pie.id,
                "sliceName": s_bot_pie.slice_name,
                "width": 4,
                "height": 45,
            },
        },
        "ROW-TABLES-2": {
            "type": "ROW",
            "id": "ROW-TABLES-2",
            "children": ["CHART-TABLE-REPOS", "CHART-TABLE-ACTORS"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "CHART-TABLE-REPOS": {
            "type": "CHART",
            "id": "CHART-TABLE-REPOS",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-TABLES-2"],
            "meta": {
                "chartId": s_top_repos.id,
                "sliceName": s_top_repos.slice_name,
                "width": 6,
                "height": 55,
            },
        },
        "CHART-TABLE-ACTORS": {
            "type": "CHART",
            "id": "CHART-TABLE-ACTORS",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-TABLES-2"],
            "meta": {
                "chartId": s_top_actors.id,
                "sliceName": s_top_actors.slice_name,
                "width": 6,
                "height": 55,
            },
        },
    }
    return json.dumps(layout)


def bootstrap():
    ch_host = os.getenv("CLICKHOUSE_HOST", "clickhouse")
    ch_port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    ch_user = os.getenv("CLICKHOUSE_USER", "default")
    ch_password = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse")

    # 1. Đảm bảo bảng Gold tồn tại trên ClickHouse
    ensure_clickhouse_gold_tables(ch_host, ch_port, ch_user, ch_password)

    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset.extensions import db
        from superset.models.core import Database
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.slice import Slice
        from superset.models.dashboard import Dashboard

        # 2. Tạo/Cập nhật Database Connection tới ClickHouse
        db_name = "ClickHouse Gold Lakehouse"
        sqlalchemy_uri = (
            f"clickhousedb+connect://{ch_user}:{ch_password}@{ch_host}:{ch_port}/gold"
        )

        database = (
            db.session.query(Database).filter_by(database_name=db_name).one_or_none()
        )
        if not database:
            logger.info(f"Đang tạo kết nối Superset Database: {db_name}")
            database = Database(
                database_name=db_name,
                sqlalchemy_uri=sqlalchemy_uri,
                expose_in_sqllab=True,
                allow_run_async=True,
                allow_ctas=True,
                allow_cvas=True,
                allow_dml=True,
            )
            db.session.add(database)
            db.session.commit()
        else:
            database.sqlalchemy_uri = sqlalchemy_uri
            db.session.commit()
            logger.info(f"Đã cập nhật kết nối Superset Database: {db_name}")

        # 3. Đăng ký các bảng Gold làm Datasets
        datasets_map = {}
        for schema_name, table_name in [
            ("gold", "gold_repo_daily_activity"),
            ("gold", "gold_actor_activity"),
            ("gold", "gold_hourly_event_stats"),
        ]:
            ds = (
                db.session.query(SqlaTable)
                .filter_by(
                    database_id=database.id,
                    schema=schema_name,
                    table_name=table_name,
                )
                .one_or_none()
            )
            if not ds:
                ds = SqlaTable(
                    database_id=database.id,
                    schema=schema_name,
                    table_name=table_name,
                )
                db.session.add(ds)
                db.session.commit()
            ds.fetch_metadata()
            db.session.commit()
            datasets_map[table_name] = ds
            logger.info(f"Đã đồng bộ Dataset: {schema_name}.{table_name} (ID={ds.id})")

        ds_hourly = datasets_map["gold_hourly_event_stats"]
        ds_repos = datasets_map["gold_repo_daily_activity"]
        ds_actors = datasets_map["gold_actor_activity"]

        # 4. Tạo 5 Biểu đồ (Slices)
        sum_total_events_metric = {
            "expressionType": "SQL",
            "sqlExpression": "SUM(total_events)",
            "label": "Tổng sự kiện",
        }

        # Chart 1: Tổng số sự kiện GitHub (Big Number)
        s_total = upsert_slice(
            db,
            Slice,
            slice_name="Tổng số Sự kiện GitHub (Total Events)",
            viz_type="big_number_total",
            dataset=ds_hourly,
            params_dict={
                "metric": sum_total_events_metric,
                "subheader": "Tổng lưu lượng sự kiện đã xử lý qua tầng Gold",
                "y_axis_format": ",d",
            },
        )

        # Chart 2: Tỷ lệ các loại Sự kiện GitHub (Pie Chart)
        s_event_pie = upsert_slice(
            db,
            Slice,
            slice_name="Phân bố các loại Sự kiện (Event Types)",
            viz_type="pie",
            dataset=ds_hourly,
            params_dict={
                "groupby": ["event_type"],
                "metric": sum_total_events_metric,
                "row_limit": 15,
                "show_labels": True,
                "show_legend": True,
                "donut": True,
            },
        )

        # Chart 3: Tỷ lệ hoạt động Người thật vs Bot (Pie Chart)
        s_bot_pie = upsert_slice(
            db,
            Slice,
            slice_name="Tỷ lệ sự kiện: Lập trình viên vs Bot",
            viz_type="pie",
            dataset=ds_actors,
            params_dict={
                "groupby": ["is_bot"],
                "metric": sum_total_events_metric,
                "row_limit": 10,
                "show_labels": True,
                "show_legend": True,
                "donut": True,
            },
        )

        # Chart 4: Top 20 Repositories sôi động nhất (Table)
        s_top_repos = upsert_slice(
            db,
            Slice,
            slice_name="Top 20 Repositories sôi động nhất (Stars, Commits, PRs)",
            viz_type="table",
            dataset=ds_repos,
            params_dict={
                "query_mode": "raw",
                "all_columns": [
                    "event_date",
                    "repo_full_name",
                    "stars_gained",
                    "forks_count",
                    "total_commits_pushed",
                    "prs_opened",
                    "issues_opened",
                    "unique_contributors",
                    "total_events",
                ],
                "order_by_cols": ['["total_events", false]'],
                "row_limit": 20,
                "include_search": True,
            },
        )

        # Chart 5: Top 20 Lập trình viên đóng góp nhiều nhất (Table)
        s_top_actors = upsert_slice(
            db,
            Slice,
            slice_name="Top 20 Lập trình viên hoạt động tích cực nhất",
            viz_type="table",
            dataset=ds_actors,
            params_dict={
                "query_mode": "raw",
                "all_columns": [
                    "event_date",
                    "actor_login",
                    "is_bot",
                    "total_commits_pushed",
                    "push_events_count",
                    "prs_opened",
                    "issues_opened",
                    "distinct_repos_interacted",
                    "total_events",
                ],
                "order_by_cols": ['["total_events", false]'],
                "row_limit": 20,
                "include_search": True,
            },
        )

        all_slices = [s_total, s_event_pie, s_bot_pie, s_top_repos, s_top_actors]

        # 5. Tạo hoặc cập nhật Dashboard
        dashboard_title = "GitHub Archive - Lakehouse Gold Analytics"
        dashboard_slug = "gharchive-gold-analytics"

        dashboard = (
            db.session.query(Dashboard)
            .filter_by(slug=dashboard_slug)
            .one_or_none()
        )
        position_json = build_dashboard_position_json(dashboard_title, all_slices)

        if not dashboard:
            dashboard = Dashboard(
                dashboard_title=dashboard_title,
                slug=dashboard_slug,
                slices=all_slices,
                position_json=position_json,
                published=True,
            )
            db.session.add(dashboard)
            db.session.commit()
            logger.info(f"Đã khởi tạo Dashboard: '{dashboard_title}' (/superset/dashboard/{dashboard_slug}/)")
        else:
            dashboard.dashboard_title = dashboard_title
            dashboard.slices = all_slices
            dashboard.position_json = position_json
            dashboard.published = True
            db.session.commit()
            logger.info(f"Đã cập nhật Dashboard: '{dashboard_title}' (/superset/dashboard/{dashboard_slug}/)")


if __name__ == "__main__":
    bootstrap()
