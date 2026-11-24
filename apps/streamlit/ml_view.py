"""ML-04: Interactive ML Forecasting & Evaluation view integrated into Streamlit."""
from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from apps.streamlit.data import DataAdapter
from ml.data import Inputs
from ml.features import FEATURES, Ineligible, feature_row
from ml.training import predict


def _default_model_dir() -> Path:
    env_dir = os.getenv("APP_ML_MODEL_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[2] / "ml" / "runs" / "github_pc_model"


def _fast_inference_inputs(adapter: DataAdapter, anchor_dt: date) -> tuple[Inputs, pd.DataFrame]:
    """Chỉ trích xuất cửa sổ 30 ngày lookback `[T-29, T]` quanh ngày neo T để inference tức thì trên UI."""
    from datetime import timedelta
    start_str = (anchor_dt - timedelta(days=30)).isoformat()
    end_str = anchor_dt.isoformat()
    bounds = adapter.date_bounds()
    if bounds:
        start_str = max(bounds[0], start_str)
        end_str = min(bounds[1], end_str)

    before = adapter.publication()
    registry = adapter.registry_history()
    catalog = adapter.repository_catalog().set_index("repository_id")
    from apps.streamlit.data.adapter import COUNTS
    columns = ["repository_id", "date", *COUNTS]
    frames = [adapter.time_series(int(rid), start_str, end_str).loc[:, columns] for rid in sorted(registry.repository_id.unique())]
    daily = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    statuses = adapter.day_status(start_str, end_str)
    return Inputs(registry, daily, statuses, before), catalog


def render_ml_forecast(adapter: DataAdapter, start: str, end: str):
    st.caption(
        "Dự báo số lượng **Star events trong 30 ngày tiếp theo (`[T+1, T+30]`)** từ cửa sổ 30 ngày quá khứ (`[T-29, T]`) "
        "bằng mô hình học máy đã huấn luyện (`ml-stars-30d-v1`)."
    )
    model_dir = _default_model_dir()
    run_file = model_dir / "run.json"
    model_file = model_dir / "model.json"
    pred_file = model_dir / "test_predictions.parquet"

    if not run_file.exists() or not model_file.exists():
        st.warning(
            f"Chưa tìm thấy model artifact tại `{model_dir}`. "
            "Hãy chạy lệnh `python -m ml.cli train` để tạo model trước khi xem dự đoán."
        )
        st.code(
            "python -m ml.fetch_github_data --output ml/runs/github_pc_fixture --repos 150 --days 320 --local-parquet-dir ./airflow/data/parquet\n"
            "python -m ml.cli build --config ml/configs/smoke.json --fixture-dir ml/runs/github_pc_fixture --output ml/runs/github_pc_dataset\n"
            "python -m ml.cli train --config ml/configs/smoke.json --dataset ml/runs/github_pc_dataset --output ml/runs/github_pc_model",
            language="bash",
        )
        return

    run_report = json.loads(run_file.read_text(encoding="utf-8"))
    model_artifact = json.loads(model_file.read_text(encoding="utf-8"))
    model = model_artifact["model"]
    selected_name = run_report.get("selected", model.get("kind", "ridge"))

    # 1. KPI Summary của Mô hình
    st.markdown("### 1. Kết quả Huấn luyện & Đánh giá Mô hình (Model Card)")
    split_rows = run_report.get("split_rows", {})
    test_metrics = run_report.get("test", {}).get(selected_name, {})
    base_metrics = run_report.get("test", {}).get("persistence", {})

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Mô hình được chọn", selected_name.upper())
    k2.metric(
        "Tổng mẫu (Train / Val / Test)",
        f"{split_rows.get('train', 0):,} / {split_rows.get('validation', 0):,} / {split_rows.get('test', 0):,}",
    )
    k3.metric("Test MAE (Model)", f"{test_metrics.get('mae', 0):.2f} stars")
    k4.metric("Test MAE (Persistence-30d)", f"{base_metrics.get('mae', 0):.2f} stars")
    rel_imp = test_metrics.get("relative_mae_improvement")
    k5.metric(
        "Cải thiện so với Baseline",
        f"{rel_imp * 100:+.1f}%" if rel_imp is not None else "—",
    )

    # Bảng so sánh 3 mô hình trên Validation và Test
    comp_rows = []
    for m_name in ("persistence", "zero", "ridge"):
        v_m = run_report.get("validation", {}).get(m_name, {})
        t_m = run_report.get("test", {}).get(m_name, {})
        if v_m or t_m:
            comp_rows.append({
                "Model": m_name.upper() + (" (Selected)" if m_name == selected_name else ""),
                "Validation MAE": round(v_m.get("mae", 0.0), 3),
                "Validation RMSE": round(v_m.get("rmse", 0.0), 3),
                "Test MAE": round(t_m.get("mae", 0.0), 3),
                "Test RMSE": round(t_m.get("rmse", 0.0), 3),
                "Test Macro-MAE (by Repo)": round(t_m.get("macro_mae", 0.0), 3),
            })
    if comp_rows:
        st.dataframe(pd.DataFrame(comp_rows), hide_index=True, width="stretch")

    # 2. Trọng số 28 đặc trưng của mô hình Ridge
    if model.get("kind") == "ridge" and "coefficients" in model:
        with st.expander("Trọng số 28 Đặc trưng (Ridge Feature Importance / Coefficients)", expanded=False):
            coef_df = pd.DataFrame({
                "Feature": model_artifact.get("feature_schema", list(FEATURES)),
                "Coefficient (Standardized)": model["coefficients"],
                "Abs_Impact": [abs(c) for c in model["coefficients"]],
            }).sort_values("Abs_Impact", ascending=False)
            fig_coef = px.bar(
                coef_df.head(15),
                x="Coefficient (Standardized)",
                y="Feature",
                orientation="h",
                title="Top 15 Đặc trưng ảnh hưởng mạnh nhất tới dự báo Star 30 ngày tới",
            )
            st.plotly_chart(fig_coef, width="stretch")
            st.dataframe(coef_df, hide_index=True, width="stretch")

    # 3. Live Batch Inference tại ngày Anchor T đang chọn trên Sidebar
    st.markdown(f"### 2. Dự báo Top Repositories bùng nổ Star trong 30 ngày tới (Anchor T = `{end}`)")
    try:
        anchor_dt = date.fromisoformat(end)
        inputs, catalog = _fast_inference_inputs(adapter, anchor_dt)

        feature_records = []
        skipped_reasons = {}
        for rid in sorted(inputs.scope):
            try:
                feats = feature_row(inputs, rid, anchor_dt)
                feature_records.append({"repository_id": rid, "anchor_date": end, **feats})
            except Ineligible as exc:
                reason = str(exc)
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

        if not feature_records:
            st.info(
                f"Tại ngày neo `{end}`, không có repository nào đủ 30 ngày lịch sử complete (`[T-29, T]`) để chạy dự báo. "
                f"Lý do loại: `{skipped_reasons}`. Hãy chọn ngày kết thúc muộn hơn (ví dụ từ sau 30 ngày đầu của bộ dữ liệu)."
            )
        else:
            feat_df = pd.DataFrame(feature_records)
            preds_ridge = predict(model, feat_df)
            preds_pers = predict({"kind": "persistence"}, feat_df)

            feat_df["predicted_stars_next_30d"] = preds_ridge.round(1)
            feat_df["past_30d_stars"] = preds_pers.round(1)
            feat_df["expected_delta_30d"] = (feat_df["predicted_stars_next_30d"] - feat_df["past_30d_stars"]).round(1)
            feat_df["repository_name"] = feat_df["repository_id"].map(catalog["repository_name"])
            feat_df["primary_language"] = feat_df["repository_id"].map(catalog["primary_language"])
            feat_df["category"] = feat_df["repository_id"].map(catalog["category"])

            ranked_df = feat_df.sort_values(
                ["predicted_stars_next_30d", "expected_delta_30d", "repository_id"],
                ascending=[False, False, True],
            ).reset_index(drop=True)
            ranked_df.insert(0, "rank", range(1, len(ranked_df) + 1))

            st.caption(
                f"Đã chạy mô hình **{selected_name.upper()}** trực tiếp trên **{len(ranked_df)} repositories** đủ điều kiện tại ngày `{end}` "
                f"(Dự báo cho giai đoạn 30 ngày kế tiếp từ `{end}`)."
            )
            display_cols = [
                "rank", "repository_id", "repository_name", "primary_language", "category",
                "past_30d_stars", "predicted_stars_next_30d", "expected_delta_30d",
                "star_events_sum_7d", "total_events_sum_30d", "prs_opened_sum_30d",
            ]
            st.dataframe(
                ranked_df[display_cols],
                hide_index=True,
                width="stretch",
                column_config={
                    "rank": st.column_config.NumberColumn("Hạng", format="%d"),
                    "repository_id": st.column_config.NumberColumn("ID"),
                    "repository_name": st.column_config.TextColumn("Repository"),
                    "primary_language": st.column_config.TextColumn("Language"),
                    "category": st.column_config.TextColumn("Category"),
                    "past_30d_stars": st.column_config.NumberColumn("Stars 30 ngày qua", format="%.0f"),
                    "predicted_stars_next_30d": st.column_config.NumberColumn("Dự báo Stars 30 ngày tới", format="%.1f"),
                    "expected_delta_30d": st.column_config.NumberColumn("Chênh lệch dự kiến", format="%+.1f"),
                    "star_events_sum_7d": st.column_config.NumberColumn("Stars 7 ngày qua", format="%d"),
                    "total_events_sum_30d": st.column_config.NumberColumn("Total Events 30d", format="%d"),
                    "prs_opened_sum_30d": st.column_config.NumberColumn("PRs Opened 30d", format="%d"),
                },
            )

            fig_top = px.bar(
                ranked_df.head(20),
                x="repository_name",
                y=["past_30d_stars", "predicted_stars_next_30d"],
                barmode="group",
                title=f"Top 20 Repositories: Stars 30 ngày qua vs. Dự báo ML 30 ngày tới (Anchor {end})",
                labels={"value": "Số lượng Stars", "repository_name": "Repository", "variable": "Chỉ số"},
            )
            st.plotly_chart(fig_top, width="stretch")
    except Exception as exc:
        st.info(f"Không thể chạy live inference trên bộ dữ liệu hiện tại: {exc}")

    # 4. Đối chiếu Dự đoán vs Thực tế trên Tập Test (Holdout Backtest)
    if pred_file.exists():
        st.markdown("### 3. Kiểm chứng Dự đoán vs. Thực tế trên Tập Test (Holdout Evaluation)")
        pred_df = pd.read_parquet(pred_file)
        catalog_map = adapter.repository_catalog().set_index("repository_id")["repository_name"].to_dict()
        pred_df["repository_name"] = pred_df["repository_id"].map(catalog_map).fillna(
            pred_df["repository_id"].apply(lambda r: f"Repo #{r}")
        )

        col_a, col_b = st.columns(2)
        with col_a:
            fig_scatter = px.scatter(
                pred_df,
                x="target",
                y="ridge" if "ridge" in pred_df.columns else selected_name,
                hover_data=["repository_name", "anchor_date"],
                title="Thực tế (Target) vs. Dự đoán của Model (Tập Test)",
                labels={"target": "Thực tế Star 30 ngày (Target)", "ridge": "Dự đoán của Ridge Model"},
            )
            st.plotly_chart(fig_scatter, width="stretch")

        with col_b:
            repo_options = sorted(pred_df["repository_name"].unique().tolist())
            chosen_repo = st.selectbox("Chọn Repository trong tập Test để xem đường dự báo theo ngày", repo_options)
            sub_df = pred_df[pred_df["repository_name"] == chosen_repo].sort_values("anchor_date")
            y_cols = [c for c in ("target", "ridge", "persistence") if c in sub_df.columns]
            fig_line = px.line(
                sub_df,
                x="anchor_date",
                y=y_cols,
                markers=True,
                title=f"So sánh Thực tế vs. Dự báo 30d cho {chosen_repo}",
                labels={"value": "Star events (30 ngày tới)", "anchor_date": "Ngày dự đoán T"},
            )
            st.plotly_chart(fig_line, width="stretch")
