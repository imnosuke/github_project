"""Overview and growth views using contract-defined completeness rules."""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from apps.streamlit.data import DataAdapter


OVERVIEW_METRICS = {"total_events": "Sự kiện", "star_events": "Lượt star", "fork_events": "Lượt fork"}
GROWTH_WINDOWS = (7, 30)
VALID_STATES = {"valid", "new_activity", "no_activity"}


def default_date_range(adapter: DataAdapter, lower: date, upper: date, latest: str | None):
    end = date.fromisoformat(latest) if latest else upper
    window = GROWTH_WINDOWS[-1]
    if latest and (end - lower).days + 1 >= 2 * window:
        status = adapter.day_status(lower.isoformat(), latest)
        complete = status.loc[status.status.eq("complete"), "date"]
        calendar = pd.Series(pd.date_range(lower, end).strftime("%Y-%m-%d"))
        eligible = calendar.isin(complete).rolling(2 * window).sum().eq(2 * window)
        if eligible.any():
            end = date.fromisoformat(calendar[eligible].iloc[-1])
    return max(lower, end - timedelta(days=window - 1)), end


def overview_data(adapter: DataAdapter, start, end):
    result = adapter.overview(start, end)
    return result["tracked_repositories"], result["totals"], result["trend"]


def render_overview(adapter: DataAdapter, start, end):
    tracked, totals, trend = overview_data(adapter, start, end)
    cols = st.columns(5)
    cols[0].metric("Repo theo dõi", f"{tracked:,}", border=True)
    for col, (field, label) in zip(cols[1:], {"active_repositories": "Repo có hoạt động", **OVERVIEW_METRICS}.items()):
        col.metric(label, "—" if totals is None else f"{totals[field]:,}", border=True)

    st.subheader("Hoạt động theo ngày")
    metric = st.radio("Chỉ số biểu đồ", list(OVERVIEW_METRICS), format_func=OVERVIEW_METRICS.get,
                      horizontal=True, label_visibility="collapsed", key="overview_metric")
    fig = px.line(
        trend, x="date", y=metric, markers=True,
        labels={metric: OVERVIEW_METRICS[metric], "date": "Ngày (UTC)"},
    )
    fig.update_layout(height=320, margin=dict(l=8, r=8, t=12, b=12))
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    st.plotly_chart(fig, width="stretch")
    with st.expander("Số liệu theo ngày"):
        st.dataframe(trend.rename(columns=OVERVIEW_METRICS), hide_index=True, width="stretch")


def render_growth(adapter: DataAdapter, start, end):
    window_col, rank_col = st.columns(2)
    window = window_col.selectbox("Độ dài mỗi kỳ", GROWTH_WINDOWS, index=1, format_func=lambda days: f"{days} ngày")
    anchor = pd.Timestamp(end)
    current_start = (anchor - pd.Timedelta(days=window-1)).strftime("%Y-%m-%d")
    previous_start = (anchor - pd.Timedelta(days=2*window-1)).strftime("%Y-%m-%d")
    previous_end = (anchor - pd.Timedelta(days=window)).strftime("%Y-%m-%d")
    st.caption(f"Kỳ này {current_start} → {end} · Kỳ trước {previous_start} → {previous_end} UTC")
    result = adapter.growth_ranking(end, window)
    eligible = result[result.state.isin(VALID_STATES)].copy()
    excluded = result[~result.state.isin(VALID_STATES)]
    st.caption(f"{len(eligible)}/{len(result)} repo đủ dữ liệu")
    if eligible.empty:
        st.info("Chưa có repository đủ dữ liệu ở cả hai kỳ.")
    else:
        render_growth_ranking(rank_col, eligible)
    if not excluded.empty:
        reason = {
            "insufficient_history": "Thiếu lịch sử theo dõi",
            "incomplete_data": "Dữ liệu chưa complete",
        }
        with st.expander(f"Repo chưa đủ dữ liệu ({len(excluded)})"):
            st.dataframe(
                excluded[["repository_name"]].assign(reason=excluded["state"].map(reason))
                .rename(columns={"repository_name": "Repo", "reason": "Lý do"}),
                hide_index=True, width="stretch",
            )


def render_growth_ranking(rank_col, eligible):
    sorts = {
        "Star events trong kỳ": ("Lượt star kỳ này", "current"),
        "Absolute delta": ("Chênh lệch lượt star", "absolute_delta"),
        "Growth % (baseline > 0)": ("Tăng trưởng lượt star (%)", "growth_pct"),
    }
    sort = rank_col.selectbox("Xếp hạng theo", list(sorts), format_func=lambda value: sorts[value][0])
    chart_label, chart_metric = sorts[sort]
    if sort == "Absolute delta":
        eligible = eligible.sort_values(["absolute_delta", "current", "repository_id"], ascending=[False, False, True])
    elif sort == "Growth % (baseline > 0)":
        eligible = eligible[eligible.previous > 0].sort_values(["growth_pct", "current", "repository_id"], ascending=[False, False, True])
    if eligible.empty:
        st.info("Không có repo đã nhận star ở kỳ trước.")
        return
    top = eligible.head(8)
    st.subheader(f"Top {len(top)} repo")
    fig = px.bar(top, x=chart_metric, y="repository_name", orientation="h",
                 labels={chart_metric: chart_label, "repository_name": "Repo"})
    fig.update_yaxes(title=None, autorange="reversed", automargin=True)
    fig.update_layout(height=max(200, 38 * len(top) + 60), margin=dict(l=8, r=16, t=8, b=12))
    st.plotly_chart(fig, width="stretch")

    eligible = eligible.assign(
        rank=range(1, len(eligible) + 1),
        state=eligible.state.map({"valid": "Có star kỳ trước", "new_activity": "Mới có star", "no_activity": "Không có star"}),
    )
    st.subheader("Bảng xếp hạng")
    st.dataframe(
        eligible[["rank", "repository_name", "current", "previous", "absolute_delta", "growth_pct", "state"]],
        hide_index=True,
        width="stretch",
        column_config={
            "rank": st.column_config.NumberColumn("Hạng", format="%d"),
            "repository_name": st.column_config.TextColumn("Repo"),
            "current": st.column_config.NumberColumn("Kỳ này", format="%d"),
            "previous": st.column_config.NumberColumn("Kỳ trước", format="%d"),
            "absolute_delta": st.column_config.NumberColumn("Chênh lệch", format="%+d"),
            "growth_pct": st.column_config.NumberColumn("Tăng trưởng", format="%.1f%%"),
            "state": st.column_config.TextColumn("Trạng thái"),
        }
    )
