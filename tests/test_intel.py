import json
from pathlib import Path

import pandas as pd
import pytest

from macrocal import intel

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResp:
    def __init__(self, text="", status=200, headers=None):
        self.text = text
        self.status_code = status
        self.headers = headers or {"content-type": "application/json"}


INIT_OK = json.dumps(
    {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26", "capabilities": {}}}
)


class FakeServer:
    """Stands in for intel._post. Records requests; replies from a script keyed by method/tool."""

    def __init__(self, tool_reply: str, session_id: str | None = None):
        self.tool_reply = tool_reply
        self.session_id = session_id
        self.calls: list[tuple[dict, str | None]] = []

    def __call__(self, body, session_id):
        self.calls.append((body, session_id))
        method = body.get("method")
        if method == "initialize":
            headers = {"content-type": "application/json"}
            if self.session_id:
                headers["mcp-session-id"] = self.session_id
            return FakeResp(INIT_OK, headers=headers)
        if method == "notifications/initialized":
            return FakeResp("", status=202)
        return FakeResp(self.tool_reply)


@pytest.fixture(autouse=True)
def fresh_client():
    intel._reset_session()
    yield
    intel._reset_session()


# --- wire format -------------------------------------------------------------


def test_parse_response_plain_json():
    payload = intel.parse_rpc_body('{"jsonrpc":"2.0","id":1,"result":{"x":1}}', "application/json")
    assert payload["result"]["x"] == 1


def test_parse_response_sse_takes_last_data_event():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"x":2}}\n\n'
    payload = intel.parse_rpc_body(body, "text/event-stream")
    assert payload["result"]["x"] == 2


def test_parse_response_garbage_raises_intel_error():
    with pytest.raises(intel.IntelError):
        intel.parse_rpc_body("<html>502</html>", "text/html")


# --- call_tool ----------------------------------------------------------------


def test_call_tool_returns_inner_json_payload(monkeypatch):
    server = FakeServer(fixture_text("country_profile.json"))
    monkeypatch.setattr(intel, "_post", server)
    out = intel.call_tool("country_profile", {"country": "NLD"})
    assert out["country"] == "Netherlands"
    assert out["latest"]["unemployment"]["value"] == 3.874


def test_call_tool_is_error_raises_with_server_message(monkeypatch):
    monkeypatch.setattr(intel, "_post", FakeServer(fixture_text("tool_error.json")))
    with pytest.raises(intel.IntelError, match="No data for country 'ZZZ'"):
        intel.call_tool("country_profile", {"country": "ZZZ"})


def test_call_tool_does_handshake_once_and_echoes_session_id(monkeypatch):
    server = FakeServer(fixture_text("country_profile.json"), session_id="sess-1")
    monkeypatch.setattr(intel, "_post", server)
    intel.call_tool("country_profile", {"country": "NLD"})
    intel.call_tool("country_profile", {"country": "DEU"})
    methods = [b.get("method") for b, _ in server.calls]
    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/call",
        "tools/call",
    ]
    assert server.calls[-1][1] == "sess-1"


def test_call_tool_works_with_stateless_server_that_sends_no_session_id(monkeypatch):
    server = FakeServer(fixture_text("country_profile.json"), session_id=None)
    monkeypatch.setattr(intel, "_post", server)
    assert intel.call_tool("country_profile", {"country": "NLD"})["country"] == "Netherlands"
    assert server.calls[-1][1] is None


def test_call_tool_reinitialises_once_when_session_expired(monkeypatch):
    replies = {"n": 0}

    def post(body, session_id):
        method = body.get("method")
        if method == "initialize":
            return FakeResp(INIT_OK, headers={"content-type": "application/json", "mcp-session-id": "s"})
        if method == "notifications/initialized":
            return FakeResp("", status=202)
        replies["n"] += 1
        if replies["n"] == 1:
            return FakeResp("session not found", status=404, headers={})
        return FakeResp(fixture_text("country_profile.json"))

    monkeypatch.setattr(intel, "_post", post)
    assert intel.call_tool("country_profile", {"country": "NLD"})["country"] == "Netherlands"
    assert replies["n"] == 2


def test_call_tool_http_error_raises(monkeypatch):
    def post(body, session_id):
        if body.get("method") == "initialize":
            return FakeResp(INIT_OK)
        if body.get("method") == "notifications/initialized":
            return FakeResp("", status=202)
        return FakeResp("bad gateway", status=502, headers={})

    monkeypatch.setattr(intel, "_post", post)
    with pytest.raises(intel.IntelError, match="502"):
        intel.call_tool("us_series", {"series": "us_cpi"})


# --- us_series ----------------------------------------------------------------


