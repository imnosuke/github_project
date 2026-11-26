"""Read the opt-in local Airflow run export for APP-10."""

import json

import pandas as pd
import streamlit as st


COLUMNS = {
    "run_id": "Airflow run ID",
    "state": "Trạng thái DAG",
    "target_start": "Giờ đích đầu (UTC)",
    "target_end": "Giờ đích cuối (UTC)",
    "started_at": "Bắt đầu (UTC)",
    "ended_at": "Kết thúc (UTC)",
    "duration_seconds": "Thời lượng (giây)",
    "expected_hours": "Giờ dự kiến",
    "uploaded_hours": "Giờ đã upload",
    "missing_hours": "Giờ thiếu",
    "failed_attempts": "Lần thử lỗi",
}


def render_pipeline_runs(path):
    st.subheader("Pipeline Health")
    try:
        report = json.loads(path.read_text(encoding="utf8"))
        if report["source"] != "airflow-local" or not isinstance(report["runs"], list):
            raise ValueError("Invalid Airflow export")
        runs = pd.DataFrame.from_records(report["runs"], columns=[*COLUMNS, "missing_target_hours"])
        task_rows = [
            {"Airflow run ID": run["run_id"], "Task": task["task_id"], "Trạng thái": task["state"]}
            for run in report["runs"] for task in run["task_states"]
        ]
        exported_at = report["exported_at"]
    except (OSError, ValueError, KeyError, TypeError):
        st.error("Không đọc được bản xuất Airflow. Kiểm tra APP_PIPELINE_RUNS_FILE hoặc xuất lại từ metadata SQLite.")
        return

    st.caption(f"Airflow cục bộ · Xuất lúc {exported_at}")
    if runs.empty:
        st.info("Chưa có lần chạy GH Archive trong bản xuất.")
        return
    st.caption("Các cột giờ dựa trên kết quả upload MinIO. Ô trống biểu thị Airflow chưa ghi nhận kết quả. Mỗi lần chạy lại có run ID riêng.")
    st.dataframe(runs[list(COLUMNS)].rename(columns=COLUMNS), hide_index=True, width="stretch")
    missing = runs.loc[runs.missing_hours.fillna(0).gt(0), ["run_id", "missing_target_hours"]]
    if not missing.empty:
        with st.expander("Giờ chưa có trong kết quả upload"):
            st.dataframe(missing.rename(columns={"run_id": COLUMNS["run_id"], "missing_target_hours": "Giờ thiếu (UTC)"}),
                         hide_index=True, width="stretch")
    if task_rows:
        with st.expander("Trạng thái upload và các task gặp lỗi"):
            st.dataframe(pd.DataFrame(task_rows), hide_index=True, width="stretch")
