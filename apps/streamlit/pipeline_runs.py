"""Read the opt-in local Airflow run export for APP-10."""

import json

import pandas as pd
import streamlit as st


COLUMNS = {
    "state": "Trạng thái DAG",
    "uploaded_hours": "Giờ đã upload",
    "expected_hours": "Giờ dự kiến",
    "missing_hours": "Giờ thiếu",
    "target_start": "Giờ đích đầu (UTC)",
    "target_end": "Giờ đích cuối (UTC)",
    "run_id": "Airflow run ID",
    "started_at": "Bắt đầu (UTC)",
    "ended_at": "Kết thúc (UTC)",
    "duration_seconds": "Thời lượng (giây)",
    "failed_attempts": "Lần thử lỗi",
    "dbt_state": "Trạng thái dbt",
    "publication_id": "Publication APP-02",
}


def render_pipeline_runs(path):
    st.title("Pipeline Health")
    try:
        report = json.loads(path.read_text(encoding="utf8"))
        if report["source"] not in {"airflow-local", "airflow-metadata"} or not isinstance(report["runs"], list):
            raise ValueError("Invalid Airflow export")
        runs = pd.DataFrame.from_records(report["runs"], columns=[*COLUMNS, "missing_target_hours"])
        for field in ("uploaded_hours", "expected_hours", "missing_hours"):
            runs[field] = pd.to_numeric(runs[field], errors="raise").astype("Int64")
        missing = runs.loc[runs.missing_hours.gt(0).fillna(False), ["run_id", "missing_target_hours"]]
        task_rows = [
            {"Airflow run ID": run["run_id"], "Task": task["task_id"], "Trạng thái": task["state"]}
            for run in report["runs"] for task in run["task_states"]
        ]
        failures = [{"Airflow run ID": run["run_id"], "Task": task["task_id"],
                     "Bắt đầu (UTC)": task["started_at"], "Kết thúc (UTC)": task["ended_at"]}
                    for run in report["runs"] for task in run.get("failure_details", [])]
        exported_at = report["exported_at"]
    except (OSError, ValueError, KeyError, TypeError):
        st.error("Không đọc được bản xuất Airflow.")
        return

    source = "Airflow cục bộ" if report["source"] == "airflow-local" else "Metadata Airflow"
    st.caption(f"{source} · {exported_at}")
    if runs.empty:
        st.info("Chưa có lần chạy GH Archive trong bản xuất.")
        return
    latest = runs.iloc[0]
    state_labels = {"success": "Thành công", "failed": "Thất bại", "running": "Đang chạy", "queued": "Đang chờ"}
    status_col, uploaded_col, missing_col = st.columns(3)
    state = str(latest.state) if pd.notna(latest.state) else "—"
    status_col.metric("Lần chạy gần nhất", state_labels.get(state, state), border=True)
    uploaded = "—" if pd.isna(latest.uploaded_hours) else str(int(latest.uploaded_hours))
    expected = "—" if pd.isna(latest.expected_hours) else str(int(latest.expected_hours))
    uploaded_col.metric("Giờ đã tải / dự kiến", f"{uploaded} / {expected}", border=True)
    missing_col.metric("Giờ thiếu", "—" if pd.isna(latest.missing_hours) else str(int(latest.missing_hours)), border=True)
    st.subheader("Lịch sử chạy")
    st.dataframe(runs[list(COLUMNS)].rename(columns=COLUMNS), hide_index=True, width="stretch")
    if not missing.empty:
        with st.expander("Giờ chưa có trong kết quả upload"):
            st.dataframe(missing.rename(columns={"run_id": COLUMNS["run_id"], "missing_target_hours": "Giờ thiếu (UTC)"}),
                         hide_index=True, width="stretch")
    if task_rows:
        with st.expander("Trạng thái upload và các task gặp lỗi"):
            st.dataframe(pd.DataFrame(task_rows), hide_index=True, width="stretch")
    if failures:
        with st.expander("Lịch sử task thất bại"):
            st.dataframe(pd.DataFrame(failures), hide_index=True, width="stretch")
