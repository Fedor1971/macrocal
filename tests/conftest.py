import pytest
import streamlit as st


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    # st.cache_data also works outside a running app; without this, one test's fake
    # server reply would be served from cache to the next test.
    st.cache_data.clear()
    yield
    st.cache_data.clear()
