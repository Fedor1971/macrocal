"""Reusable Streamlit panels. Kept out of app.py so they can be tested with AppTest."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from macrocal import fred, intel
from macrocal.context import context_stats
from macrocal.mapping import series_for_event

PRIMARY = "#008D7F"
_MARGIN = {"l": 0, "r": 0, "t": 10, "b": 0}

# Euronext home markets first, then the big economies people ask about.
COUNTRY_CHOICES = {
    "NLD": "Netherlands", "FRA": "France", "BEL": "Belgium", "PRT": "Portugal",
    "IRL": "Ireland", "ITA": "Italy", "NOR": "Norway", "DEU": "Germany",
    "ESP": "Spain", "GBR": "United Kingdom", "CHE": "Switzerland", "SWE": "Sweden",
    "USA": "United States", "JPN": "Japan", "CHN": "China",
}  # fmt: skip


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    # Metric cards truncate long text ("159,04..."), so large levels drop their decimals.
    return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:,.2f}"


def _fmt_delta(change: float | None, level: float) -> str | None:
    if change is None:
        return None
    return f"{change:+,.0f}" if abs(level) >= 1000 else f"{change:+,.2f}"


def _compact(value: float) -> str:
    """1.33e12 -> '1.33T'. Short enough for a metric card."""
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= limit:
            return f"{value / limit:,.2f}{suffix}"
    return _fmt(value)


def _render_result(result, fallback_label: str, note: str = "", show_yoy: bool = True) -> None:
    """Latest/previous/YoY cards, chart and provenance for any monthly-ish series Result."""
    if not result.ok:
        st.warning(result.error or "No data came back for this series.")
        return

    stats = context_stats(result.data)
    columns = st.columns(3 if show_yoy else 2)
    delta = _fmt_delta(stats["change"], stats["latest"])
    columns[0].metric(f"Latest ({stats['latest_date']:%b %Y})", _fmt(stats["latest"]), delta=delta)
    columns[1].metric("Previous", _fmt(stats["previous"]))
    if show_yoy:
        yoy = stats["yoy_pct"]
        columns[2].metric("Year over year", "n/a" if yoy is None else f"{yoy:+.1f}%")

    fig = px.line(result.data, x="date", y="value", markers=True)
    fig.update_traces(line_color=PRIMARY)
    fig.update_layout(height=280, margin=_MARGIN, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, width="stretch")

    st.caption(
        f"{result.meta.get('label', fallback_label)} · source: {result.source} · "
        f"as of {result.as_of}. {note}".strip()
    )


def _render_series(series: str, note: str = "") -> None:
    _render_result(intel.us_series(series), series, note)


def render_event_context(name: str, currency: str | None) -> None:
    """Macro series behind a calendar event, or a clear note when there is none."""
    series = series_for_event(name, currency)
    if series is None:
        st.caption("No linked series for this event.")
        return
    st.markdown("#### Macro context")
    _render_series(series, note="Shows the series level; the event's headline figure may be a % change.")


def _render_country_compare(indicator: str, countries: list[str]) -> None:
    result = intel.compare_countries(indicator, countries)
    if not result.ok:
        st.warning(result.error or "No data came back for this comparison.")
        return
    fig = px.bar(result.data.iloc[::-1], x="value", y="country", orientation="h", text="value")
    fig.update_traces(marker_color=PRIMARY, texttemplate="%{text:,.2f}")
    fig.update_layout(height=60 + 40 * len(result.data), margin=_MARGIN, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, width="stretch")
    years = ", ".join(str(y) for y in sorted(result.data["year"].unique()))
    st.caption(
        f"{result.meta.get('label', indicator)} · source: {result.source} · latest year per country "
        f"({years}); the newest World Bank year can be provisional."
    )


def _render_country_profile(country: str) -> None:
    result = intel.country_profile(country)
    if not result.ok:
        st.warning(result.error or "No profile came back for this country.")
        return
    st.markdown(f"#### {result.meta.get('country', country)}")
    rows = list(result.data.itertuples())
    for start in range(0, len(rows), 3):
        for col, row in zip(st.columns(3), rows[start : start + 3], strict=False):
            col.metric(row.label, _compact(row.value), help=f"Year {row.year}")
    st.caption(f"source: {result.source} · annual data, years differ by indicator.")


def render_macro_tab() -> None:
    st.subheader("United States (monthly)")
    series = st.selectbox(
        "Series", list(intel.US_SERIES), format_func=intel.US_SERIES.get, key="us_series_pick"
    )
    _render_series(series)

    st.divider()
    st.subheader("Countries (World Bank, annual)")
    indicators = list(intel.WB_INDICATORS)
    left, right = st.columns([1, 2])
    indicator = left.selectbox(
        "Indicator",
        indicators,
        index=indicators.index("unemployment"),
        format_func=intel.WB_INDICATORS.get,
        key="wb_indicator",
    )
    countries = right.multiselect(
        "Countries",
        list(COUNTRY_CHOICES),
        default=["NLD", "DEU", "FRA"],
        format_func=COUNTRY_CHOICES.get,
        max_selections=intel.MAX_COUNTRIES,
        key="wb_countries",
    )
    if not countries:
        st.info("Pick at least one country.")
        return
    _render_country_compare(indicator, countries)

    profile_country = st.selectbox(
        "Country profile", countries, format_func=COUNTRY_CHOICES.get, key="wb_profile_country"
    )
    _render_country_profile(profile_country)

    st.divider()
    _render_fred_section()


def _render_fred_section() -> None:
    st.subheader("Rates and output (FRED)")
    if not fred.available():
        st.caption("Hidden: add a free FRED_API_KEY in the app secrets to enable this section.")
        return
    series = st.selectbox("FRED series", list(fred.SERIES), format_func=fred.SERIES.get, key="fred_series_pick")
    # YoY % change of a rate or a spread is not meaningful, so only level and change are shown.
    _render_result(fred.fred_series(series), series, show_yoy=False)
