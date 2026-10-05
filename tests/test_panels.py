import pandas as pd
from streamlit.testing.v1 import AppTest

from macrocal import intel
from macrocal.result import Result


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
