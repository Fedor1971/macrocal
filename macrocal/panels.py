"""Reusable Streamlit panels. Kept out of app.py so they can be tested with AppTest."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from macrocal import intel
from macrocal.context import context_stats
from macrocal.mapping import series_for_event

PRIMARY = "#008D7F"


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


def render_event_context(name: str, currency: str | None) -> None:
    """Macro series behind a calendar event, or a clear note when there is none."""
    series = series_for_event(name, currency)
    if series is None:
        st.caption("No linked series for this event.")
        return

    result = intel.us_series(series)
    if not result.ok:
        st.warning(result.error or "No data came back for this series.")
        return

    stats = context_stats(result.data)
    st.markdown("#### Macro context")
    latest_col, prev_col, yoy_col = st.columns(3)
    delta = None if stats["change"] is None else f"{stats['change']:+,.2f}"
    latest_col.metric(f"Latest ({stats['latest_date']:%b %Y})", _fmt(stats["latest"]), delta=delta)
    prev_col.metric("Previous", _fmt(stats["previous"]))
    yoy = stats["yoy_pct"]
    yoy_col.metric("Year over year", "n/a" if yoy is None else f"{yoy:+.1f}%")

    fig = px.line(result.data, x="date", y="value", markers=True)
    fig.update_traces(line_color=PRIMARY)
    fig.update_layout(height=280, margin={"l": 0, "r": 0, "t": 10, "b": 0}, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, width="stretch")

    st.caption(
        f"{result.meta.get('label', series)} · source: {result.source} · as of {result.as_of}. "
        "Shows the series level; the event's headline figure may be a % change."
    )
