# Implementation Plan: MacroCal v1

Spec: `../SPEC.md` (locked 2026-10-05). Complexity: Medium. Phases after this plan: build → test → review → ship.

## Overview

Streamlit app joining the economic calendar (vendored ecocal) with macro series (`economy-intel`, optional FRED), market data (`yfinance`) and a Gemini Q&A bot. Built as vertical slices, so after every task the app runs and one more thing works end to end.

## Architecture decisions

- **Spec deviation (trivial):** `macrocal/calendar.py` is renamed `macrocal/events.py`. A module called `calendar` shadows the stdlib name that pandas imports. SPEC.md structure updated to match.
- **Every loader returns `Result(data, error, source, as_of)`.** Panels render the error and carry on; `app.py` has no try/except for data.
- **`economy-intel` client is plain `requests`** (initialize → `Mcp-Session-Id` → `notifications/initialized` → `tools/call`), JSON or SSE bodies. One session per process, re-initialised on a 404/expired session.
- **The bot calls the same cached data-layer functions the UI calls.** No second data path, so it can only say what the dashboard can show.
- **Secrets only via `st.secrets` / env**, read in one place (`macrocal/config.py`). A missing key hides the feature instead of raising.
- **Tests never touch the network.** Captured payloads live in `tests/fixtures/`. Live smoke tests are marked `live` and run manually.

## Dependency graph

```
T1 scaffold (Result, config, style, vendor)
 ├─ T2 calendar slice ──────────────┐
 ├─ T3 intel client (us_series) ────┤
 │                                  ├─ T4 mapping + event context   [CP1: core flow]
 │                                  │
 ├─ T5 macro tab (needs T3)
 ├─ T6 FRED optional (needs T1)
 ├─ T7 markets tab (needs T1)                                       [CP2: all data tabs]
 │
 ├─ T8 bot core (needs T2, T3, T5, T6, T7 data functions)
 ├─ T9 Ask tab + Gemini wiring (needs T8)                           [CP3: bot works]
 │
 └─ T10 degradation + run.bat + release (needs all)
    T11 README, secrets example, live smoke                         [CP4: ship-ready]
```

T5, T6 and T7 are independent once T1 and T3 exist, so they can be done in any order (or in parallel).

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `economy-intel` responds with SSE or changes its handshake | High | T3 is early and run against the live endpoint, with the payload captured as a fixture |
| `yfinance` has no wheels or breaks on Streamlit Cloud's Python 3.14 | High | T7 does an early cloud-compat check (install in a clean venv on 3.13 locally, then confirm on cloud at first deploy). Fallback: drop Markets to a lighter source or mark it optional |
| fxstreet calendar API changes | Med | Same as EcoCal; the calendar panel degrades via `Result` |
| Public app burns the Gemini quota | Med | Per-session and daily caps tested in T8 |
| Gemini model name or SDK differs from what I remember | Med | Check the SDK docs and the current free-tier model at T9. Make it `GEMINI_MODEL`-configurable. Needs Fedor's key for the live test |
| Event names don't map cleanly | Med | T4 uses an explicit rules table plus tests for non-matches. It prefers "no linked series" over a wrong series |
| Secrets leak into the public repo | High | `.gitignore` in T1, secret scan of the history at ship |

## Task list

### Phase 1: Foundation and the core flow

#### Task 1: Scaffold the project
**Description:** Repo skeleton, tooling and shared building blocks, with a runnable "hello" app in the Euronext style.
**Acceptance criteria:**
- [ ] Layout matches SPEC (with `events.py` rename); `vendor/ecocal` copied unchanged with its LICENSE
- [ ] `Result` dataclass, `config.py` (key lookup that never raises), `style.py` copied, `.gitignore` covers `.venv`, `secrets.toml`, `.env`, `dist/`, `wheels/`
- [ ] `requirements.txt`, `requirements-dev.txt`, `.streamlit/config.toml`, `secrets.toml.example`
- [ ] `app.py` shows the title, 4 empty tabs and the sidebar
**Verification:** `pytest -q` passes (tests for `Result` and `config`); `streamlit run app.py --server.port 8502` loads in a browser; `git status` shows no secret files.
**Dependencies:** None
**Files:** `app.py`, `style.py`, `macrocal/result.py`, `macrocal/config.py`, `.gitignore`, `requirements*.txt`, `.streamlit/*`, `tests/test_result.py`, `tests/test_config.py` (about 11 files, all small; the scaffold is the one exception to the 5-file guideline)
**Scope:** M

