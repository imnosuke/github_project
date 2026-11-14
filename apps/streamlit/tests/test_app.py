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
