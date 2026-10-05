"""Euronext house style, copied from ecocal-dashboard (sampled from euronext.com 2026-10-02). Copied, not imported: the two apps stay independent."""

PALETTE = {
    "topbar": "#006157",
    "primary": "#008D7F",
    "dark": "#00685E",
    "hover": "#008577",
    "tint": "#BFE2DF",
    "accent": "#007DAE",
    "text": "#252631",
    "panel": "#F3F3F3",
    "white": "#FFFFFF",
}

CSS = f"""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]):not([class*="material"]) {{ font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; }}
.stApp {{ color: {PALETTE['text']}; }}
.eu-note {{ background: {PALETTE['tint']}40; border-left: 4px solid {PALETTE['primary']}; padding: .7rem 1rem; border-radius: 3px; margin-bottom: .75rem; }}
header[data-testid="stHeader"] {{ background: {PALETTE['topbar']}; }}
header[data-testid="stHeader"]::before {{ content: "MacroCal · Euronext style"; color: #fff; font-size: .85rem; letter-spacing: .02em; padding-left: 1.5rem; align-self: center; }}
header[data-testid="stHeader"] * {{ color: #fff !important; }}
.eu-title {{ font-weight: 600; font-size: 2.4rem; color: #000; border-bottom: 2px solid {PALETTE['primary']}; padding-bottom: .6rem; margin: 0 0 1rem 0; }}
h2, h3 {{ color: {PALETTE['primary']}; font-weight: 400; }}
.eu-chip {{ display:inline-block; padding:.1rem .6rem; border-radius:3px; font-size:.8rem; font-weight:600; }}
.eu-closed {{ background:{PALETTE['dark']}; color:#fff; }}
.eu-half {{ background:{PALETTE['tint']}; color:{PALETTE['dark']}; }}
.eu-notah {{ background:{PALETTE['panel']}; color:{PALETTE['text']}; }}
.eu-manual {{ background:{PALETTE['accent']}; color:#fff; }}
[data-testid="stSidebar"] {{ background: {PALETTE['panel']}; }}
.stDownloadButton button {{ border-color: {PALETTE['primary']}; color: {PALETTE['primary']}; }}
.stDownloadButton button:hover {{ background: {PALETTE['primary']}; color: #fff; }}
</style>
"""


def inject(st) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