#### Task 2: Calendar slice: browse, filter, export
**Description:** The EcoCal core in the new app: date range, Impact filter, calendar table, per-event detail on demand, CSV export. Behaviour copied from `ecocal-dashboard`, rewritten around `Result`.
**Acceptance criteria:**
- [ ] `events.py`: `fetch_calendar(start, end) -> Result`, `fetch_event_details(id) -> Result`, with the `numpy.NaN` shim
- [ ] Calendar tab shows the table, an Impact multiselect, row selection with a detail panel, and a CSV download of the current view
- [ ] If the fetch fails, the tab shows the error and the rest of the app still works
**Verification:** `pytest -q -k events` (shaping and filtering functions on a fixture frame); manual: real range shows events, HIGH-only filter cuts rows, detail fetch works.
**Dependencies:** T1
**Files:** `macrocal/events.py`, `app.py`, `tests/test_events.py`, `tests/fixtures/calendar_sample.csv`
**Scope:** M

#### Task 3: `economy-intel` client with `us_series`
**Description:** The MCP-over-HTTP client and a typed `us_series(series)` helper returning a time-indexed frame.
**Acceptance criteria:**
- [ ] Handshake, session reuse and re-init on an expired session; JSON and SSE response parsing; `isError` mapped to `IntelError`
- [ ] `us_series` returns `Result` with columns `date`, `value` (newest-first input sorted ascending) and `as_of`
- [ ] A real response is captured to `tests/fixtures/`
**Verification:** `pytest -q -k intel` (fixtures, handshake mocked); `pytest -q -m live -k intel` against the real endpoint (manual).
**Dependencies:** T1
**Files:** `macrocal/intel.py`, `tests/test_intel.py`, `tests/fixtures/us_series_*.json`
**Scope:** S

#### Task 4: Event → macro context
**Description:** Selecting a calendar event shows the series behind it: chart, last 24 readings and latest-vs-previous change, via an explicit rules table.
**Acceptance criteria:**
- [ ] `mapping.py`: rules from event name keywords plus currency to a series key (USD only: CPI, unemployment, nonfarm payrolls, PPI, retail sales, participation, hourly earnings)
- [ ] Non-USD and unmatched events return `None` and the UI says "no linked series"
- [ ] Context panel shows chart, provenance (`source`, `as_of`) and the change
**Verification:** `pytest -q -k mapping` (table of match and non-match cases, including look-alikes such as "Core CPI" vs "CPI"); manual: CPI, Unemployment and an unmapped event.
**Dependencies:** T2, T3
**Files:** `macrocal/mapping.py`, `app.py`, `tests/test_mapping.py`
**Scope:** S

#### Checkpoint 1: core flow
- [ ] `pytest -q` green; app runs
- [ ] Calendar → select CPI → chart + change, verified in a real browser
- [ ] Unmapped event shows a clear note, not a wrong chart
- [ ] **Commit** and review with Fedor if anything surprising came up

### Phase 2: Data tabs

#### Task 5: Macro tab (US series and World Bank)
**Description:** US series picker with chart, plus country profile and country comparison using the World Bank tools.
**Acceptance criteria:**
- [ ] `intel.py` gains `country_profile`, `compare_countries`, `country_indicator`, `list_indicators` returning `Result`
- [ ] Tab: US series chart and table; country profile card; indicator comparison bar chart across chosen countries
- [ ] Bad input surfaces the server's message, no stack trace
**Verification:** `pytest -q -k intel` (new fixtures); manual: NLD profile unemployment equals the comparison value (same consistency check as 2026-10-05).
**Dependencies:** T3
**Files:** `macrocal/intel.py`, `app.py`, `tests/test_intel.py`, fixtures
**Scope:** M

