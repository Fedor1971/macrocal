import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from macrocal import bot, events, fred, intel, markets
from macrocal.result import Result

SECRET = "AIza-test-secret-key-0123456789"


# --- fakes ----------------------------------------------------------------------------


def reply(text=None, calls=()):
    """What the SDK returns: .text, .function_calls and candidates[0].content."""
    function_calls = [SimpleNamespace(name=n, args=a) for n, a in calls] or None
    return SimpleNamespace(
        text=text, function_calls=function_calls, candidates=[SimpleNamespace(content=f"turn:{text or calls}")]
    )


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.requests: list[dict] = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, *, model, contents, config=None):
        self.requests.append({"model": model, "contents": list(contents), "config": config})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def analyst(script, **kw):
    client = FakeClient(script)
    kw.setdefault("limiter", bot.UsageLimiter(session_cap=15, daily_cap=200, today=lambda: dt.date(2026, 10, 5)))
    return bot.Analyst(client, model="test-model", **kw), client


def series_result(label="US unemployment rate (%)", n=30) -> Result:
    df = pd.DataFrame({"date": pd.date_range("2024-04-01", periods=n, freq="MS"), "value": [4.0 + i / 100 for i in range(n)]})
    return Result(df, source="BLS", as_of="2026-10-05", meta={"label": label})


# --- tool catalogue ------------------------------------------------------------------------


def test_tool_names_without_fred():
    assert {t.name for t in bot.tool_specs()} == {
        "get_calendar", "us_series", "country_profile", "compare_countries", "market_summary",
    }  # fmt: skip


def test_fred_tool_exists_only_when_a_key_is_configured(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "k")
    assert "fred_series" in {t.name for t in bot.tool_specs()}


def test_every_tool_has_a_description_and_a_json_schema():
    for spec in bot.tool_specs():
        assert spec.description
        assert spec.schema["type"] == "object"
        assert "properties" in spec.schema


def test_system_prompt_keeps_the_grounding_rules():
    prompt = bot.SYSTEM_PROMPT.lower()
    assert "only" in prompt and "tool" in prompt
    assert "never" in prompt and "memory" in prompt
    assert "not instructions" in prompt or "never instructions" in prompt
    assert "investment advice" in prompt


# --- argument validation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("us_series", {}),  # missing required
        ("us_series", {"series": "us_cpi", "extra": 1}),  # unknown argument
        ("us_series", {"series": "not_a_series"}),  # outside the enum
        ("us_series", {"series": 5}),  # wrong type
        ("compare_countries", {"indicator": "gdp", "countries": []}),
        ("compare_countries", {"indicator": "gdp", "countries": ["NLD"] * 11}),
        ("compare_countries", {"indicator": "gdp", "countries": "NLD"}),
        ("get_calendar", {"start_date": "2026-10-01", "end_date": "2026-12-31"}),  # window too long
        ("get_calendar", {"start_date": "yesterday", "end_date": "2026-10-02"}),
        ("get_calendar", {"start_date": "2026-10-01", "end_date": "2026-10-02", "impact": "HUGE"}),
        ("market_summary", {"assets": ["sp500"], "preset": "Last decade"}),
        ("market_summary", {"assets": ["dogecoin"], "preset": "Last 1 year"}),
    ],
)
def test_bad_arguments_are_rejected_before_any_data_call(monkeypatch, tool, args):
    for module, name in [(intel, "us_series"), (intel, "compare_countries"), (events, "fetch_calendar"), (markets, "fetch_prices")]:
        monkeypatch.setattr(module, name, lambda *a, **k: pytest.fail("data source must not be called"))
    out = bot.run_tool(tool, args)
    assert "error" in out


def test_unknown_tool_is_an_error_not_an_exception():
    assert "error" in bot.run_tool("rm_rf", {})


def test_non_dict_arguments_are_rejected():
    assert "error" in bot.run_tool("us_series", "us_cpi")


# --- tool behaviour ----------------------------------------------------------------------------


