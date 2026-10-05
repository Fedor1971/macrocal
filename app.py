"""MacroCal: economic calendar + macro data + markets + AI analyst."""

from __future__ import annotations

import datetime as dt

import streamlit as st

import style
from macrocal import events

st.set_page_config(page_title="MacroCal", page_icon="📈", layout="wide")
style.inject(st)
st.markdown('<div class="eu-title">MacroCal</div>', unsafe_allow_html=True)

# Impact cell colours, from the Euronext palette (strongest = darkest teal).
IMPACT_STYLE = {
    "HIGH": f"background-color:{style.PALETTE['dark']};color:#fff;font-weight:600",
    "MEDIUM": f"background-color:{style.PALETTE['tint']};color:{style.PALETTE['dark']};font-weight:600",
    "LOW": f"background-color:{style.PALETTE['panel']};color:{style.PALETTE['text']}",
}

today = dt.date.today()  # noqa: DTZ011 - local date is right for a date picker default
with st.sidebar:
    st.header("Filters")
    date_range = st.date_input("Date range", value=(today, today + dt.timedelta(days=7)))

tab_calendar, tab_macro, tab_markets, tab_ask = st.tabs(["Calendar", "Macro", "Markets", "Ask"])


def render_event_details(event_id: str, name: str) -> None:
    st.subheader(name)
    details = events.fetch_event_details(event_id)
    if not details.ok:
        st.error(details.error)
        return
    d = details.data
    col1, col2, col3 = st.columns(3)
    col1.metric("Actual", d.get("actual"))
    col2.metric("Consensus", d.get("consensus"))
    col3.metric("Previous", d.get("previous"))
    st.write(f"**Country:** {d.get('countryCode', 'n/a')}")
    st.write(f"**Category:** {(d.get('category') or {}).get('name', 'n/a')}")
    st.write(f"**Source:** {d.get('source', 'n/a')}")
    description = events.clean_description(d.get("description"))
    if description:
        st.write(description)


def render_calendar_tab() -> None:
    if len(date_range) != 2:
        st.info("Pick an end date to load the calendar.")
        return
    start_date, end_date = date_range
    result = events.fetch_calendar(start_date.isoformat(), end_date.isoformat())
    if not result.ok:
        st.error(result.error or "No events in this date range.")
        return
    calendar_df = result.data

    with st.sidebar:
        impact_options = sorted(calendar_df["Impact"].dropna().unique())
        impacts = st.multiselect("Impact", impact_options, default=impact_options)
        currency_options = sorted(calendar_df["Currency"].dropna().unique())
        currencies = st.multiselect("Currency", currency_options, default=currency_options)

    filtered = events.filter_events(calendar_df, impacts, currencies)
    st.caption(
        f"{len(filtered)} of {len(calendar_df)} events · source: {result.source} · {result.as_of}"
    )

    display = filtered[["Start", "Name", "Impact", "Currency"]]
    selection = st.dataframe(
        display.style.map(lambda v: IMPACT_STYLE.get(v, ""), subset=["Impact"]),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )
    st.download_button(
        "Export filtered view to CSV",
        data=display.to_csv(index=False).encode("utf-8"),
        file_name=f"macrocal_calendar_{start_date}_{end_date}.csv",
        mime="text/csv",
    )

    rows = selection.selection.rows if selection and selection.selection else []
    if rows:
        row = filtered.iloc[rows[0]]
        render_event_details(row["Id"], row["Name"])
    else:
        st.info("Select a row in the table to see its details.")


with tab_calendar:
    render_calendar_tab()
with tab_macro:
    st.info("Macro: coming later.")
with tab_markets:
    st.info("Markets: coming later.")
with tab_ask:
    st.info("Ask: coming later.")
