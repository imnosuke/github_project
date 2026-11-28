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
UNIFIED_SNAPSHOT = Path(__file__).resolve().parents[2] / "ml/datasets/gharchive-2026-07-21/snapshot"
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
    evaluation, batch, latest = st.tabs(["Đánh giá hồi cứu", "Dự báo local", "Dự báo mới nhất"])
    with evaluation:
        render_evaluation(lock, metrics, samples, names)
    with batch:
        render_batch(manifest, lock)
    with latest:
        render_latest_snapshot_forecast(names)


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


def render_latest_snapshot_forecast(names):
    snapshot_dir = Path(os.environ.get("APP_SNAPSHOT_DIR", str(UNIFIED_SNAPSHOT)))
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        st.info("Chưa có snapshot mở rộng cho dự báo mới nhất.")
        return
    try:
        snap_manifest = json.loads(manifest_path.read_text(encoding="utf8"))
        for fname, expected_sha in (snap_manifest.get("files") or {}).items():
            actual_sha = hashlib.sha256((snapshot_dir / fname).read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise ValueError(f"Checksum mismatch for {fname}")
        status = pd.read_parquet(snapshot_dir / "daily_data_status.parquet")
        metrics_df = pd.read_parquet(snapshot_dir / "repository_daily_metrics.parquet")
        registry = pd.read_parquet(snapshot_dir / "repository_registry.parquet")
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"Không thể đọc snapshot mở rộng: {exc}")
        return

    full_days = set(status.loc[status["processed_files"].eq(24), "date"])
    if not full_days:
        st.info("Snapshot chưa có đủ dữ liệu 24/24 giờ.")
        return
    anchor = date.fromisoformat(max(full_days))
    window_dates = [(anchor - timedelta(days=offset)).isoformat() for offset in range(29, -1, -1)]
    missing_in_window = [d for d in window_dates if d not in full_days]
    if missing_in_window:
        st.warning(f"Cửa sổ 30 ngày gần nhất còn thiếu {len(missing_in_window)} ngày chưa đủ 24 giờ.")
        return

    window_df = metrics_df.loc[metrics_df["date"].isin(window_dates)]
    repo_names = registry.set_index("repository_id")["repository_name"].to_dict() or names
    preds = (
        window_df.groupby("repository_id", as_index=False)["star_events"]
        .sum()
        .assign(repository_name=lambda df: df["repository_id"].map(repo_names))
        .sort_values(["star_events", "repository_id"], ascending=[False, True])
    )
    forecast_start = anchor + timedelta(days=1)
    forecast_end = anchor + timedelta(days=30)

    st.subheader("Persistence 30 ngày từ dữ liệu mới nhất")
    st.caption(
        f"Snapshot {snap_manifest['from']} → {snap_manifest['through']} UTC · "
        f"Cửa sổ đầu vào {window_dates[0]} → {window_dates[-1]} · "
        f"Kỳ dự báo {forecast_start} → {forecast_end} UTC"
    )
    summary = st.columns(3)
    summary[0].metric("Mốc dữ liệu mới nhất", f"{anchor} UTC", border=True)
    summary[1].metric("Tổng star dự báo (20 repo)", f"{int(preds['star_events'].sum()):,}", border=True)
    summary[2].metric("Repo dẫn đầu", str(preds.iloc[0]["repository_name"]), border=True)

    st.dataframe(
        preds[["repository_name", "star_events"]].rename(
            columns={"repository_name": "Repo", "star_events": "Lượt star dự báo (30 ngày tới)"}
        ),
        hide_index=True,
        width="stretch",
    )

    # Reconcile 2026-02-05 batch forecast against actual crawled 2026-02-06..2026-03-07
    eval_dates = [(date(2026, 2, 6) + timedelta(days=i)).isoformat() for i in range(30)]
    if all(d in full_days for d in eval_dates):
        in_dates = [(date(2026, 1, 7) + timedelta(days=i)).isoformat() for i in range(30)]
        if all(d in full_days for d in in_dates):
            pred_feb = metrics_df.loc[metrics_df["date"].isin(in_dates)].groupby("repository_id")["star_events"].sum()
            actual_feb = metrics_df.loc[metrics_df["date"].isin(eval_dates)].groupby("repository_id")["star_events"].sum()
            comp = pd.DataFrame({"pred": pred_feb, "actual": actual_feb}).fillna(0)
            comp["abs_err"] = (comp["pred"] - comp["actual"]).abs()
            mae = float(comp["abs_err"].mean())
            wape = float(100.0 * comp["abs_err"].sum() / max(comp["actual"].sum(), 1))
            with st.expander("Đối chiếu thực tế kỳ 2026-02-06 → 2026-03-07 UTC (từ dữ liệu backfill)"):
                c1, c2 = st.columns(2)
                c1.metric("MAE thực tế", f"{mae:,.2f} star/repo", border=True)
                c2.metric("WAPE thực tế", f"{wape:,.2f}%", border=True)
                table = (
                    comp.reset_index()
                    .assign(Repo=lambda df: df["repository_id"].map(repo_names))
                    .sort_values("actual", ascending=False)[["Repo", "pred", "actual", "abs_err"]]
                    .rename(columns={"pred": "Dự báo", "actual": "Thực tế", "abs_err": "Sai số tuyệt đối"})
                )
                st.dataframe(table, hide_index=True, width="stretch")


main()
