"""Opt-in APP-10 fixture view for pipeline operations."""

import pandas as pd
import streamlit as st


RUNS = (
    ("staging-2025-01-13", "2025-01-13", 1, 24, 24, "complete"),
    ("staging-2025-01-14", "2025-01-14", 1, 24, 23, "failed"),
    ("staging-2025-01-14", "2025-01-14", 2, 24, 24, "complete"),
    ("staging-2025-01-15", "2025-01-15", 1, 24, 22, "provisional"),
)
EXPECTED_THROUGH = "2025-01-15"


def render_pipeline_fixture():
    st.warning("Pipeline Health · Dữ liệu vận hành giả lập")
    runs = pd.DataFrame(RUNS, columns=["run_id", "day_utc", "attempt", "expected_hours",
                                      "processed_hours", "status"])
    runs["missing_hours"] = runs.expected_hours - runs.processed_hours
    latest = runs.sort_values("attempt").drop_duplicates("run_id", keep="last")
    latest_complete = latest.loc[latest.status.eq("complete"), "day_utc"].max()
    st.caption(f"Ngày complete gần nhất: {latest_complete} UTC · Kỳ vọng: {EXPECTED_THROUGH} UTC")
    if latest_complete < EXPECTED_THROUGH:
        st.warning("Publication trễ so với kỳ vọng của fixture.")
    st.dataframe(latest.sort_values("day_utc", ascending=False), hide_index=True, width="stretch")
    with st.expander("Lịch sử lần chạy và retry"):
        st.dataframe(runs.sort_values(["day_utc", "attempt"], ascending=False), hide_index=True, width="stretch")
