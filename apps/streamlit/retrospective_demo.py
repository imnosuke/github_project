"""Standalone demo of the completed GH Archive holdout."""

from datetime import date, timedelta
import hashlib
import json
import os
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
    st.title("Dự báo lượt star")
    try:
        manifest, lock, metrics, samples, names = load_holdout()
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"Không thể đọc bộ kết quả holdout: {exc}")
        return

    st.caption(f"RepoScope · GH Archive · {manifest['repos']} repo · {manifest['hourly_files']:,} giờ dữ liệu")
    evaluation, batch = st.tabs(["Đánh giá hồi cứu", "Dự báo local"])
    with evaluation:
        render_evaluation(lock, metrics, samples, names)
    with batch:
        render_batch(manifest, lock)


def render_evaluation(lock, metrics, samples, names):
    repo_col, anchor_col = st.columns(2)
    repo = repo_col.selectbox("Repo", sorted(lock["repository_ids"], key=names.get), format_func=names.get)
    subset = samples.loc[samples.repository_id.eq(repo)].sort_values("anchor_date")
    anchor = date.fromisoformat(anchor_col.selectbox("Ngày chốt dữ liệu (UTC)", lock["anchors"],
                                                    index=len(lock["anchors"]) - 1))
    selected = subset.loc[subset.anchor_date.eq(anchor.isoformat())].iloc[0]
    st.caption(f"Kỳ dự báo 30 ngày · {anchor + timedelta(days=1)} → {anchor + timedelta(days=30)} UTC")
    output = st.columns(3)
    output[0].metric("Lượt star thực tế", f"{selected['target']:,.0f}", border=True)
    for column, (key, label) in zip(output[1:], METRICS.items()):
        error = abs(selected[key] - selected["target"])
        column.metric(label, f"{selected[key]:,.2f}", border=True)
        column.caption(f"Sai số {error:,.2f} lượt star")

    st.subheader("Sai số trung bình (MAE)")
    st.caption(f"{lock['rows']} mẫu · Mốc dự báo {lock['anchors'][0]} → {lock['anchors'][-1]} UTC")
    scores = pd.DataFrame([{"Mô hình": label, "MAE": metrics[key]["mae"]} for key, label in METRICS.items()])
    chart = px.bar(scores, x="MAE", y="Mô hình", orientation="h", text_auto=".2f",
                   labels={"MAE": "Lượt star"})
    chart.update_yaxes(title=None, autorange="reversed", automargin=True)
    chart.update_layout(height=180, margin=dict(l=8, r=12, t=8, b=12), bargap=0.4)
    st.plotly_chart(chart, width="stretch")

    trend = subset.rename(columns={"target": "Thực tế", **METRICS})
    st.subheader("Dự báo theo mốc ngày")
    chart = px.line(trend, x="anchor_date", y=["Thực tế", *METRICS.values()],
                    labels={"anchor_date": "Ngày chốt dữ liệu (UTC)", "value": "Lượt star"})
    chart.update_layout(height=280, margin=dict(l=8, r=8, t=12, b=12),
                        legend=dict(orientation="h", x=0, y=1.08, title=None))
    chart.update_xaxes(automargin=True)
    chart.update_yaxes(automargin=True)
    st.plotly_chart(chart, width="stretch")


def render_batch(manifest, lock):
    default_path = DATASET.parents[1] / "runs/ml04-local.json"
    forecast_path = Path(os.environ.get("APP_ML_BATCH_FILE", default_path))
    if not forecast_path.exists():
        st.info("Chưa có kết quả batch local.")
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
    st.subheader("Persistence 30 ngày")
    st.caption(f"Mốc dữ liệu {forecast['anchor']} · Kỳ dự báo {forecast['forecast_start']} → {forecast['forecast_end']} UTC")
    st.dataframe(rows[["repository_name", "predicted_star_events"]].rename(columns={
        "repository_name": "Repo", "predicted_star_events": "Lượt star dự báo",
    }), hide_index=True, width="stretch")


main()