def test_us_series_frame_is_ascending_monthly_floats_without_dash_gaps(monkeypatch):
    monkeypatch.setattr(intel, "_post", FakeServer(fixture_text("us_series_cpi.json")))
    r = intel.us_series("us_cpi")
    assert r.ok
    df = r.data
    assert list(df.columns) == ["date", "value"]
    assert df["date"].is_monotonic_increasing
    assert df["date"].iloc[-1] == pd.Timestamp("2026-08-01")
    assert df["value"].iloc[-1] == pytest.approx(334.98)
    assert len(df) == 23  # 24 points, one "-" (Oct 2025 gap) dropped
    assert df["date"].dt.day.eq(1).all()


def test_us_series_carries_provenance(monkeypatch):
    monkeypatch.setattr(intel, "_post", FakeServer(fixture_text("us_series_unrate.json")))
    r = intel.us_series("us_unemployment_rate")
    assert r.as_of == "2026-10-05"
    assert "Bureau of Labor Statistics" in r.source
    assert r.meta["label"] == "US unemployment rate (%)"


def test_us_series_rejects_unknown_series_without_calling_server(monkeypatch):
    server = FakeServer("{}")
    monkeypatch.setattr(intel, "_post", server)
    r = intel.us_series("us_gdp_nowcast")
    assert not r.ok
    assert "Unknown series" in r.error
    assert server.calls == []


def test_us_series_wraps_server_failure_in_result(monkeypatch):
    monkeypatch.setattr(intel, "_post", FakeServer(fixture_text("tool_error.json")))
    r = intel.us_series("us_cpi")
    assert not r.ok
    assert r.source == "economy-intel"


# --- World Bank tools ------------------------------------------------------------


def test_wb_indicator_constant_matches_what_the_server_lists():
    listed = json.loads(
        json.loads(fixture_text("list_indicators.json"))["result"]["content"][0]["text"]
    )["world_bank"]
    assert intel.WB_INDICATORS == listed  # drift here means the server added/renamed indicators


def test_country_profile_frame_has_one_row_per_indicator(monkeypatch):
    monkeypatch.setattr(intel, "_post", FakeServer(fixture_text("country_profile.json")))
    r = intel.country_profile("NLD")
    assert r.ok
    assert list(r.data.columns) == ["key", "label", "year", "value"]
    row = r.data.set_index("key").loc["unemployment"]
    assert row["value"] == pytest.approx(3.874)
    assert row["year"] == 2025
    assert r.meta["country"] == "Netherlands"
    assert r.source == "World Bank (CC-BY 4.0)"


def test_country_indicator_series_is_ascending_by_year(monkeypatch):
    monkeypatch.setattr(intel, "_post", FakeServer(fixture_text("country_indicator.json")))
    r = intel.country_indicator("NLD", "inflation", years=3)
    assert r.ok
    assert list(r.data["year"]) == [2023, 2024, 2025]
    assert r.data["value"].iloc[-1] == pytest.approx(3.2595766)
    assert r.meta["label"].startswith("Inflation")


def test_compare_countries_keeps_server_ranking_order(monkeypatch):
    monkeypatch.setattr(intel, "_post", FakeServer(fixture_text("compare_countries.json")))
    r = intel.compare_countries("unemployment", ["NLD", "DEU", "FRA"])
    assert r.ok
    assert list(r.data["country"]) == ["France", "Netherlands", "Germany"]
    assert r.data["value"].iloc[0] == pytest.approx(7.542)
    assert r.meta["label"].startswith("Unemployment")


@pytest.mark.parametrize(
    "call",
    [
        lambda: intel.country_indicator("NLD", "made_up_indicator"),
        lambda: intel.compare_countries("made_up_indicator", ["NLD"]),
        lambda: intel.compare_countries("gdp", []),
        lambda: intel.compare_countries("gdp", ["NLD"] * 11),
        lambda: intel.country_profile("NLD; DROP TABLE"),
        lambda: intel.country_profile(""),
        lambda: intel.country_indicator("NLD", "gdp", years=0),
        lambda: intel.country_indicator("NLD", "gdp", years=500),
    ],
)
def test_world_bank_loaders_reject_bad_arguments_without_calling_the_server(monkeypatch, call):
    server = FakeServer("{}")
    monkeypatch.setattr(intel, "_post", server)
    r = call()
    assert not r.ok
    assert r.error
    assert server.calls == []


def test_world_bank_loaders_wrap_server_errors(monkeypatch):
    monkeypatch.setattr(intel, "_post", FakeServer(fixture_text("tool_error.json")))
    r = intel.country_profile("ZZZ")
    assert not r.ok
    assert "No data for country" in r.error
