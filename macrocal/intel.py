"""Client for the hosted `economy-intel` MCP server (Datakoot): World Bank + US BLS/Census.

Wire format confirmed live on 2026-10-05: Streamable HTTP, JSON-RPC, replies are plain JSON
(SSE is parsed too, in case the host changes). The server is currently stateless (no
Mcp-Session-Id, a bogus id is accepted), but the handshake and session echo are kept so a
stateful host keeps working. Tool results arrive as a JSON string inside content[0].text;
values inside are strings, periods are month names, and a missing month is the string "-".

Third-party host, source not audited: send it nothing but series/country names.
"""

from __future__ import annotations

import itertools
import json
import re
import threading

import pandas as pd
import requests
import streamlit as st

from macrocal.result import Result

URL = "https://economy.datakoot.com/mcp"
SOURCE = "economy-intel"
PROTOCOL_VERSION = "2025-03-26"

US_SERIES = {
    "us_unemployment_rate": "US unemployment rate (%)",
    "us_cpi": "US CPI-U, all items (index)",
    "us_nonfarm_payrolls": "US total nonfarm payrolls (thousands)",
    "us_labor_participation": "US labor force participation rate (%)",
    "us_avg_hourly_earnings": "US avg hourly earnings, private (US$)",
    "us_ppi": "US PPI final demand, seasonally adjusted (index)",
    "us_retail_sales": "US advance retail & food services sales, SA (US$ millions)",
}

WB_INDICATORS = {
    "gdp": "GDP (current US$)",
    "gdp_per_capita": "GDP per capita (current US$)",
    "gdp_growth": "GDP growth (annual %)",
    "inflation": "Inflation, consumer prices (annual %)",
    "population": "Population, total",
    "unemployment": "Unemployment (% of labor force)",
    "life_expectancy": "Life expectancy at birth (years)",
    "exports": "Exports of goods & services (current US$)",
    "imports": "Imports of goods & services (current US$)",
    "govt_debt_pct_gdp": "Central govt debt (% of GDP)",
    "real_interest_rate": "Real interest rate (%)",
    "fdi": "Foreign direct investment, net inflows (US$)",
    "co2_per_capita": "CO2 emissions per capita (t)",
    "internet_users": "Individuals using the Internet (% pop)",
}  # a test pins this to the server's own list_indicators reply, so drift is noticed
WB_SOURCE = "World Bank (CC-BY 4.0)"
MAX_COUNTRIES = 10
_COUNTRY = re.compile(r"[A-Za-z][A-Za-z .'\-]{1,39}")  # ISO code or plain country name

# Series already measured in percent: a year-over-year move is shown in percentage points, not as
# a relative % change of a percentage (4.4% -> 4.2% is -0.2 pp, not "-4.5%").
RATE_SERIES = {"us_unemployment_rate", "us_labor_participation"}

_MONTHS = {
    name: i
    for i, name in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August",
         "September", "October", "November", "December"],
        start=1,
    )
}  # fmt: skip


class IntelError(Exception):
    """Anything that stops us getting a usable answer from economy-intel."""


# --- transport -----------------------------------------------------------------


def _post(body: dict, session_id: str | None) -> requests.Response:
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return requests.post(URL, json=body, headers=headers, timeout=30)


def parse_rpc_body(text: str, content_type: str) -> dict:
    """JSON-RPC message from a plain JSON or an SSE body (last `data:` event wins)."""
    try:
        if "text/event-stream" in (content_type or ""):
            events = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
            if not events:
                raise ValueError("no data events")
            return json.loads(events[-1])
        return json.loads(text)
    except ValueError as exc:
        raise IntelError(f"economy-intel sent an unreadable reply ({exc})") from exc


# --- session -------------------------------------------------------------------

_lock = threading.Lock()
_ids = itertools.count(1)
_state: dict = {"ready": False, "session_id": None}


def _reset_session() -> None:
    with _lock:
        _state.update(ready=False, session_id=None)


def _ensure_initialized() -> None:
    with _lock:
        if _state["ready"]:
            return
        init = _post(
            {
                "jsonrpc": "2.0",
                "id": next(_ids),
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "macrocal", "version": "1.0"},
                },
            },
            None,
        )
        if init.status_code != 200:
            raise IntelError(f"economy-intel initialize failed (HTTP {init.status_code})")
        session_id = init.headers.get("mcp-session-id")
        _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
        _state.update(ready=True, session_id=session_id)


