"""MacroCal: economic calendar + macro data + markets + AI analyst."""

from __future__ import annotations

import streamlit as st

import style

st.set_page_config(page_title="MacroCal", page_icon="📈", layout="wide")
style.inject(st)

st.markdown('<div class="eu-title">MacroCal</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Filters")
    st.caption("Date range and impact filters arrive with the calendar tab.")

tab_calendar, tab_macro, tab_markets, tab_ask = st.tabs(["Calendar", "Macro", "Markets", "Ask"])

with tab_calendar:
    st.info("Calendar: coming in the next build step.")
with tab_macro:
    st.info("Macro: coming later.")
with tab_markets:
    st.info("Markets: coming later.")
with tab_ask:
    st.info("Ask: coming later.")
