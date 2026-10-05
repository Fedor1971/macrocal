import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from macrocal import fred, intel
from macrocal.result import Result


def test_number_format_keeps_large_values_short_enough_for_a_metric_card():
    from macrocal.panels import _fmt, _fmt_delta

    assert _fmt(159044.0) == "159,044"  # no ".00": long values were truncated in the card
    assert _fmt(334.98) == "334.98"
    assert _fmt(4.2) == "4.20"
    assert _fmt(None) == "n/a"
    assert _fmt_delta(29.0, 159044.0) == "+29"
    assert _fmt_delta(-0.1, 4.2) == "-0.10"


def series_result() -> Result:
    dates = pd.date_range("2024-10-01", periods=13, freq="MS")
    df = pd.DataFrame({"date": dates, "value": [4.1 + i * 0.01 for i in range(13)]})
    return Result(
        df,
        source="US Bureau of Labor Statistics (public domain)",
        as_of="2026-10-05",
        meta={"label": "US unemployment rate (%)"},
    )


def panel_app():
    from macrocal.panels import render_event_context

    render_event_context("Unemployment Rate", "USD")


def unmapped_app():
    from macrocal.panels import render_event_context

    render_event_context("FOMC Minutes", "USD")


def non_usd_app():
    from macrocal.panels import render_event_context

    render_event_context("Unemployment Rate", "EUR")


def test_mapped_event_shows_metrics_chart_and_provenance(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    at = AppTest.from_function(panel_app).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert labels[0].startswith("Latest (")
    assert "Previous" in labels
    assert "Year over year" in labels
    caption = " ".join(c.value for c in at.caption)
    assert "Bureau of Labor Statistics" in caption
    assert "2026-10-05" in caption


def test_unmapped_event_says_no_linked_series_and_calls_nothing(monkeypatch):
    def forbidden(series):
        raise AssertionError("must not fetch for an unmapped event")

    monkeypatch.setattr(intel, "us_series", forbidden)
    at = AppTest.from_function(unmapped_app).run()
    assert not at.exception
    assert any("No linked series" in c.value for c in at.caption)
    assert len(at.metric) == 0


def test_non_usd_event_is_not_linked(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    at = AppTest.from_function(non_usd_app).run()
    assert any("No linked series" in c.value for c in at.caption)


def test_source_failure_shows_warning_not_exception(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: Result.fail("economy-intel is unreachable", "economy-intel"))
    at = AppTest.from_function(panel_app).run()
    assert not at.exception
    assert any("unreachable" in w.value for w in at.warning)


# --- Macro tab ---------------------------------------------------------------------


def wb_profile() -> Result:
    df = pd.DataFrame(
        {
            "key": ["gdp", "unemployment"],
            "label": ["GDP (current US$)", "Unemployment (% of labor force)"],
            "year": [2025, 2025],
            "value": [1.33e12, 3.874],
        }
    )
    return Result(df, source="World Bank (CC-BY 4.0)", meta={"country": "Netherlands"})


def wb_compare() -> Result:
    df = pd.DataFrame(
        {"country": ["France", "Netherlands", "Germany"], "year": [2025] * 3, "value": [7.5, 3.9, 3.7]}
    )
    return Result(df, source="World Bank (CC-BY 4.0)", meta={"label": "Unemployment (% of labor force)"})


def macro_app():
    from macrocal.panels import render_macro_tab

    render_macro_tab()


def test_macro_tab_renders_us_series_country_compare_and_profile(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    monkeypatch.setattr(intel, "compare_countries", lambda i, c: wb_compare())
    monkeypatch.setattr(intel, "country_profile", lambda c: wb_profile())
    at = AppTest.from_function(macro_app, default_timeout=30).run()
    assert not at.exception
    text = " ".join(c.value for c in at.caption)
    assert "Bureau of Labor Statistics" in text
    assert "World Bank" in text
    assert any(m.label.startswith("Unemployment") for m in at.metric)


def test_macro_tab_one_source_down_does_not_break_the_other(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: Result.fail("BLS is rate limiting", "economy-intel"))
    monkeypatch.setattr(intel, "compare_countries", lambda i, c: wb_compare())
    monkeypatch.setattr(intel, "country_profile", lambda c: wb_profile())
    at = AppTest.from_function(macro_app, default_timeout=30).run()
    assert not at.exception
    assert any("rate limiting" in w.value for w in at.warning)
    assert any("World Bank" in c.value for c in at.caption)


def test_macro_tab_changing_indicator_refetches(monkeypatch):
    seen = []

    def compare(indicator, countries):
        seen.append(indicator)
        return wb_compare()

    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    monkeypatch.setattr(intel, "compare_countries", compare)
    monkeypatch.setattr(intel, "country_profile", lambda c: wb_profile())
    at = AppTest.from_function(macro_app, default_timeout=30).run()
    at.selectbox(key="wb_indicator").select("inflation").run()
    assert seen[0] == "unemployment"
    assert seen[-1] == "inflation"


# --- FRED section (optional) ---------------------------------------------------------

def fred_result() -> Result:
    dates = pd.date_range("2025-08-01", periods=13, freq="MS")
    df = pd.DataFrame({"date": dates, "value": [4.5 - i * 0.05 for i in range(13)]})
    return Result(df, source=fred.SOURCE, as_of="2026-08-01", meta={"label": fred.SERIES["FEDFUNDS"]})


def patch_other_macro_sources(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    monkeypatch.setattr(intel, "compare_countries", lambda i, c: wb_compare())
    monkeypatch.setattr(intel, "country_profile", lambda c: wb_profile())


def test_fred_section_is_hidden_with_a_hint_when_no_key(monkeypatch):
    patch_other_macro_sources(monkeypatch)
    monkeypatch.setattr(fred, "fred_series", lambda s: pytest.fail("must not fetch without a key"))
    at = AppTest.from_function(macro_app, default_timeout=30).run()
    assert not at.exception
    assert "fred_series_pick" not in [s.key for s in at.selectbox]
    assert any("FRED_API_KEY" in c.value for c in at.caption)


def test_fred_section_renders_when_a_key_exists(monkeypatch):
    patch_other_macro_sources(monkeypatch)
    monkeypatch.setenv("FRED_API_KEY", "k-for-test")
    monkeypatch.setattr(fred, "fred_series", lambda s: fred_result())
    at = AppTest.from_function(macro_app, default_timeout=30).run()
    assert not at.exception
    assert at.selectbox(key="fred_series_pick").value == "FEDFUNDS"
    assert any("St. Louis" in c.value for c in at.caption)


def test_fred_failure_is_a_warning_and_the_rest_of_the_tab_survives(monkeypatch):
    patch_other_macro_sources(monkeypatch)
    monkeypatch.setenv("FRED_API_KEY", "k-for-test")
    monkeypatch.setattr(fred, "fred_series", lambda s: Result.fail("FRED returned HTTP 429", fred.SOURCE))
    at = AppTest.from_function(macro_app, default_timeout=30).run()
    assert not at.exception
    assert any("HTTP 429" in w.value for w in at.warning)
    assert any("World Bank" in c.value for c in at.caption)