def call_tool(name: str, arguments: dict) -> dict:
    """Call one tool and return its decoded JSON payload. Raises IntelError on any failure."""
    try:
        response = _call_with_one_retry(name, arguments)
    except requests.RequestException as exc:
        raise IntelError(f"economy-intel is unreachable ({type(exc).__name__})") from exc
    if response.status_code != 200:
        raise IntelError(f"economy-intel returned HTTP {response.status_code}")

    message = parse_rpc_body(response.text, response.headers.get("content-type", ""))
    if "error" in message:
        raise IntelError(str(message["error"].get("message", message["error"])))
    result = message.get("result") or {}
    try:
        payload = json.loads(result["content"][0]["text"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise IntelError("economy-intel sent an unexpected tool result") from exc
    if result.get("isError"):
        raise IntelError(str(payload.get("error", "tool error")) if isinstance(payload, dict) else "tool error")
    return payload


def _call_with_one_retry(name: str, arguments: dict) -> requests.Response:
    for attempt in (0, 1):
        _ensure_initialized()
        response = _post(
            {
                "jsonrpc": "2.0",
                "id": next(_ids),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            _state["session_id"],
        )
        if response.status_code == 404 and attempt == 0:  # session expired: handshake again
            _reset_session()
            continue
        return response
    return response  # pragma: no cover


# --- US series -----------------------------------------------------------------


def _clean(text: str) -> str:
    # The host sends U+FFFD where it meant a dash (seen in the Census source string).
    return text.replace("�", "-")


@st.cache_data(ttl=3600, show_spinner=False)
def _us_series_raw(series: str) -> dict:
    # Raises on failure so st.cache_data never caches an error.
    return call_tool("us_series", {"series": series})


def us_series(series: str) -> Result:
    """24 monthly points (ascending), missing months ("-") dropped."""
    if series not in US_SERIES:
        return Result.fail(f"Unknown series '{series}'. Choose from: {', '.join(US_SERIES)}", SOURCE)
    try:
        payload = _us_series_raw(series)
        frame = _series_frame(payload["data"])
    except (IntelError, KeyError, TypeError, ValueError) as exc:
        return Result.fail(f"Could not load {series}: {exc}", SOURCE)
    return Result(
        frame,
        source=_clean(payload.get("source", SOURCE)),
        as_of=payload.get("as_of", ""),
        meta={"label": payload.get("series", US_SERIES[series]), "series_id": payload.get("seriesID", "")},
    )


def _series_frame(points: list[dict]) -> pd.DataFrame:
    rows = [
        (pd.Timestamp(int(p["year"]), _MONTHS[p["period"]], 1), float(p["value"]))
        for p in points
        if p.get("value") not in (None, "", "-")
    ]
    return pd.DataFrame(rows, columns=["date", "value"]).sort_values("date").reset_index(drop=True)


# --- World Bank (annual, lagging; latest year may be provisional) -----------------


def _check_country(country: str) -> str | None:
    if not isinstance(country, str) or not _COUNTRY.fullmatch(country.strip()):
        return f"'{country}' is not a country code or name"
    return None


def _wb(tool: str, arguments: dict, build) -> Result:
    """Run a World Bank tool and shape the payload with `build(payload) -> (frame, meta)`."""
    try:
        payload = _wb_raw(tool, json.dumps(arguments, sort_keys=True))
        frame, meta = build(payload)
    except (IntelError, KeyError, TypeError, ValueError) as exc:
        return Result.fail(f"Could not load {tool}: {exc}", SOURCE)
    return Result(frame, source=_clean(payload.get("source", WB_SOURCE)), meta=meta)


@st.cache_data(ttl=3600, show_spinner=False)
def _wb_raw(tool: str, arguments_json: str) -> dict:
    # Raises on failure so st.cache_data never caches an error.
    return call_tool(tool, json.loads(arguments_json))


def country_profile(country: str) -> Result:
    """Latest value of each headline indicator for one country."""
    if (problem := _check_country(country)) is not None:
        return Result.fail(problem, SOURCE)

    def build(payload: dict):
        rows = [
            (key, item["label"], int(item["year"]), float(item["value"]))
            for key, item in payload["latest"].items()
            if item.get("value") is not None
        ]
        return pd.DataFrame(rows, columns=["key", "label", "year", "value"]), {
            "country": payload.get("country", country)
        }

    return _wb("country_profile", {"country": country.strip()}, build)


def country_indicator(country: str, indicator: str, years: int = 12) -> Result:
    """One indicator over time for one country, ascending by year."""
    if (problem := _check_country(country)) is not None:
        return Result.fail(problem, SOURCE)
    if indicator not in WB_INDICATORS:
        return Result.fail(f"Unknown indicator '{indicator}'", SOURCE)
    if not 1 <= years <= 60:
        return Result.fail("years must be between 1 and 60", SOURCE)

    def build(payload: dict):
        rows = [
            (int(p["year"]), float(p["value"])) for p in payload["series"] if p.get("value") is not None
        ]
        frame = pd.DataFrame(rows, columns=["year", "value"]).sort_values("year").reset_index(drop=True)
        return frame, {"label": payload.get("indicator", WB_INDICATORS[indicator]),
                       "country": payload.get("country", country)}  # fmt: skip

    return _wb("country_indicator", {"country": country.strip(), "indicator": indicator, "years": years}, build)


def compare_countries(indicator: str, countries: list[str]) -> Result:
    """One indicator across countries, in the server's ranking order (highest first)."""
    if indicator not in WB_INDICATORS:
        return Result.fail(f"Unknown indicator '{indicator}'", SOURCE)
    if not 1 <= len(countries) <= MAX_COUNTRIES:
        return Result.fail(f"Choose between 1 and {MAX_COUNTRIES} countries", SOURCE)
    for country in countries:
        if (problem := _check_country(country)) is not None:
            return Result.fail(problem, SOURCE)

    def build(payload: dict):
        rows = [
            (r["country"], int(r["year"]), float(r["value"]))
            for r in payload["ranking"]
            if r.get("value") is not None
        ]
        return pd.DataFrame(rows, columns=["country", "year", "value"]), {
            "label": payload.get("indicator", WB_INDICATORS[indicator])
        }

    return _wb("compare_countries", {"indicator": indicator, "countries": [c.strip() for c in countries]}, build)
