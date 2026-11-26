import hashlib
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parent


@pytest.mark.parametrize("source", ["fixture", "snapshot"])
def test_forecast_harness_only_displays_fixture_artifacts(tmp_path, monkeypatch, source):
    monkeypatch.setenv("APP_ML_MODEL_DIR", str(tmp_path))
    model = b'{"model":{"kind":"persistence"}}'
    (tmp_path / "model.json").write_bytes(model)
    report = {
        "status": "completed",
        "publication": {"data_source": source},
        "selected": "persistence",
        "test": {"persistence": {"mae": 4.25}},
        "model_sha256": hashlib.sha256(model).hexdigest(),
    }
    (tmp_path / "run.json").write_text(json.dumps(report), encoding="utf8")

    app = AppTest.from_file(str(ROOT / "forecast_fixture_app.py")).run()
    assert not app.exception and app.warning
    if source == "fixture":
        assert [metric.value for metric in app.metric] == ["persistence", "4.25"]
        (tmp_path / "model.json").write_bytes(b"corrupted")
        app.run()
    assert not app.metric
    assert app.info


def test_main_app_does_not_expose_forecast_fixture(monkeypatch):
    monkeypatch.setenv("APP_DATA_SOURCE", "fixture")
    monkeypatch.setenv("APP_ENABLE_ML_FORECAST_DEMO", "1")
    app = AppTest.from_file(str(ROOT.parent / "app.py")).run()
    assert not app.exception
    assert app.sidebar.radio(key="page").options == ["Overview", "Repository Explorer", "Growth Analytics"]
