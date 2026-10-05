"""Small pure helpers that turn a monthly series into the numbers shown next to an event."""

from __future__ import annotations

import pandas as pd


def context_stats(df: pd.DataFrame) -> dict:
    """Latest vs previous available point, plus year-over-year when the year-ago month exists.

    `df` has ascending `date` (month start) and `value` columns. "Previous" is the prior
    available point, so a gap month (the "-" the source sends) does not break the comparison.
    """
    latest_row = df.iloc[-1]
    latest = float(latest_row["value"])
    stats: dict = {
        "latest": latest,
        "latest_date": latest_row["date"],
        "previous": None,
        "change": None,
        "pct_change": None,
        "yoy_pct": None,
    }
    if len(df) >= 2:
        previous = float(df.iloc[-2]["value"])
        stats["previous"] = previous
        stats["change"] = latest - previous
        if previous != 0:
            stats["pct_change"] = (latest - previous) / abs(previous) * 100

    year_ago = df[df["date"] == latest_row["date"] - pd.DateOffset(years=1)]
    if not year_ago.empty:
        base = float(year_ago.iloc[0]["value"])
        if base != 0:
            stats["yoy_pct"] = (latest - base) / abs(base) * 100
    return stats
