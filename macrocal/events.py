"""Economic-calendar data layer on top of the vendored ecocal package.

ecocal facts, confirmed live while building ecocal-dashboard (not from its README):
- getCalendar(withDetails=False) returns Id, Start (MM/DD/YYYY HH:MM:SS string), Name,
  Impact (LOW/MEDIUM/HIGH/NONE) and Currency. There is no Country column.
- Country only exists in a single event's detail payload (countryCode).
- Per-event details are one HTTP request each, so they are fetched on demand only.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import sys
from pathlib import Path

import numpy as np

# Vendored ecocal (MIT). Appended last, so a pip-installed ecocal (run.bat path) wins.
sys.path.append(str(Path(__file__).resolve().parent.parent / "vendor"))

# ecocal calls numpy.NaN, removed in NumPy 2.0. Same value as numpy.nan.
np.NaN = np.nan

import pandas as pd
import requests
import streamlit as st
from ecocal import Calendar
from ecocal.constants import API_SOURCE_URL, BASE_URL, DEFAULT_USER_AGENT

from macrocal.result import Result

SOURCE = "fxstreet (via ecocal)"
MAX_RANGE_DAYS = 31  # a public app must not let anyone ask fxstreet for years of events
BASIC_COLUMNS = ["Id", "Start", "Name", "Impact", "Currency"]


def shape_calendar(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=BASIC_COLUMNS)
    df = raw.copy()
    df["Start"] = pd.to_datetime(df["Start"], format="%m/%d/%Y %H:%M:%S")
    return df.sort_values("Start").reset_index(drop=True)


def filter_events(df: pd.DataFrame, impacts: list[str], currencies: list[str]) -> pd.DataFrame:
    return df[df["Impact"].isin(impacts) & df["Currency"].isin(currencies)]


_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


def clean_description(raw_html: str | None) -> str:
    """Event descriptions are third-party HTML. Show them as plain text, never as markup."""
    if not raw_html:
        return ""
    text = _SCRIPT_STYLE.sub("", raw_html)
    text = _TAGS.sub(" ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


@st.cache_data(ttl=600, max_entries=32, show_spinner="Fetching economic calendar...")
def _fetch_calendar_raw(start_date: str, end_date: str) -> pd.DataFrame:
    # Raises on failure so st.cache_data never caches an error.
    cal = Calendar(
        startHorizon=start_date,
        endHorizon=end_date,
        withDetails=False,
        withProgressBar=False,
        nbThreads=10,
    )
    return cal.getCalendar(withDetails=False).copy()


def fetch_calendar(start_date: str, end_date: str) -> Result:
    """Basic calendar for a date range (YYYY-MM-DD strings), at most MAX_RANGE_DAYS long."""
    try:
        start, end = dt.date.fromisoformat(start_date), dt.date.fromisoformat(end_date)
    except ValueError:
        return Result.fail("Dates must look like 2026-10-05", SOURCE)
    if start > end:
        return Result.fail("The start date must not be after the end date", SOURCE)
    if (end - start).days > MAX_RANGE_DAYS:
        return Result.fail(f"Choose a range of at most {MAX_RANGE_DAYS} days", SOURCE)
    try:
        df = shape_calendar(_fetch_calendar_raw(start_date, end_date))
    except Exception as exc:  # noqa: BLE001 - shown to the user via Result.error
        return Result.fail(f"Could not fetch the calendar: {exc}", SOURCE)
    return Result(df, source=SOURCE, as_of=f"{start_date} to {end_date}")


@st.cache_data(ttl=600, max_entries=256, show_spinner="Fetching event details...")
def _fetch_event_details_raw(event_id: str) -> dict:
    # Uses ecocal's public constants, not its private Calendar._requestDetails.
    response = requests.get(
        url=f"{API_SOURCE_URL}/{event_id}",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": BASE_URL,
            "Connection": "keep-alive",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def fetch_event_details(event_id: str) -> Result:
    try:
        payload = _fetch_event_details_raw(event_id)
    except Exception as exc:  # noqa: BLE001 - shown to the user via Result.error
        return Result.fail(f"Could not fetch details for this event: {exc}", SOURCE)
    return Result(payload, source=SOURCE)
