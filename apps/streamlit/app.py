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
from apps.streamlit.analytics import render_overview, render_growth

st.set_page_config(page_title="RepoScope · GitHub Analytics", page_icon="📊", layout="wide")


@st.cache_resource(ttl=300)
def load_adapter(source, directory, interface_version, connection_key=None):
    # Include the consumer interface in the cache key across hot reloads.
    return get_adapter(source=source, directory=directory)


def main():
    st.title("RepoScope")
    st.caption("GitHub activity · Repository Explorer · Growth Analytics")
    source = os.getenv("APP_DATA_SOURCE", "fixture")
    directory = os.getenv("APP_FIXTURE_DIR") or str(Path(__file__).parent / "data" / "fixtures")
    if source in {"snapshot", "clickhouse_snapshot"}:
        directory = os.getenv("APP_SNAPSHOT_DIR")
    connection_key = None
    if source in {"clickhouse", "clickhouse_snapshot"}:
        settings = {key: value for key, value in os.environ.items() if key.startswith("APP_CLICKHOUSE_")}
        connection_key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode("utf8")).hexdigest()
    try:
        with st.spinner("Đang kiểm tra và tải dữ liệu…"):
            adapter = load_adapter(source, directory, interface_version="app-07-v1", connection_key=connection_key)
            envelope = adapter.publication()
    except Exception as exc:
        st.error("Không thể tải nguồn dữ liệu. Kiểm tra cấu hình và thư mục dữ liệu.")
        with st.expander("Chi tiết lỗi"):
            st.code(str(exc))
        if st.button("Thử lại"):
            load_adapter.clear()
            st.rerun()
        return

    if envelope["data_source"] == "fixture":
        st.warning("DEMO — Dữ liệu tổng hợp, không phải hoạt động GitHub thực tế hoặc kết quả ML.")
    elif source == "clickhouse_snapshot":
        st.info("ClickHouse cục bộ · Chỉ số Gold đã đối soát với snapshot GH Archive.")
    elif envelope["data_source"] == "snapshot":
        st.info("Snapshot tĩnh từ GH Archive · Số liệu theo repo và ngày trong đợt trích xuất.")
    with st.sidebar:
        st.header("Điều hướng")
        page = st.radio("Trang", ["Overview", "Repository Explorer", "Growth Analytics"], key="page")
        st.divider()
        st.caption(f"Nguồn: {source if source == 'clickhouse_snapshot' else envelope['data_source']}")
        st.caption(f"Publication: {envelope['publication_id']}")
        st.caption(f"Công bố (UTC): {envelope['published_at']}")
        if st.button("Tải lại dữ liệu"):
            load_adapter.clear()
            st.rerun()

    bounds = adapter.date_bounds()
    if bounds is None:
        st.info("Nguồn chưa có ngày dữ liệu nào. Hãy kiểm tra thư mục dữ liệu hoặc chờ lần công bố tiếp theo.")
        return
    lower, upper = (date.fromisoformat(value) for value in bounds)
    latest = adapter.latest_complete_date()
    expected = envelope.get("expected_complete_through")
    if latest is None:
        st.error("Chưa có ngày nào complete.")
    elif expected is None:
        st.info(f"Complete gần nhất: {latest} UTC. Chưa cấu hình kỳ vọng freshness.")
    elif latest < expected:
        st.warning(f"Dữ liệu stale: complete gần nhất {latest}, kỳ vọng đến {expected} UTC.")
    elif envelope["data_source"] == "fixture":
        st.caption(f"Complete gần nhất: {latest} UTC · Kỳ vọng fixture: {expected}. Freshness này theo manifest demo, không theo ngày hiện tại.")
    else:
        st.caption(f"Complete gần nhất: {latest} UTC · Kỳ vọng theo publication: {expected} UTC.")

    start_default = max(lower, (pd.Timestamp(latest or upper) - pd.Timedelta(days=29)).date())
    end_default = date.fromisoformat(latest) if latest else upper
    selected = st.sidebar.date_input("Khoảng ngày (UTC)", value=(start_default, end_default),
                                     min_value=lower, max_value=upper, key="date_range")
    if len(selected) != 2:
        st.info("Chọn đủ ngày bắt đầu và kết thúc để xem nội dung.")
        return
    start, end = (d.isoformat() for d in selected)
    if start > end:
        st.error("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        return
    st.subheader(page)
    st.caption(f"Bộ lọc dùng chung: {start} → {end}, gồm cả hai đầu ngày UTC.")
    dates = pd.date_range(start, end).strftime("%Y-%m-%d")
    selected_status = adapter.day_status(start, end)
    unknown = len(set(dates) - set(selected_status.date))
    incomplete = int((selected_status.status != "complete").sum()) + unknown
    if incomplete:
        st.warning(f"Khoảng đã chọn có {incomplete} ngày thiếu, chưa complete hoặc chưa rõ trạng thái. Không công bố KPI tổng/growth cho toàn kỳ.")
    with st.expander("Trạng thái dữ liệu trong kỳ", expanded=bool(incomplete)):
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

    if page == "Overview":
        render_overview(adapter, start, end)
    elif page == "Repository Explorer":
        render_explorer(adapter, start, end)
    else:
        render_growth(adapter, start, end)


main()

