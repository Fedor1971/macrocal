# MacroCal v1: task list

Plan: `plan.md`. Spec: `../SPEC.md`.

## Phase 1: Foundation and the core flow
- [x] T1 Scaffold (Result, config, style, vendor, hello app) · S/M
- [x] T2 Calendar slice: browse, filter, detail, export · M
- [x] T3 `economy-intel` client + `us_series` · S
- [x] T4 Event → macro context (mapping + panel) · S
- [x] **Checkpoint 1:** verified in a real browser 2026-10-05: USD Nonfarm Payrolls shows its series (event Actual +29k = series change +29), EUR "Consumer Price Index (YoY)" shows "No linked series". US CPI and Unemployment not in the visible window (CPI due ~Oct 14); covered by tests, recheck in the test phase

## Phase 2: Data tabs
- [x] T5 Macro tab: US series + World Bank · M
- [x] T6 FRED optional section · S
- [x] T7 Markets tab (+ yfinance compat check) · M
- [x] **Checkpoint 2:** Macro and Markets verified in a real browser on live data (2026-10-05). "Source blocked" behaviour is covered by AppTest per view (calendar, macro, FRED, markets failures), not by blocking the network in the browser. Found and fixed: YoY for rate series now in percentage points. yfinance Python 3.14 (Streamlit Cloud) compat still to confirm at first deploy.

## Phase 3: AI bot
- [x] T8 Bot core: tools, validation, caps (no UI) · M
- [~] T9 Ask tab + Gemini wiring: UI and mocked tests done (214 pass); LIVE Gemini run blocked on GEMINI_API_KEY from Fedor; default model name unverified
- [~] **Checkpoint 3:** bot logic + UI verified with a fake client (mutation-checked); scripted live Q&A BLOCKED on GEMINI_API_KEY

## Phase 4: Ship-readiness
- [x] T10 Degradation states, run.bat, offline release: clean-room offline install verified 2026-10-05 (no-index install, vendored ecocal loads, 157 live events, health ok)
- [x] T11 README, secrets example, live smoke tests (calendar, intel, World Bank, markets pass live; FRED + Gemini skip without keys)
- [~] **Checkpoint 4:** criteria 1-6,8 partly met: see "Open before ship" below

## Then
- [ ] Test phase · [ ] Review phase · [ ] Ship gate (secret scan → public repo → Cloud → verify EcoCal → vault save)

## Waiting on Fedor
- [ ] `GEMINI_API_KEY` from Google AI Studio (before T9 live test)
- [ ] Optional `FRED_API_KEY`

## Open before ship (as of 2026-10-05, after T11)
- [ ] Fedor: create `GEMINI_API_KEY` (Google AI Studio) -> run `pytest -m live`, 5 scripted Ask questions, confirm/replace the default model name
- [ ] Run the real `run.bat` from the offline zip (only its steps were verified by hand in a clean room), view in browser
- [ ] Browser-recheck US CPI + Unemployment event context (not in the visible window on 2026-10-05)
- [ ] Test phase (full suite + live), review phase (security: secrets, prompt injection via tool output, quota abuse), then ship gate
- [ ] Ship: secret scan of full history -> public repo -> Streamlit Cloud (check yfinance on its Python) -> confirm ecocal-dashboard still loads -> /obsidian-save
