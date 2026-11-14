import numpy as np
import pandas as pd
import pytest

from ml.features import FEATURES
from ml.training import fit_ridge, predict, score, train_and_evaluate


def examples():
    rows = []
    for block, start, count in [("train", "2025-01-01", 8), ("validation", "2025-04-01", 4), ("test", "2025-07-01", 4)]:
        for i, anchor in enumerate(pd.date_range(start, periods=count)):
            value = i + 1
            features = dict.fromkeys(FEATURES, value)
            features["star_events_sum_30d"] = 2 * value
            rows.append({"repository_id": 1 if i % 2 else 2, "anchor_date": str(anchor.date()),
                         "split": block, "target": 4 * value, **features})
    return pd.DataFrame(rows)


def test_fit_is_deterministic_and_uses_only_training_statistics():
    samples = examples()
    train = samples[samples.split == "train"]
    model = fit_ridge(train, 1.0)
    assert model == fit_ridge(train, 1.0)
    np.testing.assert_allclose(model["mean"], train[list(FEATURES)].mean().to_numpy())
    first_report, first_model, _ = train_and_evaluate(samples, 1.0)
    samples.loc[samples.split == "test", "target"] = 999999
    second_report, second_model, _ = train_and_evaluate(samples, 1.0)
    assert first_model == second_model
    assert first_report["validation"] == second_report["validation"]
    assert first_report["selected"] == second_report["selected"]
    assert first_report["test"] != second_report["test"]


def test_validation_features_do_not_change_fitted_parameters():
    samples = examples()
    original = fit_ridge(samples[samples.split == "train"], 1.0)
    samples.loc[samples.split != "train", list(FEATURES)] = 1e9
    assert original == fit_ridge(samples[samples.split == "train"], 1.0)


def test_tied_mae_keeps_persistence():
    samples = examples()
    samples.loc[:, list(FEATURES)] = 0
    samples.loc[:, "target"] = 0
    report, model, predictions = train_and_evaluate(samples, 1.0)
    assert report["selected"] == model["kind"] == "persistence"
    assert report["test"]["ridge"]["relative_mae_improvement"] is None
    assert (predictions.ridge == 0).all()


def test_empty_splits_block_without_model():
    report, model, predictions = train_and_evaluate(examples().query("split == 'validation'"), 1.0)
    assert report["status"] == "blocked"
    assert report["empty_splits"] == ["train", "test"]
    assert model is None and predictions is None


def test_metrics_use_original_scale_and_macro_repo_mae():
    frame = pd.DataFrame({"target": [0, 2, 10], "repository_id": [1, 1, 2]})
    metrics = score(frame, [0, 0, 0])
    assert metrics["mae"] == 4
    assert metrics["macro_mae"] == 5.5
    assert metrics["rmse"] == pytest.approx(np.sqrt(104 / 3))
    assert metrics["zero_label_fraction"] == pytest.approx(1 / 3)
    assert score(frame, [-3, -2, -1]) == metrics


@pytest.mark.parametrize("predictions", [[0, 0], [0, 0, np.nan], [0, np.inf, 0]])
def test_invalid_predictions_fail_scoring(predictions):
    frame = pd.DataFrame({"target": [0, 1, 2], "repository_id": [1, 1, 1]})
    with pytest.raises(ValueError):
        score(frame, predictions)


def test_model_schema_rejected_and_negative_outputs_clamped():
    frame = examples()
    model = fit_ridge(frame.query("split == 'train'"), 1.0)
    model["intercept"] = -1e9
    assert (predict(model, frame) == 0).all()
    model["scale"] = [0] * len(FEATURES)
    with pytest.raises(ValueError):
        predict(model, frame)
