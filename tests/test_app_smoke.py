from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from macrocal import events, intel, markets
from macrocal.result import Result

APP = str(Path(__file__).resolve().parent.parent / "app.py")
VIEWS = ["Calendar", "Macro", "Markets", "Ask"]


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


@pytest.fixture
def calls(monkeypatch):
    """Fake every data source and record which ones the app touched."""
    seen: list[str] = []

    def fake(name, result):
        def _fn(*args, **kwargs):
            seen.append(name)
            return result

        return _fn

    series = Result(
        pd.DataFrame({"date": pd.date_range("2025-09-01", periods=13, freq="MS"), "value": range(13)}),
        source="BLS",
        as_of="2026-10-05",
        meta={"label": "x"},
    )
    compare = Result(
        pd.DataFrame({"country": ["France"], "year": [2025], "value": [7.5]}),
        source="World Bank (CC-BY 4.0)",
        meta={"label": "Unemployment"},
    )
    profile = Result(
        pd.DataFrame({"key": ["gdp"], "label": ["GDP"], "year": [2025], "value": [1.0e12]}),
        source="World Bank (CC-BY 4.0)",
        meta={"country": "Netherlands"},
    )

    prices = Result(
        pd.DataFrame({"date": pd.bdate_range("2026-01-01", periods=60), "sp500": range(60), "gold": range(60)}),
        source=markets.SOURCE,
        as_of="2026-03-24",
        meta={"missing": [], "labels": {"sp500": "S&P 500", "gold": "Gold futures"}},
    )

    def raw(start, end):
        seen.append("calendar")
        return fake_raw(start, end)

    monkeypatch.setattr(events, "_fetch_calendar_raw", raw)
    monkeypatch.setattr(intel, "us_series", fake("us_series", series))
    monkeypatch.setattr(intel, "compare_countries", fake("compare_countries", compare))
    monkeypatch.setattr(intel, "country_profile", fake("country_profile", profile))
    monkeypatch.setattr(markets, "fetch_prices", fake("fetch_prices", prices))
    return seen


def run_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=30).run()


def test_app_offers_four_views_and_opens_on_calendar(calls):
    at = run_app()
    assert not at.exception
    switcher = at.segmented_control(key="view")
    assert list(switcher.options) == VIEWS
    assert switcher.value == "Calendar"


def test_calendar_view_shows_events_and_filter_widgets(calls):
    at = run_app()
    assert len(at.dataframe) == 1
    assert len(at.dataframe[0].value) == 2
    assert [m.label for m in at.sidebar.multiselect] == ["Impact", "Currency"]


def test_unopened_views_do_not_touch_their_data_sources(calls):
    run_app()
    assert calls == ["calendar"]  # nothing from the Macro tab's sources


def test_impact_filter_narrows_rows(calls):
    at = run_app()
    at.sidebar.multiselect[0].set_value(["HIGH"]).run()
    assert len(at.dataframe[0].value) == 1


def test_switching_to_macro_loads_macro_sources_not_the_calendar(calls):
    at = run_app()
    calls.clear()
    at.segmented_control(key="view").set_value("Macro").run()
    assert not at.exception
    assert "us_series" in calls
    assert "compare_countries" in calls
    assert "calendar" not in calls
    assert len(at.dataframe) == 0


def test_calendar_failure_shows_error_and_keeps_the_view_switcher(calls, monkeypatch):
    def boom(start, end):
        raise RuntimeError("fxstreet down")

    monkeypatch.setattr(events, "_fetch_calendar_raw", boom)
    at = run_app()
    assert not at.exception
    assert any("fxstreet down" in e.value for e in at.error)
    assert list(at.segmented_control(key="view").options) == VIEWS


def test_switching_to_markets_loads_only_the_markets_source(calls):
    at = run_app()
    calls.clear()
    at.segmented_control(key="view").set_value("Markets").run()
    assert not at.exception
    assert calls == ["fetch_prices"]
    assert len(at.get("plotly_chart")) == 2
