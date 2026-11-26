"""Repository exploration UI and complete-window summaries."""

import pandas as pd
import plotly.express as px
import streamlit as st

from apps.streamlit.data import DataAdapter

METRIC_LABELS = {
    "total_events": "Sự kiện",
    "star_events": "Lượt star",
    "fork_events": "Lượt fork",
    "push_events": "Lượt push",
    "commits_pushed": "Commit đã push",
    "prs_opened": "PR mở",
    "prs_merged": "PR đã merge",
    "prs_closed_unmerged": "PR đóng chưa merge",
    "issues_opened": "Issue mở",
    "issues_closed": "Issue đóng",
    "issue_comments": "Bình luận issue",
}
DAILY_LABELS = {
    **METRIC_LABELS,
    "unique_actors": "Tài khoản hoạt động",
    "unique_human_actors": "Tài khoản không gắn nhãn bot",
}


def catalog(adapter: DataAdapter):
    return adapter.repository_catalog()


def prepared_series(adapter: DataAdapter, rid, start, end):
    rows = adapter.time_series(rid, start, end)
    for metric in DAILY_LABELS:
        rows.loc[rows.status != "complete", metric] = pd.NA
    return rows


def summary(rows, start, end):
    expected = set(pd.date_range(start, end).strftime("%Y-%m-%d"))
    if set(rows.date) != expected or (rows.status != "complete").any():
        return None
    return {metric: None if rows[metric].isna().any() else int(rows[metric].sum()) for metric in METRIC_LABELS}


def render_explorer(adapter: DataAdapter, start, end):
    query = st.text_input("Tìm repo", placeholder="owner/repo")
    repos = catalog(adapter)
    with st.expander("Bộ lọc repo"):
        cols = st.columns(3)
        for col, field, label in zip(cols, ["primary_language", "category", "ecosystem"],
                                     ["Ngôn ngữ", "Danh mục", "Hệ sinh thái"]):
            options = sorted(repos[field].dropna().unique().tolist())
            choice = col.selectbox(label, ["Tất cả", "Chưa có metadata"] + options, key=f"filter_{field}")
            if choice == "Chưa có metadata":
                repos = repos[repos[field].isna()]
            elif choice != "Tất cả":
                repos = repos[repos[field] == choice]
        sort = st.selectbox("Sắp xếp", ["Tên A–Z", "Tên Z–A", "ID tăng dần"])
    repos = repos[repos.repository_name.str.contains(query, case=False, regex=False)]
    repos = repos.sort_values("repository_id" if sort == "ID tăng dần" else "repository_name", ascending=sort != "Tên Z–A")
    if repos.empty:
        st.info("Không tìm thấy repo phù hợp.")
        return

    labels = repos.set_index("repository_id").repository_name.to_dict()
    repo_col, compare_col = st.columns(2)
    rid = repo_col.selectbox("Repo", list(labels), format_func=labels.get, key="detail_repo")
    others = [value for value in labels if value != rid]
    other = compare_col.selectbox(
        "So sánh với", [None, *others], index=1 if others else 0,
        format_func=lambda value: labels[value] if value is not None else "Không chọn",
        disabled=not others, key="compare_repo",
    )
    if not others:
        st.info("Cần ít nhất hai repo để so sánh.")

    try:
        detail = adapter.repository_detail(rid)
    except KeyError:
        st.error("Repo không có trong bản dữ liệu.")
        return

    metric = st.selectbox("Chỉ số biểu đồ", list(DAILY_LABELS), index=1,
                          format_func=DAILY_LABELS.get, key="compare_metric")
    date_index = pd.date_range(start, end).strftime("%Y-%m-%d")
    summaries, frames = [], []
    ids = [rid, other] if other is not None else [rid]
    for col, repo_id in zip(st.columns(len(ids)), ids):
        rows = prepared_series(adapter, repo_id, start, end)
        totals = summary(rows, start, end)
        if totals is None:
            col.warning(f"{labels[repo_id]} · Không tổng hợp toàn kỳ")
        elif metric in METRIC_LABELS:
            amount = totals[metric]
            col.metric(labels[repo_id], "—" if amount is None else f"{amount:,}", border=True)
        summaries.append({"Repo": labels[repo_id], "Trạng thái": "Đủ dữ liệu" if totals is not None else "Chưa đủ dữ liệu",
                          **(totals or {field: None for field in METRIC_LABELS})})
        frame = rows.set_index("date").reindex(date_index).rename_axis("date").reset_index()
        frames.append(frame.assign(repository=labels[repo_id]))

    chart = px.line(
        pd.concat(frames), x="date", y=metric, color="repository", markers=True,
        labels={"date": "Ngày (UTC)", metric: DAILY_LABELS[metric], "repository": "Repo"},
    )
    chart.update_layout(height=330, margin=dict(l=8, r=8, t=12, b=12),
                        legend=dict(orientation="h", x=0, y=1.06, title=None))
    chart.update_xaxes(automargin=True)
    chart.update_yaxes(automargin=True)
    st.plotly_chart(chart, width="stretch")

    with st.expander("Tổng hợp theo repo"):
        st.dataframe(pd.DataFrame(summaries).rename(columns=METRIC_LABELS), hide_index=True, width="stretch")
    with st.expander("Số liệu theo ngày"):
        st.dataframe(pd.concat(frames)[["repository", "date", "status", *DAILY_LABELS]]
                     .rename(columns={"repository": "Repo", "date": "Ngày (UTC)", "status": "Trạng thái", **DAILY_LABELS}),
                     hide_index=True, width="stretch")
    with st.expander(f"Metadata · {labels[rid]}"):
        meta = detail["metadata"]
        if meta is None:
            st.info("Repo chưa có metadata snapshot.")
        else:
            st.caption(f"Ngày quan sát · {meta['observed_at']}")
            if meta.get("description"):
                st.write(meta["description"])
            meta_display = {
                "Ngôn ngữ": meta.get("primary_language"),
                "Giấy phép": meta.get("license"),
                "Chủ đề": ", ".join(meta.get("topics") or []),
                "Lưu trữ": "Có" if meta.get("archived") else "Không",
                "Repo fork": "Có" if meta.get("is_fork") else "Không",
                "Ngày tạo": meta.get("created_at"),
                "Star tại snapshot": meta.get("current_stars"),
                "Fork tại snapshot": meta.get("current_forks"),
            }
            st.dataframe(pd.DataFrame([meta_display]), hide_index=True, width="stretch")
    with st.expander(f"Danh mục repo ({len(repos)})"):
        size_col, page_col = st.columns(2)
        size = size_col.selectbox("Số dòng mỗi trang", [5, 10, 20], index=1)
        pages = max(1, (len(repos) + size - 1) // size)
        page = page_col.selectbox("Trang kết quả", list(range(1, pages + 1)))
        st.dataframe(
            repos.iloc[(page - 1) * size:page * size][
                ["repository_id", "repository_name", "primary_language", "category", "ecosystem"]
            ].rename(columns={"repository_id": "ID", "repository_name": "Repo", "primary_language": "Ngôn ngữ",
                              "category": "Danh mục", "ecosystem": "Hệ sinh thái"}),
            hide_index=True, width="stretch",
        )
    return rid
