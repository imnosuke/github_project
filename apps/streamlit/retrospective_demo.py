"""Standalone demo of the completed GH Archive holdout."""

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


DATASET = Path(__file__).resolve().parents[2] / "ml/datasets/gharchive-2026-02-05"
METRICS = {"persistence": "Persistence 30 ngày", "ridge": "Ridge"}


def verified_path(relative, checksum):
    path = DATASET / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise ValueError(f"Checksum mismatch for {relative}")
    return path


def load_holdout():
    manifest = json.loads((DATASET / "export-manifest.json").read_text(encoding="utf8"))
    files = manifest["evaluation_sha256"]
    metrics = json.loads(verified_path("evaluation/metrics.json", files["metrics.json"]).read_text(encoding="utf8"))
    lock = json.loads(verified_path("evaluation/holdout-lock.json", files["holdout-lock.json"]).read_text(encoding="utf8"))
    samples = pd.read_parquet(verified_path("evaluation/predictions.parquet", files["predictions.parquet"]))
    registry = pd.read_parquet(verified_path("snapshot/repository_registry.parquet",
                                            manifest["snapshot_files"]["repository_registry.parquet"]))
    if metrics["mode"] != "retrospective_event_time" or metrics["status"] != "completed":
        raise ValueError("Unexpected evaluation artifact")
    if (len(samples) != lock["rows"] or samples.duplicated(["repository_id", "anchor_date"]).any()
            or sorted(samples.anchor_date.unique()) != lock["anchors"]
            or sorted(samples.repository_id.unique()) != lock["repository_ids"]):
        raise ValueError("Holdout sample scope differs from the lock")
    return manifest, lock, metrics["score"], samples, registry.set_index("repository_id").repository_name.to_dict()


def main():
    st.set_page_config(page_title="RepoScope · Demo ML", layout="wide")
    st.title("Dự đoán star events của repository")
    st.info("Đánh giá hồi cứu và dự đoán local trên dữ liệu GH Archive đã fetch. Mỗi kết quả hiển thị theo mốc ngày của bộ dữ liệu.")
    try:
        manifest, lock, metrics, samples, names = load_holdout()
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"Không thể đọc bộ kết quả holdout: {exc}")
        return

    indicators = st.columns(3)
    indicators[0].metric("Repo", manifest["repos"])
    indicators[1].metric("Giờ GH Archive", manifest["hourly_files"])
    indicators[2].metric("Mẫu holdout", lock["rows"])
    scores = pd.DataFrame([{"Model": label, "MAE": metrics[key]["mae"], "RMSE": metrics[key]["rmse"]}
                           for key, label in METRICS.items()])
    st.subheader("Sai số trên holdout")
    st.plotly_chart(px.bar(scores, x="MAE", y="Model", orientation="h", text_auto=".2f"), width="stretch")
    st.caption("MAE càng thấp càng tốt. Persistence lấy tổng star events của 30 ngày trước làm dự đoán cho 30 ngày sau.")

    repo = st.selectbox("Repository", sorted(lock["repository_ids"], key=names.get), format_func=names.get)
    subset = samples.loc[samples.repository_id.eq(repo)].sort_values("anchor_date")
    anchor = date.fromisoformat(st.selectbox("Ngày chốt feature (UTC)", lock["anchors"], index=len(lock["anchors"]) - 1))
    selected = subset.loc[subset.anchor_date.eq(anchor.isoformat())].iloc[0]
    st.caption(f"Cửa sổ cần dự đoán (UTC) {anchor + timedelta(days=1)} → {anchor + timedelta(days=30)}")
    output = st.columns(3)
    output[0].metric("Star events thực tế", f"{selected['target']:,.0f}")
    for column, (key, label) in zip(output[1:], METRICS.items()):
        column.metric(label, f"{selected[key]:,.2f}")
    trend = subset.rename(columns={"target": "Thực tế", **METRICS})
    st.plotly_chart(px.line(trend, x="anchor_date", y=["Thực tế", *METRICS.values()],
                           labels={"anchor_date": "Ngày chốt feature (UTC)", "value": "Star events", "variable": "Chuỗi"}),
                    width="stretch")

    forecast_path = DATASET.parents[1] / "runs/ml04-local.json"
    st.subheader("Dự đoán chạy từ snapshot đã crawl")
    if not forecast_path.exists():
        st.info("Chạy batch ML-04 local để tạo kết quả cho phần này.")
        return
    try:
        forecast = json.loads(forecast_path.read_text(encoding="utf8"))
        if (forecast["mode"] != "local_archive" or forecast["anchor"] != manifest["end"]
                or forecast["input_publication"] != manifest["source_publication"]):
            raise ValueError("Forecast refers to a different archive")
        rows = pd.DataFrame(forecast["rows"])
        if sorted(rows.repository_id) != lock["repository_ids"]:
            raise ValueError("Forecast scope differs from the dataset")
    except (OSError, ValueError, KeyError):
        st.error("Batch dự đoán không khớp với snapshot đã crawl.")
        return
    st.caption(f"Persistence 30 ngày · Dữ liệu tới {forecast['anchor']} UTC · Cửa sổ {forecast['forecast_start']} → {forecast['forecast_end']} UTC")
    st.dataframe(rows[["repository_name", "predicted_star_events"]].rename(columns={
        "repository_name": "Repository", "predicted_star_events": "Star events dự đoán",
    }), hide_index=True, width="stretch")


main()
