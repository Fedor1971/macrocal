"""Market prices from Yahoo Finance (unofficial `yfinance` API) plus the maths on top.

Yahoo can change or rate-limit without notice (same fragility class as the fxstreet calendar),
so every failure becomes a Result and the rest of the app keeps working. Error messages carry
only the exception type, never its text.

yfinance 1.7 shape, confirmed live 2026-10-05: columns are a (Price, Ticker) MultiIndex even
for one ticker, and an unknown ticker comes back as an all-NaN column plus stderr noise.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import streamlit as st

from macrocal.result import Result

SOURCE = "Yahoo Finance via yfinance (unofficial, may be delayed or break)"
MAX_YEARS = 20
MIN_OVERLAP = 20  # trading days needed before a correlation is shown

# key -> (Yahoo symbol, label)
ASSETS = {
    "sp500": ("^GSPC", "S&P 500"),
    "bond10y": ("^TNX", "US 10-year yield (%)"),
    "gold": ("GC=F", "Gold futures"),
    "oil": ("CL=F", "WTI crude oil futures"),
    "eurusd": ("EURUSD=X", "EUR/USD"),
    "reit_etf": ("VNQ", "US real estate ETF (VNQ)"),
}
# Inclusive windows around each episode (start of stress through the trough/recovery leg).
CRISIS_WINDOWS = {
    "Global financial crisis 2008": ("2007-10-01", "2009-03-31"),
    "COVID-19 crash 2020": ("2020-02-01", "2020-06-30"),
    "2022 inflation shock": ("2022-01-01", "2022-12-31"),
}
PRESETS = ["Last 1 year", "Last 5 years", *CRISIS_WINDOWS]
_YIELD_KEYS = {"bond10y"}  # a % change of a rate is meaningless, so these use level changes


class MarketsError(Exception):
    pass


def preset_window(name: str, today: dt.date) -> tuple[str, str]:
    if name in CRISIS_WINDOWS:
        return CRISIS_WINDOWS[name]
    years = {"Last 1 year": 1, "Last 5 years": 5}.get(name)
    if years is None:
        raise ValueError(f"Unknown preset '{name}'")
    start = (pd.Timestamp(today) - pd.DateOffset(years=years)).date()
    return start.isoformat(), today.isoformat()


@st.cache_data(ttl=3600, show_spinner="Fetching market prices...")
def _download(symbols: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    # Raises on failure so st.cache_data never caches an error.
    import yfinance as yf  # lazy: slow to import, only needed by this view

    raw = yf.download(list(symbols), start=start, end=end, auto_adjust=True, progress=False)
    return extract_close(raw)


def extract_close(raw: pd.DataFrame | None) -> pd.DataFrame:
    """Close prices, one column per Yahoo symbol, from a yfinance (Price, Ticker) frame."""
    if raw is None or raw.empty:
        raise MarketsError("Yahoo Finance returned no data")
    try:
        return raw["Close"]
    except KeyError:
        raise MarketsError("Yahoo Finance reply had no closing prices") from None


def _validate(keys: list[str], start: str, end: str) -> tuple[dt.date, dt.date]:
    if not keys:
        raise MarketsError("Pick at least one asset")
    unknown = [k for k in keys if k not in ASSETS]
    if unknown:
        raise MarketsError(f"Unknown asset: {', '.join(unknown)}")
    try:
        start_d, end_d = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    except ValueError:
        raise MarketsError("Dates must look like 2026-01-31") from None
    if start_d >= end_d:
        raise MarketsError("The start date must be before the end date")
    if (end_d - start_d).days > MAX_YEARS * 366:
        raise MarketsError(f"Choose a window of at most {MAX_YEARS} years")
    return start_d, end_d


def fetch_prices(keys: list[str], start: str, end: str) -> Result:
    """Daily closes (adjusted), one column per asset key, plus a `date` column."""
    try:
        _, end_d = _validate(keys, start, end)
        symbols = tuple(ASSETS[k][0] for k in keys)
        close = _download(symbols, start, (end_d + dt.timedelta(days=1)).isoformat())
    except MarketsError as exc:
        return Result.fail(str(exc), SOURCE)
    except Exception as exc:  # noqa: BLE001 - never show library text, only the type
        return Result.fail(f"Yahoo Finance request failed ({type(exc).__name__})", SOURCE)

    columns, missing = {}, []
    for key in keys:
        symbol = ASSETS[key][0]
        if symbol in close.columns and close[symbol].notna().any():
            columns[key] = close[symbol]
        else:
            missing.append(key)
    if not columns:
        return Result.fail("Yahoo Finance had no data for the chosen assets and dates", SOURCE)

    frame = pd.DataFrame(columns).dropna(how="all")
    index = pd.to_datetime(frame.index)
    frame.index = index.tz_localize(None) if index.tz is not None else index
    frame.index.name = "date"
    frame = frame.sort_index().reset_index()
    return Result(
        frame,
        source=SOURCE,
        as_of=frame["date"].iloc[-1].date().isoformat(),
        meta={"missing": missing, "labels": {k: ASSETS[k][1] for k in columns}},
    )


def normalise(prices: pd.DataFrame) -> pd.DataFrame:
    """Rebase every asset to 100 at its own first available value."""
    values = prices.set_index("date")
    first = values.apply(lambda col: col.dropna().iloc[0] if col.notna().any() else np.nan)
    return (values / first * 100).reset_index()


def returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily % change; for yield series the daily change in percentage points."""
    values = prices.set_index("date")
    out = values.pct_change(fill_method=None) * 100
    for key in _YIELD_KEYS & set(values.columns):
        out[key] = values[key].diff()
    return out.iloc[1:].reset_index()


def correlation(prices: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation of daily returns; NaN when too few overlapping days."""
    return returns(prices).drop(columns="date").corr(min_periods=MIN_OVERLAP)
