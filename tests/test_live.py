"""Live smoke tests: hit the real third-party services. Run manually: pytest -m live -q"""

import pytest

from macrocal import bot, fred, intel, markets

pytestmark = pytest.mark.live


def test_intel_us_series_live():
    r = intel.us_series("us_unemployment_rate")
    assert r.ok, r.error
    assert len(r.data) >= 12
    assert r.data["value"].between(0, 30).all()
    assert r.as_of


def test_intel_bad_country_is_a_clean_error_live():
    with pytest.raises(intel.IntelError, match="No data for country"):
        intel.call_tool("country_profile", {"country": "ZZZ"})


def test_intel_world_bank_loaders_live():
    profile = intel.country_profile("NLD")
    assert profile.ok, profile.error
    unemployment_in_profile = profile.data.set_index("key").loc["unemployment", "value"]

    compare = intel.compare_countries("unemployment", ["NLD", "DEU", "FRA"])
    assert compare.ok, compare.error
    assert len(compare.data) == 3
    # same cross-endpoint consistency check as the manual test on 2026-10-05
    nld = compare.data.set_index("country").loc["Netherlands", "value"]
    assert nld == unemployment_in_profile

    history = intel.country_indicator("NLD", "inflation", years=5)
    assert history.ok, history.error
    assert history.data["year"].is_monotonic_increasing


def test_intel_wb_indicator_list_has_not_drifted_live():
    listed = intel.call_tool("list_indicators", {})["world_bank"]
    assert intel.WB_INDICATORS == listed


@pytest.mark.skipif(not fred.available(), reason="needs FRED_API_KEY (free)")
def test_fred_live():
    r = fred.fred_series("FEDFUNDS")
    assert r.ok, r.error
    assert r.data["value"].between(0, 25).all()
    assert "api_key" not in (r.error or "")


def test_markets_all_assets_recent_window_live():
    keys = list(markets.ASSETS)
    r = markets.fetch_prices(keys, "2026-08-01", "2026-09-30")
    assert r.ok, r.error
    assert r.meta["missing"] == []
    assert len(r.data) >= 30
    assert r.data["bond10y"].dropna().between(0.5, 15).all()  # percent, not yield x 10; NaN = US holiday
    corr = markets.correlation(r.data)
    assert corr.shape == (6, 6)


def test_markets_2008_crisis_window_live():
    start, end = markets.CRISIS_WINDOWS["Global financial crisis 2008"]
    r = markets.fetch_prices(list(markets.ASSETS), start, end)
    assert r.ok, r.error
    assert r.meta["missing"] == [], f"no 2008 data for {r.meta['missing']}"
    sp = markets.normalise(r.data)["sp500"]
    assert sp.min() < 70  # the S&P fell by more than 30% across that window


@pytest.mark.skipif(not bot.available(), reason="needs GEMINI_API_KEY (Google AI Studio)")
def test_gemini_analyst_answers_from_tools_live():
    analyst = bot.make_analyst()
    session: dict = {}
    answer = analyst.ask("What is the latest US unemployment rate?", [], session)
    assert answer.error is None, answer.error
    assert any(c.name == "us_series" and c.ok for c in answer.tool_calls)
    latest = intel.us_series("us_unemployment_rate").data["value"].iloc[-1]
    assert f"{latest:.1f}" in answer.text  # the figure in the answer is the tool's figure


@pytest.mark.skipif(not bot.available(), reason="needs GEMINI_API_KEY (Google AI Studio)")
def test_gemini_analyst_refuses_off_topic_questions_live():
    answer = bot.make_analyst().ask("Write me a poem about cats.", [], {})
    assert answer.error is None, answer.error
    assert answer.tool_calls == []
    assert "cat" not in answer.text.lower() or len(answer.text) < 400  # a refusal, not a poem
