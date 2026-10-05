import datetime as dt

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from macrocal import fred, intel, markets
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


# --- Markets view -----------------------------------------------------------------------


def markets_result(keys, missing=()) -> Result:
    rng = np.random.default_rng(3)
    n = 80
    frame = pd.DataFrame({"date": pd.bdate_range("2026-01-01", periods=n)})
    for k in keys:
        frame[k] = 100 + np.cumsum(rng.normal(0, 1, n))
    return Result(
        frame,
        source=markets.SOURCE,
        as_of="2026-04-21",
        meta={"missing": list(missing), "labels": {k: markets.ASSETS[k][1] for k in keys}},
    )


def markets_app():
    from macrocal.panels import render_markets_tab

    render_markets_tab()


def test_markets_view_shows_normalised_chart_heatmap_and_provenance(monkeypatch):
    monkeypatch.setattr(markets, "fetch_prices", lambda keys, s, e: markets_result(keys))
    at = AppTest.from_function(markets_app, default_timeout=30).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 2
    text = " ".join(c.value for c in at.caption)
    assert "Yahoo Finance" in text
    assert "2026-04-21" in text


def test_markets_default_window_is_the_last_year_ending_today(monkeypatch):
    seen = []

    def fetch(keys, start, end):
        seen.append((start, end))
        return markets_result(keys)

    monkeypatch.setattr(markets, "fetch_prices", fetch)
    AppTest.from_function(markets_app, default_timeout=30).run()
    start, end = seen[0]
    assert end == dt.date.today().isoformat()  # noqa: DTZ011
    assert start < end


def test_choosing_a_crisis_preset_requests_exactly_that_window(monkeypatch):
    seen = []

    def fetch(keys, start, end):
        seen.append((start, end))
        return markets_result(keys)

    monkeypatch.setattr(markets, "fetch_prices", fetch)
    at = AppTest.from_function(markets_app, default_timeout=30).run()
    at.selectbox(key="mk_preset").select("COVID-19 crash 2020").run()
    assert seen[-1] == markets.CRISIS_WINDOWS["COVID-19 crash 2020"]


def test_markets_source_failure_is_a_warning(monkeypatch):
    failure = Result.fail("Yahoo Finance request failed (HTTPError)", markets.SOURCE)
    monkeypatch.setattr(markets, "fetch_prices", lambda k, s, e: failure)
    at = AppTest.from_function(markets_app, default_timeout=30).run()
    assert not at.exception
    assert any("request failed" in w.value for w in at.warning)


def test_assets_without_data_are_named_in_a_warning(monkeypatch):
    monkeypatch.setattr(
        markets, "fetch_prices", lambda keys, s, e: markets_result(["sp500", "gold"], missing=["oil"])
    )
    at = AppTest.from_function(markets_app, default_timeout=30).run()
    assert not at.exception
    assert any("WTI crude oil futures" in w.value for w in at.warning)


def test_clearing_the_asset_selection_asks_for_one_and_fetches_nothing_more(monkeypatch):
    fetches = []

    def fetch(keys, start, end):
        fetches.append(list(keys))
        return markets_result(keys)

    monkeypatch.setattr(markets, "fetch_prices", fetch)
    at = AppTest.from_function(markets_app, default_timeout=30).run()
    assert len(fetches) == 1
    at.multiselect(key="mk_assets").set_value([]).run()
    assert len(fetches) == 1
    assert any("at least one asset" in i.value for i in at.info)


def test_one_asset_shows_the_chart_but_explains_why_there_is_no_heatmap(monkeypatch):
    monkeypatch.setattr(markets, "fetch_prices", lambda keys, s, e: markets_result(keys))
    at = AppTest.from_function(markets_app, default_timeout=30).run()
    at.multiselect(key="mk_assets").set_value(["sp500"]).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 1
    assert any("two or more" in i.value for i in at.info)


# --- rate series show percentage points, not a relative % change -------------------------


def cpi_app():
    from macrocal.panels import render_event_context

    render_event_context("Consumer Price Index (YoY)", "USD")


def yoy_value(at) -> str:
    return next(m.value for m in at.metric if m.label == "Year over year")


def test_rate_series_year_over_year_is_in_percentage_points(monkeypatch):
    # unemployment 4.1 a year ago -> 4.2 now: "+0.1 pp", not a misleading "+2.4%"
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    at = AppTest.from_function(panel_app).run()
    assert yoy_value(at).endswith("pp")


