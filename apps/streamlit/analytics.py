"""Overview and growth views using contract-defined completeness rules."""
import pandas as pd
import plotly.express as px
import streamlit as st


def overview_data(adapter, start, end):
    registry = adapter.tables["repository_registry"]
    scoped = registry[(registry.tracking_start_date <= end)
                      & (registry.tracking_end_date.fillna("9999-12-31") >= start)]
    rows = adapter.tables["repository_daily_metrics"]
    rows = rows[rows.date.between(start, end)]
    statuses = adapter.tables["daily_data_status"]
    statuses = statuses[statuses.date.between(start, end)]
    expected = set(pd.date_range(start, end).strftime("%Y-%m-%d"))
    valid = set(statuses.date) == expected and (statuses.status == "complete").all()
    totals = None
    fields = ["total_events", "star_events", "fork_events"]
    if valid and not rows[fields].isna().any().any():
        totals = {field: int(rows[field].sum()) for field in fields}
        totals["active_repositories"] = int(rows.loc[rows.total_events > 0, "repository_id"].nunique())
    trend = rows.groupby("date")[fields].sum(min_count=1).reindex(sorted(expected))
    complete_dates = set(statuses.loc[statuses.status == "complete", "date"])
    trend.loc[~trend.index.isin(complete_dates), fields] = float("nan")
    # Complete days with no tracked activity are known zeros, not missing days.
    trend.loc[trend.index.isin(complete_dates), fields] = trend.loc[trend.index.isin(complete_dates), fields].fillna(0)
    return int(scoped.repository_id.nunique()), totals, trend.rename_axis("date").reset_index()


def render_overview(adapter, start, end):
    tracked, totals, trend = overview_data(adapter, start, end)
    st.metric("Repositories được theo dõi trong kỳ", tracked)
    if totals is None:
        st.warning("KPI toàn kỳ chưa khả dụng vì thiếu dữ liệu complete. Các ngày hợp lệ vẫn xuất hiện trên biểu đồ.")
    else:
        for col, (field, label) in zip(st.columns(4), [("active_repositories", "Repos có activity"),
                ("total_events", "Total events"), ("star_events", "Star events"), ("fork_events", "Fork events")]):
            col.metric(label, f"{totals[field]:,}")
    st.plotly_chart(px.line(trend, x="date", y=["total_events", "star_events", "fork_events"],
                           title="Hoạt động theo ngày UTC"), width="stretch")
    st.caption("Tracked repos tính theo registry giao với kỳ; repos có activity tính từ event. Counts gồm bot. Không cộng daily unique actors thành unique contributors toàn kỳ.")
    with st.expander("Dữ liệu trend"):
        st.dataframe(trend, hide_index=True, width="stretch")


def render_growth(adapter, start, end):
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
        with st.expander("Repositories bị loại", expanded=eligible.empty):
            st.dataframe(excluded[["repository_name", "state"]], hide_index=True, width="stretch")
    if eligible.empty:
        st.info("Chưa có repository đủ hai cửa sổ complete để xếp hạng. Chọn ngày kết thúc khác hoặc chờ backfill.")
        return
    sort = st.selectbox("Xếp hạng theo", ["Star events trong kỳ", "Absolute delta", "Growth % (baseline > 0)"])
    if sort == "Absolute delta":
        eligible = eligible.sort_values(["absolute_delta", "current", "repository_id"], ascending=[False, False, True])
    elif sort == "Growth % (baseline > 0)":
        eligible = eligible[eligible.previous > 0].sort_values(["growth_pct", "current", "repository_id"], ascending=[False, False, True])
    if eligible.empty:
        st.info("Không có repository với baseline dương cho kiểu xếp hạng này.")
        return
    eligible.insert(0, "rank", range(1, len(eligible)+1))
    st.dataframe(eligible, hide_index=True, width="stretch")
    st.plotly_chart(px.bar(eligible.head(20), x="repository_name", y="current", title="Top repo theo thứ tự đã chọn · Star events trong kỳ"), width="stretch")
    st.caption("growth_pct = 100 × (current − previous) / previous. Baseline 0 và current > 0: new_activity, % không xác định; cả hai 0: no_activity, 0%. Đây là event analytics, không phải net stars hoặc dự đoán ML.")
    st.caption("Tie-break: mặc định current ↓, absolute_delta ↓, ID ↑; absolute delta: delta ↓, current ↓, ID ↑; growth %: % ↓, current ↓, ID ↑.")
