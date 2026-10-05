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