#### Task 6: FRED (optional)
**Description:** FRED loader gated on `FRED_API_KEY`; adds a "FRED" section to the Macro tab with a short curated series list (fed funds, 10y, GDP, leading index).
**Acceptance criteria:**
- [ ] No key → section hidden with a one-line hint; key present → charts render; HTTP errors → `Result.error`
- [ ] Key never appears in logs, errors or the UI
**Verification:** `pytest -q -k fred` (mocked requests, including a test that the key is not in any error string); manual with a real key if available.
**Dependencies:** T1 (UI placement uses T5's tab)
**Files:** `macrocal/fred.py`, `app.py`, `tests/test_fred.py`
**Scope:** S

#### Task 7: Markets tab
**Description:** yfinance loaders for the six instruments; normalised price chart, correlation heatmap over a chosen window, crisis-window presets.
**Acceptance criteria:**
- [ ] `markets.py`: `fetch_prices(symbols, start, end) -> Result`, `returns()`, `correlation(window)`, `CRISIS_WINDOWS` constant
- [ ] Tab: asset multiselect, window picker with presets, normalised chart, heatmap, provenance caption
- [ ] **Compat check:** `yfinance` installs and runs in a clean venv on Python 3.13; recorded in the dev log, with the cloud result checked at first deploy
**Verification:** `pytest -q -k markets` (correlation and returns maths on a small hand-built frame); manual: 2008 preset renders; empty-data case shows a message.
**Dependencies:** T1
**Files:** `macrocal/markets.py`, `app.py`, `tests/test_markets.py`
**Scope:** M

#### Checkpoint 2: all data tabs
- [ ] `pytest -q` green; each tab works alone with the others' sources blocked
- [ ] Core flow from CP1 still works
- [ ] **Commit**

### Phase 3: AI bot

#### Task 8: Bot core (no UI)
**Description:** `bot.py` with tool declarations mapped to data-layer functions, argument validation, a system prompt that forbids numbers from memory, and usage caps.
**Acceptance criteria:**
- [ ] Tools: `get_calendar`, `us_series`, `country_profile`, `compare_countries`, `market_summary`, `fred_series` (only when keyed)
- [ ] Unknown tools and invalid args are rejected before any call; tool output is truncated to a sane size
- [ ] Session cap 15 and process-wide daily cap 200 enforced and tested; Gemini client is injectable so tests use a fake
**Verification:** `pytest -q -k bot` (routing, validation, caps, truncation, tool error is passed back to the model as text).
**Dependencies:** T2, T3, T5, T6, T7
**Files:** `macrocal/bot.py`, `tests/test_bot.py`
**Scope:** M

#### Task 9: Ask tab and Gemini wiring
**Description:** Chat UI over `bot.py` with the real Gemini SDK: history in `st.session_state`, tool-call citations shown under each answer, key gating.
**Acceptance criteria:**
- [ ] SDK usage and the default model are checked against current docs, and the model is `GEMINI_MODEL`-overridable
- [ ] No key → tab shows "bot disabled" instructions; cap reached → clear message
- [ ] 5 scripted questions answered with the tool named; an off-topic question gets a short refusal
**Verification:** `pytest -q` stays green; manual with Fedor's `GEMINI_API_KEY` (**blocked until the key exists**, so mocked work is done first and the live run is a checklist item).
**Dependencies:** T8
**Files:** `app.py`, `macrocal/bot.py`, `tests/test_bot.py`
**Scope:** S

#### Checkpoint 3: bot
- [ ] Scripted Q&A verified live (or flagged as waiting on the key)
- [ ] All earlier flows still pass
- [ ] **Commit**

### Phase 4: Ship-readiness

#### Task 10: Degradation, local launcher, offline release
**Description:** Make every failure mode clean, then package for colleagues.
**Acceptance criteria:**
- [ ] With network blocked per source, each panel shows its own message and nothing else breaks
- [ ] `run.bat` adapted from EcoCal (port 8502, installs the vendored/--no-deps ecocal path as before); `tools/make_release.py` builds the offline zip
- [ ] Clean-room offline install verified, as was done for EcoCal
**Verification:** manual: toggle each source off; run `run.bat` from a fresh folder; `make_release.py` zip installs without internet.
**Dependencies:** T2–T9
**Files:** `run.bat`, `tools/make_release.py`, `app.py`, minor `macrocal/*`
**Scope:** M

#### Task 11: Docs, examples and live smoke
**Description:** README with setup, keys and data-source caveats, `secrets.toml.example`, and `-m live` smoke tests for all five sources.
**Acceptance criteria:**
- [ ] README covers local run, Cloud deploy, keys, the ToS/fragility notes per source, and the third-party-host warning
- [ ] `pytest -q -m live` passes for calendar, intel, markets (and FRED/Gemini when keys are present)
**Verification:** run the live suite; read the README from a cold start.
**Dependencies:** T10
**Files:** `README.md`, `tests/test_live.py`, `.streamlit/secrets.toml.example`
**Scope:** S

#### Checkpoint 4: ship-ready
- [ ] SPEC success criteria 1–6 and 8 ticked (7, the secret scan, runs at ship)
- [ ] Hand off to test, review, ship phases

## After the plan (not tasks here)

- **Test phase:** full `pytest -q`, live smoke, browser verification per SPEC (CPI, Unemployment, unmapped event, each tab, each degraded state).
- **Review phase:** correctness, security (secrets, prompt-injection from tool output into the bot, quota abuse), readability.
- **Ship (gate):** secret scan of full history → `gh repo create macrocal --public` → Streamlit Cloud deploy (manual form; add secrets there) → confirm `ecocal-dashboard` URL still loads → `/obsidian-save`.

## Open questions

- Fedor creates the `GEMINI_API_KEY` (needed at T9 live test). Not blocking T1–T8.
- Optional free `FRED_API_KEY` (T6 live test only).
