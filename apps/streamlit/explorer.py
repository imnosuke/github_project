"""Repository exploration UI and complete-window summaries."""
import pandas as pd
import plotly.express as px
import streamlit as st

METRICS = ["total_events", "star_events", "fork_events", "push_events", "commits_pushed",
           "prs_opened", "prs_merged", "prs_closed_unmerged", "issues_opened", "issues_closed", "issue_comments"]


def catalog(adapter):
    # Fixture implementation; APP-07 will move catalog filtering to the live query.
    registry = adapter.tables["repository_registry"].sort_values("tracking_start_date").drop_duplicates("repository_id", keep="last").copy()
    metadata = adapter.tables["repository_metadata"].sort_values("observed_at").drop_duplicates("repository_id", keep="last")
    return registry.merge(metadata[["repository_id", "primary_language"]], on="repository_id", how="left", validate="one_to_one")


def prepared_series(adapter, rid, start, end):
    rows = adapter.time_series(rid, start, end)
    for metric in METRICS + ["unique_actors", "unique_human_actors"]:
        rows.loc[rows.status != "complete", metric] = pd.NA
    return rows


def summary(rows, start, end):
    expected = set(pd.date_range(start, end).strftime("%Y-%m-%d"))
    if set(rows.date) != expected or (rows.status != "complete").any():
        return None
    return {metric: None if rows[metric].isna().any() else int(rows[metric].sum()) for metric in METRICS}


def render_explorer(adapter, start, end):
    query = st.text_input("Tìm repository", placeholder="Ví dụ: rising")
    repos = catalog(adapter)
    cols = st.columns(3)
    for col, field, label in zip(cols, ["primary_language", "category", "ecosystem"], ["Language", "Category", "Ecosystem"]):
        options = sorted(repos[field].dropna().unique().tolist())
        choice = col.selectbox(label, ["Tất cả", "Chưa có metadata"] + options, key=f"filter_{field}")
        if choice == "Chưa có metadata":
            repos = repos[repos[field].isna()]
        elif choice != "Tất cả":
            repos = repos[repos[field] == choice]
    repos = repos[repos.repository_name.str.contains(query, case=False, regex=False)]
    sort = st.selectbox("Sắp xếp", ["Tên A–Z", "Tên Z–A", "ID tăng dần"])
    repos = repos.sort_values("repository_id" if sort == "ID tăng dần" else "repository_name", ascending=sort != "Tên Z–A")
    if repos.empty:
        st.info("Không tìm thấy repository phù hợp. Thử từ khóa hoặc bộ lọc khác.")
        return
    size = st.selectbox("Số dòng mỗi trang", [5, 10, 20], index=1)
    pages = max(1, (len(repos) + size - 1) // size)
    page = st.selectbox("Trang kết quả", list(range(1, pages + 1)))
    st.caption(f"{len(repos)} repositories · Trang {page}/{pages}. Metadata và filters phản ánh snapshot mới nhất, không phải phân loại lịch sử.")
    st.dataframe(repos.iloc[(page-1)*size:page*size][["repository_id", "repository_name", "primary_language", "category", "ecosystem"]], hide_index=True, width="stretch")
    labels = repos.set_index("repository_id").repository_name.to_dict()
    rid = st.selectbox("Xem chi tiết repository", list(labels), format_func=labels.get, key="detail_repo")
    try:
        detail = adapter.repository_detail(rid)
    except KeyError:
        st.error("Repository không tồn tại trong publication này. Hãy tải lại dữ liệu.")
        return
    st.markdown(f"### {detail['registry']['repository_name']}")
    meta = detail["metadata"]
    if meta is None:
        st.info("Repository chưa có metadata snapshot; chỉ hiển thị registry và event metrics.")
    else:
        st.caption(f"Metadata quan sát tại {meta['observed_at']} · Đây là snapshot, không phải dữ liệu hiện tại theo thời gian thực.")
        st.write(meta.get("description") or "Chưa có mô tả")
        st.dataframe(pd.DataFrame([{key: meta.get(key) for key in ["primary_language", "license", "archived", "current_stars", "current_forks"]}]), hide_index=True)
    rows = prepared_series(adapter, rid, start, end)
    totals = summary(rows, start, end)
    if totals is None:
        st.warning("Không tổng hợp toàn kỳ: thiếu lịch sử theo dõi hoặc ngày chưa complete.")
    else:
        st.dataframe(pd.DataFrame([totals]), hide_index=True, width="stretch")
    if rows.empty:
        st.info("Repository chưa có lịch sử trong khoảng ngày đã chọn.")
    else:
        metric = st.selectbox("Metric biểu đồ", METRICS + ["unique_actors", "unique_human_actors"])
        chart_rows = rows.set_index("date").reindex(pd.date_range(start, end).strftime("%Y-%m-%d")).rename_axis("date").reset_index()
        st.plotly_chart(px.line(chart_rows, x="date", y=metric, title=f"{metric} theo ngày UTC"), width="stretch")
        st.caption("Ngày chưa complete hoặc ngoài scope có khoảng trống; unique actors chỉ ở grain ngày, không cộng qua ngày.")
        with st.expander("Dữ liệu theo ngày"):
            st.dataframe(rows, hide_index=True, width="stretch")
    st.markdown("### So sánh cùng kỳ")
    others = [value for value in labels if value != rid]
    if not others:
        st.info("Cần ít nhất hai repositories trong bộ lọc để so sánh.")
        return
    other = st.selectbox("So sánh với", others, format_func=labels.get, key="compare_repo")
    other_rows = prepared_series(adapter, other, start, end)
    other_totals = summary(other_rows, start, end)
    comparisons = []
    for repo_id, values in [(rid, totals), (other, other_totals)]:
        comparisons.append({"repository": labels[repo_id], "status": "complete" if values is not None else "incomplete / insufficient history", **(values or {m: None for m in METRICS})})
    st.dataframe(pd.DataFrame(comparisons), hide_index=True, width="stretch")
    frames = []
    for repo_id, data in [(rid, rows), (other, other_rows)]:
        frame = data.set_index("date").reindex(pd.date_range(start, end).strftime("%Y-%m-%d")).rename_axis("date").reset_index()
        frame["repository"] = labels[repo_id]
        frames.append(frame)
    st.plotly_chart(px.line(pd.concat(frames), x="date", y="star_events", color="repository", title="Star events · cùng khoảng ngày UTC"), width="stretch")
    st.caption("Star events không phải net stars. Bot events nằm trong event counts; contributor metrics chưa được cung cấp.")