def test_index_series_year_over_year_stays_a_percent_change(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    at = AppTest.from_function(cpi_app).run()
    assert yoy_value(at).endswith("%")
    assert "pp" not in yoy_value(at)


def test_the_rate_series_are_the_two_percentage_series():
    assert intel.RATE_SERIES == {"us_unemployment_rate", "us_labor_participation"}


# --- Ask view ------------------------------------------------------------------------------


from macrocal import bot


class StubAnalyst:
    """Stands in for bot.Analyst so the UI can be tested without Gemini."""

    def __init__(self, answer=None):
        self.questions: list[str] = []
        self.answer = answer or bot.Answer(
            text="US unemployment is 4.2% (us_series, BLS, as of 2026-10-05).",
            tool_calls=[bot.ToolCall("us_series", {"series": "us_unemployment_rate"}, True)],
        )

    def ask(self, question, history, session):
        self.questions.append(question)
        return self.answer


def ask_app():
    from macrocal.panels import render_ask_tab

    render_ask_tab()


def test_ask_tab_is_disabled_with_instructions_when_there_is_no_key(monkeypatch):
    monkeypatch.setattr(bot, "make_analyst", lambda: pytest.fail("must not build a client without a key"))
    at = AppTest.from_function(ask_app, default_timeout=30).run()
    assert not at.exception
    assert any("GEMINI_API_KEY" in c.value for c in at.caption)
    assert len(at.chat_input) == 0


def test_ask_tab_warns_about_sensitive_information_when_enabled(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-for-test")
    monkeypatch.setattr(bot, "make_analyst", lambda: StubAnalyst())
    at = AppTest.from_function(ask_app, default_timeout=30).run()
    assert not at.exception
    text = " ".join(c.value for c in at.caption)
    assert "Google" in text and "sensitive" in text
    assert len(at.chat_input) == 1


def test_a_question_is_answered_with_tool_citations(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-for-test")
    stub = StubAnalyst()
    monkeypatch.setattr(bot, "make_analyst", lambda: stub)
    at = AppTest.from_function(ask_app, default_timeout=30).run()
    at.chat_input[0].set_value("What is US unemployment?").run()
    assert not at.exception
    assert stub.questions == ["What is US unemployment?"]
    rendered = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "4.2%" in rendered
    assert "us_series" in rendered  # the tool that produced the figure is shown under the answer


def test_a_failed_tool_is_marked_in_the_citations(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-for-test")
    failed = bot.Answer(text="No data right now.", tool_calls=[bot.ToolCall("us_series", {"series": "us_cpi"}, False)])
    monkeypatch.setattr(bot, "make_analyst", lambda: StubAnalyst(failed))
    at = AppTest.from_function(ask_app, default_timeout=30).run()
    at.chat_input[0].set_value("CPI?").run()
    text = " ".join(c.value for c in at.caption)
    assert "failed" in text.lower()


def test_an_error_answer_is_shown_as_an_error_not_a_reply(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-for-test")
    capped = bot.Answer(error="Session limit reached (15 questions). Reload the page to start again.")
    monkeypatch.setattr(bot, "make_analyst", lambda: StubAnalyst(capped))
    at = AppTest.from_function(ask_app, default_timeout=30).run()
    at.chat_input[0].set_value("hello").run()
    assert not at.exception
    assert any("Session limit" in e.value for e in at.error)


def test_history_is_kept_between_questions(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-for-test")
    seen = []

    class Recording(StubAnalyst):
        def ask(self, question, history, session):
            seen.append(list(history))
            return super().ask(question, history, session)

    stub = Recording()
    monkeypatch.setattr(bot, "make_analyst", lambda: stub)
    at = AppTest.from_function(ask_app, default_timeout=30).run()
    at.chat_input[0].set_value("first").run()
    at.chat_input[0].set_value("second").run()
    assert seen[0] == []
    assert [t["role"] for t in seen[1]] == ["user", "assistant"]
    assert seen[1][0]["text"] == "first"


def test_the_client_is_built_once_per_session_not_per_message(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-for-test")
    built = []

    def make():
        built.append(1)
        return StubAnalyst()

    monkeypatch.setattr(bot, "make_analyst", make)
    at = AppTest.from_function(ask_app, default_timeout=30).run()
    at.chat_input[0].set_value("a").run()
    at.chat_input[0].set_value("b").run()
    assert len(built) == 1