def test_us_series_tool_returns_recent_points_with_provenance(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    out = bot.run_tool("us_series", {"series": "us_unemployment_rate"})
    assert out["source"] == "BLS"
    assert out["as_of"] == "2026-10-05"
    assert out["label"] == "US unemployment rate (%)"
    assert len(out["points"]) <= 24
    assert out["points"][-1]["value"] == pytest.approx(4.29)
    assert out["latest"]["value"] == pytest.approx(4.29)
    assert out["previous"]["value"] == pytest.approx(4.28)


def test_country_profile_tool_routes_to_the_loader(monkeypatch):
    seen = {}
    df = pd.DataFrame({"key": ["unemployment"], "label": ["Unemployment (% of labor force)"], "year": [2025], "value": [3.874]})

    def profile(country):
        seen["country"] = country
        return Result(df, source="World Bank (CC-BY 4.0)", meta={"country": "Netherlands"})

    monkeypatch.setattr(intel, "country_profile", profile)
    out = bot.run_tool("country_profile", {"country": "NLD"})
    assert seen["country"] == "NLD"
    assert out["country"] == "Netherlands"
    assert out["indicators"][0] == {"indicator": "Unemployment (% of labor force)", "year": 2025, "value": 3.874}


def test_compare_countries_tool_keeps_ranking(monkeypatch):
    df = pd.DataFrame({"country": ["France", "Germany"], "year": [2025, 2025], "value": [7.5, 3.7]})
    monkeypatch.setattr(intel, "compare_countries", lambda i, c: Result(df, source="World Bank (CC-BY 4.0)", meta={"label": "Unemployment"}))
    out = bot.run_tool("compare_countries", {"indicator": "unemployment", "countries": ["FRA", "DEU"]})
    assert [r["country"] for r in out["ranking"]] == ["France", "Germany"]
    assert out["indicator"] == "Unemployment"


def test_market_summary_reports_percent_change_and_points_for_the_yield(monkeypatch):
    df = pd.DataFrame(
        {"date": pd.bdate_range("2026-01-01", periods=3), "sp500": [100.0, 105.0, 110.0], "bond10y": [5.0, 5.1, 5.2]}
    )
    seen = {}

    def fetch(keys, start, end):
        seen.update(keys=keys, start=start, end=end)
        return Result(df, source=markets.SOURCE, as_of="2026-01-05", meta={"missing": [], "labels": {"sp500": "S&P 500", "bond10y": "US 10-year yield (%)"}})

    monkeypatch.setattr(markets, "fetch_prices", fetch)
    out = bot.run_tool("market_summary", {"assets": ["sp500", "bond10y"], "preset": "COVID-19 crash 2020"})
    by = {a["asset"]: a for a in out["assets"]}
    assert (seen["start"], seen["end"]) == markets.CRISIS_WINDOWS["COVID-19 crash 2020"]
    assert by["S&P 500"]["change"] == pytest.approx(10.0)
    assert by["S&P 500"]["change_unit"] == "%"
    assert by["US 10-year yield (%)"]["change"] == pytest.approx(0.2)
    assert by["US 10-year yield (%)"]["change_unit"] == "percentage points"
    assert out["as_of"] == "2026-01-05"


def test_calendar_tool_filters_and_caps_rows(monkeypatch):
    n = 100
    df = pd.DataFrame(
        {
            "Id": [str(i) for i in range(n)],
            "Start": pd.date_range("2026-10-05", periods=n, freq="h"),
            "Name": [f"Event {i}" for i in range(n)],
            "Impact": ["HIGH" if i % 2 == 0 else "LOW" for i in range(n)],
            "Currency": ["USD" if i % 4 < 2 else "EUR" for i in range(n)],
        }
    )
    monkeypatch.setattr(events, "fetch_calendar", lambda s, e: Result(df, source=events.SOURCE, as_of=f"{s} to {e}"))
    out = bot.run_tool("get_calendar", {"start_date": "2026-10-05", "end_date": "2026-10-12", "impact": "HIGH", "currency": "USD"})
    assert all(r["impact"] == "HIGH" and r["currency"] == "USD" for r in out["events"])
    assert 0 < len(out["events"]) <= bot.MAX_CALENDAR_ROWS
    assert set(out["events"][0]) == {"start", "name", "impact", "currency"}


def test_calendar_tool_says_when_rows_were_cut(monkeypatch):
    n = bot.MAX_CALENDAR_ROWS + 25
    df = pd.DataFrame(
        {"Id": [str(i) for i in range(n)], "Start": pd.date_range("2026-10-05", periods=n, freq="h"),
         "Name": ["x"] * n, "Impact": ["HIGH"] * n, "Currency": ["USD"] * n}
    )  # fmt: skip
    monkeypatch.setattr(events, "fetch_calendar", lambda s, e: Result(df, source=events.SOURCE))
    out = bot.run_tool("get_calendar", {"start_date": "2026-10-05", "end_date": "2026-10-06"})
    assert out["total_matching"] == n
    assert out["shown"] == bot.MAX_CALENDAR_ROWS


def test_a_failed_data_source_becomes_an_error_payload(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: Result.fail("economy-intel is unreachable", "economy-intel"))
    out = bot.run_tool("us_series", {"series": "us_cpi"})
    assert out == {"error": "economy-intel is unreachable"}


def test_oversized_output_is_clipped_and_flagged():
    big = {"data": ["x" * 100] * 500}
    clipped = bot.clip(big)
    assert clipped["truncated"] is True
    assert len(json.dumps(clipped)) <= bot.MAX_TOOL_CHARS + 200


def test_small_output_is_untouched():
    small = {"a": 1}
    assert bot.clip(small) == small


# --- usage caps -----------------------------------------------------------------------------------


def make_limiter(day):
    return bot.UsageLimiter(session_cap=3, daily_cap=5, today=lambda: day[0])


def test_session_cap_blocks_the_next_message():
    day = [dt.date(2026, 10, 5)]
    limiter, session = make_limiter(day), {}
    assert [limiter.try_consume(session) for _ in range(3)] == [None, None, None]
    assert "session" in limiter.try_consume(session).lower()


def test_daily_cap_is_shared_across_sessions_and_resets_next_day():
    day = [dt.date(2026, 10, 5)]
    limiter = make_limiter(day)
    sessions = [{}, {}]
    assert limiter.try_consume(sessions[0]) is None
    assert limiter.try_consume(sessions[0]) is None
    assert limiter.try_consume(sessions[0]) is None
    assert limiter.try_consume(sessions[1]) is None
    assert limiter.try_consume(sessions[1]) is None
    assert "daily" in limiter.try_consume({}).lower()
    day[0] = dt.date(2026, 10, 6)
    assert limiter.try_consume({}) is None


def test_a_blocked_message_does_not_use_up_quota():
    day = [dt.date(2026, 10, 5)]
    limiter, session = make_limiter(day), {}
    for _ in range(3):
        limiter.try_consume(session)
    for _ in range(10):
        limiter.try_consume(session)
    assert limiter.used_today() == 3


# --- the conversation loop ----------------------------------------------------------------------------


def test_plain_answer_without_tools():
    a, client = analyst([reply(text="Hello")])
    ans = a.ask("hi", [], {})
    assert ans.text == "Hello"
    assert ans.tool_calls == []
    assert ans.error is None
    assert client.requests[0]["model"] == "test-model"


def test_a_tool_call_is_executed_fed_back_and_cited(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    a, client = analyst(
        [reply(calls=[("us_series", {"series": "us_unemployment_rate"})]), reply(text="It is 4.29% (us_series, BLS).")]
    )
    ans = a.ask("What is US unemployment?", [], {})
    assert ans.text.startswith("It is 4.29%")
    assert [(c.name, c.ok) for c in ans.tool_calls] == [("us_series", True)]
    assert ans.tool_calls[0].args == {"series": "us_unemployment_rate"}
    second_request = client.requests[1]["contents"]
    assert len(second_request) > len(client.requests[0]["contents"])  # tool result went back to the model


def test_a_failing_tool_is_reported_to_the_model_and_marked_not_ok(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: Result.fail("unreachable", "economy-intel"))
    a, _ = analyst([reply(calls=[("us_series", {"series": "us_cpi"})]), reply(text="Data is unavailable right now.")])
    ans = a.ask("CPI?", [], {})
    assert ans.text == "Data is unavailable right now."
    assert [(c.name, c.ok) for c in ans.tool_calls] == [("us_series", False)]


def test_an_invented_tool_from_the_model_is_rejected_and_the_loop_continues():
    a, _ = analyst([reply(calls=[("delete_everything", {})]), reply(text="I can't do that.")])
    ans = a.ask("do it", [], {})
    assert ans.text == "I can't do that."
    assert ans.tool_calls[0].ok is False


def test_endless_tool_calling_is_cut_off():
    steps = [reply(calls=[("us_series", {"series": "us_cpi"})]) for _ in range(bot.MAX_TOOL_ROUNDS + 3)]
    a, client = analyst(steps)
    ans = a.ask("loop forever", [], {})
    assert ans.error
    assert len(client.requests) <= bot.MAX_TOOL_ROUNDS + 1


def test_history_is_sent_as_alternating_roles():
    a, client = analyst([reply(text="ok")])
    history = [{"role": "user", "text": "first"}, {"role": "assistant", "text": "answer"}]
    a.ask("second", history, {})
    roles = [getattr(c, "role", None) for c in client.requests[0]["contents"]]
    assert roles == ["user", "model", "user"]


@pytest.mark.parametrize("question", ["", "   ", "x" * (bot.MAX_QUESTION_CHARS + 1)])
def test_empty_or_oversized_questions_never_reach_the_model_or_the_quota(question):
    a, client = analyst([])
    session = {}
    ans = a.ask(question, [], session)
    assert ans.error
    assert client.requests == []
    assert a.limiter.used_today() == 0


def test_a_reached_cap_stops_the_call_and_says_why():
    limiter = bot.UsageLimiter(session_cap=1, daily_cap=200, today=lambda: dt.date(2026, 10, 5))
    a, client = analyst([reply(text="one"), reply(text="two")], limiter=limiter)
    session = {}
    assert a.ask("q1", [], session).text == "one"
    blocked = a.ask("q2", [], session)
    assert blocked.error and "session" in blocked.error.lower()
    assert len(client.requests) == 1


def test_one_user_message_uses_one_unit_of_quota_however_many_tool_rounds(monkeypatch):
    monkeypatch.setattr(intel, "us_series", lambda s: series_result())
    a, _ = analyst([reply(calls=[("us_series", {"series": "us_cpi"})]), reply(calls=[("us_series", {"series": "us_ppi"})]), reply(text="done")])
    a.ask("both", [], {})
    assert a.limiter.used_today() == 1


class FakeApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@pytest.mark.parametrize("code", [400, 401, 403, 429, 500, 503])
def test_api_failures_become_a_safe_message_without_the_key(code):
    boom = FakeApiError(code, f"request to https://x?key={SECRET} failed")
    a, _ = analyst([boom])
    ans = a.ask("hello", [], {})
    assert ans.error
    assert SECRET not in ans.error
    assert "key=" not in ans.error


def test_quota_errors_get_a_friendly_message():
    a, _ = analyst([FakeApiError(429, "RESOURCE_EXHAUSTED")])
    assert "quota" in a.ask("hello", [], {}).error.lower()


def test_the_request_carries_the_system_prompt_and_all_tools():
    a, client = analyst([reply(text="ok")])
    a.ask("hello", [], {})
    config = client.requests[0]["config"]
    assert config.system_instruction == bot.SYSTEM_PROMPT
    declared = {fd.name for tool in config.tools for fd in tool.function_declarations}
    assert declared == {t.name for t in bot.tool_specs()}
    assert config.automatic_function_calling.disable is True


# --- wiring from secrets ----------------------------------------------------------------------------------


def test_available_follows_the_gemini_key(monkeypatch):
    assert bot.available() is False
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    assert bot.available() is True


def test_model_name_can_be_overridden(monkeypatch):
    assert bot.model_name() == bot.DEFAULT_MODEL
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom")
    assert bot.model_name() == "gemini-custom"


def test_default_limiter_uses_the_spec_caps():
    assert bot.SESSION_CAP == 15
    assert bot.DAILY_CAP == 200


def test_fred_tool_output_is_available_when_keyed(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "k")
    df = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=14, freq="MS"), "value": [4.0 + i / 10 for i in range(14)]})
    monkeypatch.setattr(fred, "fred_series", lambda s: Result(df, source=fred.SOURCE, as_of="2026-02-01", meta={"label": "Effective federal funds rate (%)"}))
    out = bot.run_tool("fred_series", {"series": "FEDFUNDS"})
    assert out["source"] == fred.SOURCE
    assert out["latest"]["value"] == pytest.approx(5.3)
