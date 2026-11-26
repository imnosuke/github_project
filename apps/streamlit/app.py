"""Local Streamlit application for repository analytics."""
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

# Supports `streamlit run apps/streamlit/app.py` from any working directory.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from apps.streamlit.data import get_adapter
from apps.streamlit.explorer import render_explorer
from apps.streamlit.analytics import default_date_range, render_growth, render_overview

st.set_page_config(page_title="RepoScope · GitHub Analytics", page_icon="📊", layout="wide")


@st.cache_resource(ttl=300)
def load_adapter(source, directory, interface_version, connection_key=None):
    # Include the consumer interface in the cache key across hot reloads.
    return get_adapter(source=source, directory=directory)


def main():
    source = os.getenv("APP_DATA_SOURCE", "fixture")
    pipeline_runs_file = os.getenv("APP_PIPELINE_RUNS_FILE")
    pipeline_fixture = source == "fixture" and os.getenv("APP_ENABLE_PIPELINE_FIXTURE") == "1"
    with st.sidebar:
        st.header("RepoScope")
        pages = ["Overview", "Repository Explorer", "Growth Analytics"]
        if pipeline_runs_file or pipeline_fixture:
            pages.append("Pipeline Health")
        page = st.radio("Trang", pages, key="page", label_visibility="collapsed")
        st.divider()

    if page == "Pipeline Health":
        if pipeline_runs_file:
            from apps.streamlit.pipeline_runs import render_pipeline_runs

            render_pipeline_runs(Path(pipeline_runs_file))
        else:
            from apps.streamlit.pipeline_fixture import render_pipeline_fixture

            st.title(page)
            render_pipeline_fixture()
        return

    st.title(page)
    directory = os.getenv("APP_FIXTURE_DIR") or str(Path(__file__).parent / "data" / "fixtures")
    if source in {"snapshot", "clickhouse_snapshot"}:
        directory = os.getenv("APP_SNAPSHOT_DIR")
    connection_key = None
    if source in {"clickhouse", "clickhouse_snapshot"}:
        settings = {key: value for key, value in os.environ.items() if key.startswith("APP_CLICKHOUSE_")}
        connection_key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode("utf8")).hexdigest()
    try:
        with st.spinner("Đang tải dữ liệu…"):
            adapter = load_adapter(source, directory, interface_version="app-07-v1", connection_key=connection_key)
            envelope = adapter.publication()
    except Exception as exc:
        st.error("Không thể tải nguồn dữ liệu.")
        with st.expander("Chi tiết lỗi"):
            st.code(str(exc))
        if st.button("Thử lại"):
            load_adapter.clear()
            st.rerun()
        return

    bounds = adapter.date_bounds()
    if bounds is None:
        st.info("Nguồn chưa có dữ liệu theo ngày.")
        return
    lower, upper = (date.fromisoformat(value) for value in bounds)
    latest = adapter.latest_complete_date()
    expected = envelope.get("expected_complete_through")
    if latest is None:
        st.error("Chưa có ngày nào complete.")
    elif expected and latest < expected:
        st.warning(f"Dữ liệu trễ · Có đến {latest} · Mốc kỳ vọng {expected} UTC")

    selected = st.sidebar.date_input("Khoảng ngày (UTC)", value=default_date_range(adapter, lower, upper, latest),
                                     min_value=lower, max_value=upper, key="date_range")
    with st.sidebar.expander("Thông tin nguồn"):
        st.caption(f"Bản dữ liệu · {envelope['publication_id']}")
        st.caption(f"Nguồn dữ liệu · {envelope['data_source']}")
        st.caption(f"Công bố · {envelope['published_at']}")
        if latest:
            st.caption(f"Ngày complete gần nhất · {latest} UTC")
        if st.button("Tải lại dữ liệu"):
            load_adapter.clear()
            st.rerun()

    if len(selected) != 2:
        st.info("Khoảng ngày chưa đủ.")
        return
    start, end = (d.isoformat() for d in selected)
    if start > end:
        st.error("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        return
    source_label = {
        "fixture": "DEMO · Dữ liệu tổng hợp",
        "snapshot": "GH Archive · Snapshot",
        "clickhouse_snapshot": "GH Archive · ClickHouse local",
        "clickhouse": "GitHub · ClickHouse Gold",
    }[source]
    date_label = f" · {start} → {end} UTC" if page != "Growth Analytics" else ""
    st.caption(f"{source_label}{date_label}")
    coverage_notice = st.empty()
    coverage_start = start

    if page == "Overview":
        render_overview(adapter, start, end)
    elif page == "Repository Explorer":
        repository_id = render_explorer(adapter, start, end)
        if source == "clickhouse" and os.getenv("APP_ENABLE_PREDICTIONS") == "1" and repository_id is not None:
            from apps.streamlit.predictions import render_predictions

            render_predictions(adapter, end, repository_id)
    else:
        coverage_start = render_growth(adapter, end)
        if source == "clickhouse" and os.getenv("APP_ENABLE_PREDICTIONS") == "1":
            from apps.streamlit.predictions import render_predictions

            render_predictions(adapter, end)

    dates = pd.date_range(coverage_start, end).strftime("%Y-%m-%d")
    selected_status = adapter.day_status(coverage_start, end)
    unknown = len(set(dates) - set(selected_status.date))
    incomplete = int((selected_status.status != "complete").sum()) + unknown
    if incomplete:
        scope = "Hai kỳ so sánh" if page == "Growth Analytics" else "Khoảng ngày đã chọn"
        coverage_notice.warning(f"{scope} · {incomplete} ngày chưa complete")

    with st.expander("Trạng thái dữ liệu theo ngày"):
        st.dataframe(
            selected_status,
            hide_index=True,
            width="stretch",
            column_config={
                "date": st.column_config.DateColumn("Ngày (UTC)"),
                "status": st.column_config.TextColumn("Trạng thái"),
                "expected_files": st.column_config.NumberColumn("File kỳ vọng", format="%d"),
                "processed_files": st.column_config.NumberColumn("File đã xử lý", format="%d"),
                "quality_passed": st.column_config.CheckboxColumn("Quality passed"),
                "published_at": st.column_config.TextColumn("Công bố (UTC)"),
                "reason": st.column_config.TextColumn("Ghi chú / Lý do"),
            }
        )

main()

