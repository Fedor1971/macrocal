"""Optional FRED (St. Louis Fed) series. Enabled only when FRED_API_KEY is set.

Security: requests puts the full URL, `api_key` included, into its exception text, so error
messages here are built from the exception *type* and HTTP status only, never from `str(exc)`
or the response body. A test fails if the key ever shows up in an error.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import requests
import streamlit as st

from macrocal.config import get_secret
from macrocal.result import Result

URL = "https://api.stlouisfed.org/fred/series/observations"
SOURCE = "FRED, Federal Reserve Bank of St. Louis"
LOOKBACK_DAYS = 3650

SERIES = {
    "FEDFUNDS": "Effective federal funds rate (%)",
    "GS10": "10-year Treasury yield (%)",
    "T10Y2Y": "10-year minus 2-year Treasury spread (percentage points)",
    "GDPC1": "Real GDP, quarterly (billions of chained dollars)",
}
# Daily series are averaged to monthly so the chart and the "previous" comparison stay meaningful.
_FREQUENCY = {"T10Y2Y": "m"}


class FredError(Exception):
    """A failure whose message is safe to show (it never contains the API key)."""


def available() -> bool:
    return get_secret("FRED_API_KEY") is not None


@st.cache_data(ttl=3600, show_spinner=False)
def _observations(series_id: str) -> list[dict]:
    # Raises on failure so st.cache_data never caches an error. The key is read here, not
    # passed in, so it is never part of a cache key or a call signature.
    key = get_secret("FRED_API_KEY")
    if key is None:
        raise FredError("FRED_API_KEY is not set")
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "observation_start": (dt.date.today() - dt.timedelta(days=LOOKBACK_DAYS)).isoformat(),  # noqa: DTZ011
    }
    if series_id in _FREQUENCY:
        params["frequency"] = _FREQUENCY[series_id]
    try:
        response = requests.get(URL, params=params, timeout=15)
    except requests.RequestException as exc:
        raise FredError(f"FRED is unreachable ({type(exc).__name__})") from None
    if response.status_code != 200:
        raise FredError(f"FRED returned HTTP {response.status_code}")
    try:
        return response.json()["observations"]
    except (ValueError, KeyError, TypeError):
        raise FredError("FRED sent an unreadable reply") from None


def fred_series(series_id: str) -> Result:
    if series_id not in SERIES:
        return Result.fail(f"Unknown FRED series '{series_id}'. Choose from: {', '.join(SERIES)}", SOURCE)
    try:
        observations = _observations(series_id)
    except FredError as exc:
        return Result.fail(str(exc), SOURCE)
    rows = [(o["date"], o["value"]) for o in observations if o.get("value") not in (None, "", ".")]
    if not rows:
        return Result.fail(f"FRED returned no observations for {series_id}", SOURCE)
    frame = pd.DataFrame(rows, columns=["date", "value"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna().sort_values("date").reset_index(drop=True)
    return Result(
        frame,
        source=SOURCE,
        as_of=frame["date"].iloc[-1].date().isoformat(),
        meta={"label": SERIES[series_id], "series_id": series_id},
    )
