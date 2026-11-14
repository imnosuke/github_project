"""Overview and growth views using contract-defined completeness rules."""
import pandas as pd
import plotly.express as px
import streamlit as st

from apps.streamlit.data import DataAdapter


def overview_data(adapter: DataAdapter, start, end):
    result = adapter.overview(start, end)
    return result["tracked_repositories"], result["totals"], result["trend"]


def render_overview(adapter: DataAdapter, start, end):
    tracked, totals, trend = overview_data(adapter, start, end)
    cols = st.columns(5)
    cols[0].metric("Repositories theo dõi", f"{tracked:,}")
    if totals is None:
        for col, label in zip(cols[1:], ["Repos có activity", "Total events", "Star events", "Fork events"]):
            col.metric(label, "—")
        st.warning("KPI toàn kỳ chưa khả dụng vì thiếu dữ liệu complete. Các ngày hợp lệ vẫn xuất hiện trên biểu đồ.")
    else:
        for col, (field, label) in zip(cols[1:], [("active_repositories", "Repos có activity"),
                ("total_events", "Total events"), ("star_events", "Star events"), ("fork_events", "Fork events")]):
            col.metric(label, f"{totals[field]:,}")
    fig = px.line(
        trend,
        x="date",
        y=["total_events", "star_events", "fork_events"],
        markers=True,
        labels={"value": "Số lượng sự kiện", "date": "Ngày (UTC)", "variable": "Loại sự kiện"},
        title="Hoạt động theo ngày UTC"
    )
    fig.for_each_trace(lambda t: t.update(name={
        "total_events": "Total events",
        "star_events": "Star events",
        "fork_events": "Fork events"
    }.get(t.name, t.name)))
    st.plotly_chart(fig, width="stretch")
    st.caption("Tracked repos tính theo registry giao với kỳ; repos có activity tính từ event. Counts gồm bot. Không cộng daily unique actors thành unique contributors toàn kỳ.")
    with st.expander("Dữ liệu trend"):
        st.dataframe(trend, hide_index=True, width="stretch")


def render_growth(adapter: DataAdapter, start, end):
    st.caption("Ngày kết thúc của bộ lọc chung là anchor T. Khoảng ngày bắt đầu không giới hạn lookback: hệ thống đọc thêm kỳ trước để so sánh đúng.")
    window = st.selectbox("Cửa sổ growth (ngày)", [7, 30], index=1)
    anchor = pd.Timestamp(end)
    current_start = (anchor - pd.Timedelta(days=window-1)).strftime("%Y-%m-%d")
    previous_start = (anchor - pd.Timedelta(days=2*window-1)).strftime("%Y-%m-%d")
    previous_end = (anchor - pd.Timedelta(days=window)).strftime("%Y-%m-%d")
    st.write(f"Kỳ hiện tại: {current_start} → {end} · Kỳ trước: {previous_start} → {previous_end} (UTC, inclusive).")
    result = adapter.growth_ranking(end, window)
    valid_states = {"valid", "new_activity", "no_activity"}
    eligible = result[result.state.isin(valid_states)].copy()
    excluded = result[~result.state.isin(valid_states)]
    st.caption(f"{len(eligible)} repo hợp lệ · {len(excluded)} repo bị loại do thiếu lịch sử hoặc dữ liệu chưa complete.")
    if not excluded.empty:
        excluded_display = excluded[["repository_id", "repository_name", "state"]].copy()
        state_map = {
            "insufficient_history": "Thiếu lịch sử theo dõi (chưa đủ 2× cửa sổ)",
            "incomplete_data": "Dữ liệu chưa complete trong cửa sổ (có ngày missing/provisional)",
        }
        excluded_display["reason"] = excluded_display["state"].map(state_map).fillna(excluded_display["state"])
        with st.expander(f"Repositories bị loại ({len(excluded)})", expanded=eligible.empty):
            st.dataframe(
                excluded_display,
                hide_index=True,
                width="stretch",
                column_config={
                    "repository_id": st.column_config.NumberColumn("ID"),
                    "repository_name": st.column_config.TextColumn("Repository"),
                    "state": st.column_config.TextColumn("Mã trạng thái"),
                    "reason": st.column_config.TextColumn("Lý do loại"),
                }
            )
    if eligible.empty:
        st.info("Chưa có repository đủ hai cửa sổ complete để xếp hạng. Chọn ngày kết thúc khác hoặc chờ backfill.")
        return
    sort = st.selectbox("Xếp hạng theo", ["Star events trong kỳ", "Absolute delta", "Growth % (baseline > 0)"])
    chart_y = "current"
    chart_title = "Top repo · Star events trong kỳ"
    if sort == "Absolute delta":
        eligible = eligible.sort_values(["absolute_delta", "current", "repository_id"], ascending=[False, False, True])
        chart_y = "absolute_delta"
        chart_title = "Top repo · Absolute delta (current − previous)"
    elif sort == "Growth % (baseline > 0)":
        eligible = eligible[eligible.previous > 0].sort_values(["growth_pct", "current", "repository_id"], ascending=[False, False, True])
        chart_y = "growth_pct"
        chart_title = "Top repo · Growth % (baseline > 0)"
    if eligible.empty:
        st.info("Không có repository với baseline dương cho kiểu xếp hạng này.")
        return
    eligible.insert(0, "rank", range(1, len(eligible)+1))
    st.dataframe(
        eligible,
        hide_index=True,
        width="stretch",
        column_config={
            "rank": st.column_config.NumberColumn("Hạng", format="%d"),
            "repository_id": st.column_config.NumberColumn("ID"),
            "repository_name": st.column_config.TextColumn("Repository"),
            "current": st.column_config.NumberColumn("Kỳ hiện tại", format="%d"),
            "previous": st.column_config.NumberColumn("Kỳ trước", format="%d"),
            "absolute_delta": st.column_config.NumberColumn("Delta", format="%+d"),
            "growth_pct": st.column_config.NumberColumn("Growth %", format="%.1f%%"),
            "state": st.column_config.TextColumn("Trạng thái"),
        }
    )
    y_label = "Star events trong kỳ" if chart_y == "current" else "Absolute delta" if chart_y == "absolute_delta" else "Growth %"
    st.plotly_chart(
        px.bar(
            eligible.head(20),
            x="repository_name",
            y=chart_y,
            labels={"repository_name": "Repository", chart_y: y_label},
            title=chart_title
        ),
        width="stretch"
    )
    st.caption("growth_pct = 100 × (current − previous) / previous. Baseline 0 và current > 0: new_activity, % không xác định; cả hai 0: no_activity, 0%. Đây là event analytics, không phải net stars hoặc dự đoán ML.")
    st.caption("Tie-break: mặc định current ↓, absolute_delta ↓, ID ↑; absolute delta: delta ↓, current ↓, ID ↑; growth %: % ↓, current ↓, ID ↑.")
