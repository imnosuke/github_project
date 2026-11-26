"""An opt-in view of an approved 30-day prediction publication."""

from datetime import date, datetime, timedelta, timezone
import math
import os

import pandas as pd
import streamlit as st

from apps.streamlit.data.config import ClickHouseConfig
from apps.streamlit.data.prediction_publication import prediction_timestamp, read_prediction_publication


LABELS = {"insufficient_history": "Chưa đủ lịch sử", "incomplete_features": "Dữ liệu feature chưa đủ"}


def render_predictions(adapter, anchor, repository_id=None):
    release = os.getenv("APP_PREDICTION_RELEASE_ID", "").strip()
    st.subheader("Dự đoán star events trong 30 ngày")
    try:
        max_age = float(os.environ["APP_PREDICTION_MAX_AGE_HOURS"])
        if not release or not math.isfinite(max_age) or max_age <= 0:
            raise ValueError("Prediction release and freshness are required")
    except (KeyError, ValueError):
        st.info("Chưa cấu hình bản phát hành dự đoán hoặc SLA.")
        return
    try:
        batch = read_prediction_publication(ClickHouseConfig.from_env(), anchor, release)
        if batch:
            generated = prediction_timestamp(batch["generated_at"])
            if generated > datetime.now(timezone.utc):
                raise ValueError("Unexpected prediction timestamp")
    except (OSError, KeyError, TypeError, ValueError):
        st.warning("Nguồn dự đoán tạm thời không đọc được.")
        return
    if batch is None:
        st.info("Chưa có dự đoán cho ngày được chọn.")
        return
    last = date.fromisoformat(anchor)
    st.caption(f"Khoảng dự đoán UTC {last + timedelta(days=1)} → {last + timedelta(days=30)} · Cập nhật {generated.isoformat()}")
    if (datetime.now(timezone.utc) - generated).total_seconds() / 3600 > max_age:
        st.warning("Bản dự đoán đã quá hạn theo SLA.")
        return
    rows = [row for row in batch["rows"] if repository_id is None or row["repository_id"] == repository_id]
    if not rows:
        st.info("Repo này chưa có trong publication dự đoán.")
        return
    if repository_id is not None:
        row = rows[0]
        if row["status"] == "ready":
            st.metric("Star events dự đoán", f"{row['predicted_star_events']:,.2f}")
        else:
            st.info(LABELS[row["status"]])
        return
    catalog = adapter.repository_catalog().set_index("repository_id").repository_name.to_dict()
    st.dataframe(pd.DataFrame([
        {"Repository": catalog.get(row["repository_id"], row["repository_id"]),
         "Star events dự đoán": row["predicted_star_events"],
         "Trạng thái": LABELS.get(row["status"], "Có dự đoán")} for row in rows
    ]), hide_index=True, width="stretch")
