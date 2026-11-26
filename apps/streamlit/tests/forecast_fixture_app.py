"""Standalone Streamlit harness for synthetic Forecast evaluation."""

import hashlib
import json
import os
from pathlib import Path

import streamlit as st


def render_ml_forecast():
    st.warning("DEMO — Điểm đánh giá từ fixture tổng hợp. Chưa có publication dự đoán.")
    default_run = Path(__file__).resolve().parents[3] / "ml/runs/github_pc_model"
    directory = Path(os.getenv("APP_ML_MODEL_DIR", str(default_run)))
    try:
        report = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        model_path = directory / "model.json"
        if (report["status"] != "completed" or report["publication"]["data_source"] != "fixture"
                or hashlib.sha256(model_path.read_bytes()).hexdigest() != report["model_sha256"]):
            st.info("Cần một artifact fixture đã hoàn tất có checksum hợp lệ.")
            return
        selected = report["selected"]
        test = report["test"]
        st.metric("Model được chọn trên validation", selected)
        st.metric("MAE holdout trên fixture", f"{test[selected]['mae']:.2f}")
    except (OSError, ValueError, KeyError, TypeError):
        st.info("Chưa có báo cáo fixture hợp lệ tại APP_ML_MODEL_DIR.")


render_ml_forecast()
