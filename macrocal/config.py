"""Secret lookup. Env var first, then Streamlit secrets. Never raises: a missing key hides a feature."""

from __future__ import annotations

import os


def get_secret(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        value = _streamlit_secret(name)
    value = (value or "").strip()
    return value or None


def _streamlit_secret(name: str) -> str | None:
    try:
        import streamlit as st

        raw = st.secrets.get(name)
    except Exception:  # noqa: BLE001 - st.secrets raises varied errors when absent
        return None
    return str(raw) if raw is not None else None
