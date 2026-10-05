# Spec: MacroCal

Status: DRAFT for review (2026-10-05). Complexity: Medium.

## Objective

A Streamlit app that puts the **economic calendar next to the macro data behind it**, with an **AI analyst** that answers questions from that same data.

- **User:** Fedor (finance background, Euronext context), and colleagues on a restricted network for the local build.
- **Problem:** [EcoCal Dashboard](../ecocal-dashboard) lists upcoming releases ("US CPI") but shows nothing about the prior readings or trend. Triumph-KT's macroeconomic-dashboard shows macro series and cross-asset correlation but has no calendar. MacroCal joins the two.
- **EcoCal Dashboard stays live and untouched.** MacroCal is a separate repo and a separate Streamlit Cloud app. Code is copied, never imported.

### Core features (v1)

1. **Calendar with context.** Pick a date range and impact filter (same as EcoCal). Select an event; if it maps to a known series (e.g. "CPI", "Unemployment", "Nonfarm Payrolls", "Retail Sales", "PPI"), show the series chart, last 24 readings and the latest-vs-previous change next to the event detail.
2. **Macro tab.** US series from `economy-intel` (`us_series`), country comparison and profile from World Bank via `economy-intel`, and optional FRED series (rates, GDP, leading index) when a FRED key exists.
3. **Markets tab.** S&P 500, US 10y yield, gold, WTI oil, EUR/USD, VNQ via `yfinance`. Normalised price chart, correlation heatmap over a chosen window, and crisis-window presets (2008, COVID 2020, 2022 inflation shock).
4. **Ask tab (Gemini bot).** Chat panel that answers from the app's own data using function-calling over the data layer. It cites which tool results it used. No answers from model memory for numbers.
5. **Euronext house style** (copy of EcoCal's `style.py`), CSV export of the current calendar view.

### Acceptance criteria for the core flow

- Selecting a HIGH-impact "CPI" USD event shows the `us_cpi` chart and "latest vs previous" within 3 s on a warm cache.
- Selecting an event with no mapping shows its details and a clear "no linked series" note. It never shows a wrong series.
- Each tab degrades independently: if one source is down or a key is missing, that panel shows a short message and the rest of the app works.
- Ask tab: "What was the latest US unemployment rate?" returns the value that `us_series` returns, with the tool named in the answer.

## Tech Stack

- Python 3.11+ (cloud runs 3.14; local `run.bat` finds 3.11–3.13)
- `streamlit>=1.38`, `pandas>=2.2`, `plotly`, `requests`, `yfinance`
- `google-genai` (Gemini SDK). Model name is read from `GEMINI_MODEL` with a default confirmed at build time. Not asserted in this spec because model names change.
- Vendored `ecocal` 1.2.1 in `vendor/ecocal/` (same pattern and `numpy.NaN` shim as EcoCal)
- `pytest` + `pytest-mock` (dev only)

### Data sources

| Source | Auth | Use | Risk |
|---|---|---|---|
| fxstreet via ecocal | none | calendar | undocumented API, same as EcoCal |
| `economy-intel` MCP (`https://economy.datakoot.com/mcp`) | none | US BLS/Census series, World Bank | third-party host, unaudited, BLS rate limits on shared IPs |
| FRED REST | `FRED_API_KEY` (free) | optional rates/GDP/CLI | key management |
| Yahoo via `yfinance` | none | market prices | unofficial, can break or rate-limit |
| Gemini API | `GEMINI_API_KEY` | bot | outside the Claude subscription; free tier has quotas |

`economy-intel` is called with a small HTTP client in the app (initialize → read `Mcp-Session-Id` → `notifications/initialized` → `tools/call`; responses may be JSON or SSE). Verified manually on 2026-10-05, see [[Knowledge/Economy-Intel-MCP]]. Triumph-KT's code is **not** copied: its loaders are ~30 lines each and it reads committed CSV snapshots. Only the ideas (KPI cards, correlation heatmap, crisis windows) are reused. The repo is MIT, and its README claims ARIMA but the app code uses a linear forecast, so there is **no forecasting in v1**.

## Commands

Run from the project root with the project venv (global `streamlit` lacks deps).

```
Setup:     py -3.13 -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
Dev:       .venv\Scripts\python.exe -m streamlit run app.py --server.port 8502 --server.address localhost
Test:      .venv\Scripts\python.exe -m pytest -q
Test live: .venv\Scripts\python.exe -m pytest -q -m live      # hits real APIs, run manually
Lint:      .venv\Scripts\python.exe -m ruff check . --fix
Release:   .venv\Scripts\python.exe tools\make_release.py     # offline zip with wheels
Local run: run.bat                                             # one-click, port 8502
```

Port 8502 so it can run next to EcoCal (8501).

## Project Structure

```
app.py                 → Streamlit entry: sidebar + 4 tabs, no data logic
style.py               → Euronext theme (copied from ecocal-dashboard)
macrocal/
  events.py            → ecocal wrapper, cached fetch, event details on demand (not "calendar.py": shadows stdlib)
  config.py            → key lookup from st.secrets/env, never raises
  intel.py             → economy-intel HTTP/MCP client + typed helpers
  fred.py              → FRED loader (returns empty + reason if no key)
  markets.py           → yfinance loader, returns, correlation, crisis windows
  mapping.py           → event name/currency → series key rules
  bot.py               → Gemini client, tool declarations, guardrails, usage caps
  result.py            → Result(data, error, source, as_of) used by every loader
tests/                 → pytest, HTTP mocked (fixtures/ holds captured payloads)
vendor/ecocal/         → vendored, never edited (MIT, LICENSE kept)
tools/make_release.py  → offline wheelhouse zip builder (adapted from EcoCal)
.streamlit/config.toml, secrets.toml.example
requirements.txt, requirements-dev.txt, run.bat, README.md, SPEC.md
```

## Code Style

Every loader returns a `Result`, so panels can degrade without try/except in UI code:

```python
@dataclass(frozen=True)
class Result:
    data: pd.DataFrame | None
    error: str | None = None
    source: str = ""
    as_of: str = ""          # data date as reported by the source, not "now"

@st.cache_data(ttl=3600, show_spinner=False)
def us_series(series: str) -> Result:
    try:
        payload = _call_tool("us_series", {"series": series})
    except IntelError as exc:
        return Result(None, error=str(exc), source="economy-intel")
    return Result(_to_frame(payload), source="BLS/Census", as_of=payload["as_of"])
```

Conventions: type hints, `from __future__ import annotations`, small functions, no data fetching inside `app.py`, `snake_case`, ruff defaults, comments only for non-obvious "why" (undocumented API quirks, shims).

## Testing Strategy

- **Unit (pytest, no network):** `mapping.py` (event→series rules incl. non-matches), `intel.py` (JSON and SSE parsing, session handshake, `isError` handling) against captured fixtures, `markets.py` (returns/correlation maths on a small frame), `Result` handling, bot usage caps and tool-argument validation.
- **Bot:** Gemini is mocked. Tests assert that tool calls route to the data layer, bad args are rejected, caps trigger, and a missing key hides the panel. Answer quality is checked manually.
- **Live smoke (`-m live`, manual):** one real call per source. Run before ship. Not in any automatic run.
- **UI:** manual browser verification via claude-in-chrome before ship (as done for EcoCal): calendar → event → context, each tab, each degraded state (disable network per source).
- Coverage target: logic modules (`mapping`, `intel`, `markets`, `bot`) ≥ 80%. `app.py` is excluded.

## Boundaries

**Always**
- Run `pytest -q` before each commit. Keep EcoCal's vendored code unmodified.
- Return `Result` from loaders and show `source` + `as_of` next to every chart (data provenance is a house rule).
- Show real data only: no mocks, no made-up values, no forecasts.
- Cap bot usage: per-session message limit (15) and a process-wide daily limit (200), because a public app plus my API key is open to quota abuse.

**Ask first**
- Adding a dependency beyond the list above, a new data source, or any paid API.
- Changing the Streamlit Cloud app settings, making the repo private, or anything touching `ecocal-dashboard`.
- Persisting user data or chat logs anywhere.

**Never**
- Commit secrets (`secrets.toml`, `.env`), or print keys in logs or the UI.
- Let the bot answer numeric questions from model memory, run web search, or execute code.
- Send sensitive text to `economy-intel` or Gemini (both are third-party hosts). Prompts contain only dashboard data and the user's question.
- Edit `vendor/`, or `git add -A` without checking for secrets.

## Success Criteria (definition of done for v1)

1. Local run via `run.bat` on a clean Windows machine with internet: all four tabs work.
2. Offline: `run.bat` still starts; macro, markets and bot panels show a clear "offline" message, and the calendar degrades the same way (it needs fxstreet).
3. Streamlit Cloud deployment (public repo) works with `GEMINI_API_KEY` and `FRED_API_KEY` in Cloud secrets, and works with both missing (FRED and bot panels hidden/disabled).
4. `pytest -q` is green. Live smoke passes for all five sources on ship day.
5. Calendar event → context verified in a real browser for at least CPI, Unemployment and one unmapped event.
6. Bot: 5 scripted questions answered with tool citations. Caps verified. An off-topic question gets a short refusal.
7. Secret scan of the full git history is clean before the repo is made public.
8. `ecocal-dashboard` still loads at its existing URL after the work.

## Open Questions

1. **Gemini model default.** Check the current free-tier model at build time and set the default then. Needs a `GEMINI_API_KEY` from Google AI Studio (Fedor to create one; I will not).
2. **Non-USD events.** v1 maps USD events to US series. EUR events could map to World Bank country data (annual only, poor fit for a release calendar), so I propose "no linked series" for them in v1. OK?
3. **Cloud slot.** The Euronext app holds the private slot, so MacroCal's repo must be public (same as ecocal). Confirmed assumption, flagging because it affects the secret-scan boundary.
