import pytest
import streamlit as st

from macrocal import config


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    # st.cache_data also works outside a running app; without this, one test's fake
    # server reply would be served from cache to the next test.
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture(autouse=True)
def isolate_secrets(monkeypatch):
    # A developer's real keys (env or .streamlit/secrets.toml) must never change test outcomes.
    for name in ("FRED_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "_streamlit_secret", lambda name: None)
