from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from macrocal import events

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def fake_raw(start, end):
    return pd.DataFrame(
        {
            "Id": ["a", "b"],
            "Start": ["10/06/2026 08:00:00", "10/07/2026 14:30:00"],
            "Name": ["Unemployment Rate", "Core CPI (MoM)"],
            "Impact": ["MEDIUM", "HIGH"],
            "Currency": ["USD", "USD"],
        }
    )


def test_app_renders_four_tabs_without_exception(monkeypatch):
    monkeypatch.setattr(events, "_fetch_calendar_raw", fake_raw)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Calendar", "Macro", "Markets", "Ask"]


def test_calendar_tab_shows_events_and_filter_widgets(monkeypatch):
    monkeypatch.setattr(events, "_fetch_calendar_raw", fake_raw)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.dataframe) == 1
    assert len(at.dataframe[0].value) == 2
    assert [m.label for m in at.sidebar.multiselect] == ["Impact", "Currency"]


def test_impact_filter_narrows_rows(monkeypatch):
    monkeypatch.setattr(events, "_fetch_calendar_raw", fake_raw)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.multiselect[0].set_value(["HIGH"]).run()
    assert len(at.dataframe[0].value) == 1


def test_calendar_failure_shows_error_and_keeps_other_tabs(monkeypatch):
    def boom(start, end):
        raise RuntimeError("fxstreet down")

    monkeypatch.setattr(events, "_fetch_calendar_raw", boom)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("fxstreet down" in e.value for e in at.error)
    assert [t.label for t in at.tabs] == ["Calendar", "Macro", "Markets", "Ask"]
