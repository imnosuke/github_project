from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_navigation_and_shared_dates():
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    app.sidebar.date_input[0].set_value((date(2026, 8, 14), date(2026, 8, 16))).run()
    for page in ["Repository Explorer", "Growth Analytics", "Overview"]:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
        assert any("chưa complete" in item.value for item in app.warning)
        assert app.sidebar.date_input[0].value == (date(2026, 8, 14), date(2026, 8, 16))


def test_empty_search():
    app = AppTest.from_file(str(APP)).run()
    app.sidebar.radio[0].set_value("Repository Explorer").run()
    app.text_input[0].set_value("does-not-exist").run()
    assert not app.exception
    assert any("Không tìm thấy" in item.value for item in app.info)


def test_load_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_FIXTURE_DIR", str(tmp_path))
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert any("Không thể tải" in item.value for item in app.error)


def test_incompatible_adapter_shows_retry(monkeypatch):
    import apps.streamlit.data as data

    monkeypatch.setenv("APP_FIXTURE_DIR", "incompatible-adapter-test")
    monkeypatch.setattr(data, "get_adapter", lambda **kwargs: object())
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert any("Không thể tải" in item.value for item in app.error)
    assert any(button.label == "Thử lại" for button in app.button)


def test_explorer_metadata_and_comparison():
    app = AppTest.from_file(str(APP)).run()
    app.sidebar.radio[0].set_value("Repository Explorer").run()
    app.selectbox(key="detail_repo").set_value(1006).run()
    assert not app.exception
    assert any("chưa có metadata snapshot" in item.value for item in app.info)
    assert app.selectbox(key="compare_repo").value != 1006
    app.selectbox(key="detail_repo").set_value(1005).run()
    assert not app.exception
    assert any("Không tổng hợp toàn kỳ" in item.value for item in app.warning)


def test_explorer_filter_and_pagination():
    app = AppTest.from_file(str(APP)).run()
    app.sidebar.radio[0].set_value("Repository Explorer").run()
    app.selectbox(key="filter_primary_language").set_value("Chưa có metadata").run()
    assert not app.exception
    assert app.selectbox(key="detail_repo").value == 1006
    assert any("Cần ít nhất hai" in item.value for item in app.info)

def test_forecast_demo_is_opt_in_and_fixture_only(monkeypatch):
    monkeypatch.setenv("APP_DATA_SOURCE", "fixture")
    monkeypatch.delenv("APP_ENABLE_ML_FORECAST_DEMO", raising=False)
    app = AppTest.from_file(str(APP)).run()
    assert "ML Forecast Demo" not in app.sidebar.radio(key="page").options

    monkeypatch.setenv("APP_ENABLE_ML_FORECAST_DEMO", "1")
    app.run()
    app.sidebar.radio(key="page").set_value("ML Forecast Demo").run()
    assert not app.exception
    assert any("publication" in warning.value for warning in app.warning)

    monkeypatch.setenv("APP_DATA_SOURCE", "snapshot")
    monkeypatch.setenv("APP_SNAPSHOT_DIR", str(APP.parent / "data/snapshots/gharchive-2025-01-15"))
    app = AppTest.from_file(str(APP)).run()
    assert "ML Forecast Demo" not in app.sidebar.radio(key="page").options
