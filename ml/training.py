"""Deterministic training skeleton; selection uses validation MAE only."""
import numpy as np
import pandas as pd

from ml.features import FEATURES


def matrix(frame):
    values = frame.loc[:, FEATURES].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Feature matrix must be finite")
    return values


def fit_ridge(train, alpha):
    if isinstance(alpha, bool) or not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("ridge_alpha must be finite and positive")
    x = matrix(train)
    y = train.target.to_numpy(dtype=float)
    if len(y) == 0 or not np.isfinite(y).all() or (y < 0).any():
        raise ValueError("Training requires nonempty finite nonnegative labels")
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    centered = (x - mean) / scale
    intercept = float(y.mean())
    # Augmented least squares: penalty on coefficients, not the intercept.
    design = np.vstack([centered, np.sqrt(alpha) * np.eye(len(FEATURES))])
    response = np.concatenate([y - intercept, np.zeros(len(FEATURES))])
    coefficients = np.linalg.lstsq(design, response, rcond=None)[0]
    return {"kind": "ridge", "alpha": alpha, "mean": mean.tolist(),
            "scale": scale.tolist(), "coefficients": coefficients.tolist(),
            "intercept": intercept}


def predict(model, frame):
    if model["kind"] == "persistence":
        values = frame.star_events_sum_30d.to_numpy(dtype=float)
    elif model["kind"] == "zero":
        values = np.zeros(len(frame))
    elif model["kind"] == "ridge":
        mean, scale, coef = [np.asarray(model[key], dtype=float)
                             for key in ("mean", "scale", "coefficients")]
        if any(vector.shape != (len(FEATURES),) for vector in (mean, scale, coef)):
            raise ValueError("Model feature dimensions do not match schema")
        if not all(np.isfinite(v).all() for v in (mean, scale, coef)) or (scale <= 0).any():
            raise ValueError("Invalid model parameters")
        values = ((matrix(frame) - mean) / scale) @ coef + model["intercept"]
    else:
        raise ValueError("Unsupported model kind")
    if not np.isfinite(values).all():
        raise ValueError("Predictions must be finite")
    return np.maximum(values, 0)


def score(frame, predictions):
    target = frame.target.to_numpy(dtype=float)
    predictions = np.asarray(predictions, dtype=float)
    if (len(frame) == 0 or predictions.shape != target.shape
            or not np.isfinite(target).all() or (target < 0).any()
            or not np.isfinite(predictions).all()):
        raise ValueError("Evaluation requires nonempty aligned finite predictions/labels")
    errors = np.maximum(predictions, 0) - target
    absolute = np.abs(errors)
    return {
        "mae": float(absolute.mean()), "rmse": float(np.sqrt(np.mean(errors**2))),
        "macro_mae": float(pd.Series(absolute).groupby(frame.repository_id.to_numpy()).mean().mean()),
        "rows": len(frame), "repositories": int(frame.repository_id.nunique()),
        "zero_label_fraction": float(np.mean(target == 0)),
    }


def evaluate(model, test, train_ids):
    predictions = predict(model, test)
    result = score(test, predictions)
    result["by_anchor"] = {str(day): score(group, predict(model, group))
                           for day, group in test.groupby("anchor_date", sort=True)}
    result["by_activity"] = {}
    result["by_seen_repository"] = {}
    for name, mask in [("zero", test.total_events_sum_30d == 0),
                       ("nonzero", test.total_events_sum_30d > 0)]:
        group = test[mask]
        result["by_activity"][name] = None if group.empty else score(group, predict(model, group))
    for name, mask in [("seen", test.repository_id.isin(train_ids)),
                       ("unseen", ~test.repository_id.isin(train_ids))]:
        group = test[mask]
        result["by_seen_repository"][name] = None if group.empty else score(group, predict(model, group))
    # A single prespecified calendar offset; never choose the best offset.
    origin = pd.Timestamp("1970-01-01")
    spaced = test[(pd.to_datetime(test.anchor_date) - origin).dt.days % 30 == 0]
    result["anchors_every_30d"] = None if spaced.empty else score(spaced, predict(model, spaced))
    result["sensitivity_calendar_origin"] = "1970-01-01"
    return result


def train_and_evaluate(samples, alpha):
    blocks = {name: samples[samples.split == name].copy()
              for name in ("train", "validation", "test")}
    empty = [name for name, block in blocks.items() if block.empty]
    if empty:
        return {"status": "blocked", "reason": "empty_splits", "empty_splits": empty}, None, None
    models = {"persistence": {"kind": "persistence"}, "zero": {"kind": "zero"},
              "ridge": fit_ridge(blocks["train"], alpha)}
    validation = {name: score(blocks["validation"], predict(model, blocks["validation"]))
                  for name, model in models.items()}
    selected = "persistence"
    for name in ("zero", "ridge"):
        if validation[name]["mae"] < validation[selected]["mae"] - 1e-12:
            selected = name
    # Test is read for scoring only, after selection is frozen.
    train_ids = set(blocks["train"].repository_id)
    test = {name: evaluate(model, blocks["test"], train_ids) for name, model in models.items()}
    baseline = test["persistence"]["mae"]
    for metrics in test.values():
        metrics["mae_delta_vs_persistence"] = metrics["mae"] - baseline
        metrics["relative_mae_improvement"] = None if baseline == 0 else (baseline - metrics["mae"]) / baseline
    predictions = blocks["test"][["repository_id", "anchor_date", "target"]].copy()
    for name, model in models.items():
        predictions[name] = predict(model, blocks["test"])
    report = {"status": "completed", "selected": selected, "validation": validation,
              "test": test, "split_rows": {name: len(block) for name, block in blocks.items()},
              "train_repository_ids": sorted(map(int, train_ids))}
    return report, models[selected], predictions
