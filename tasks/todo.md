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
- [x] T9 Ask tab + Gemini wiring: verified live 2026-10-05 with Fedor's key (5 scripted questions grounded, off-topic and advice questions declined; default model verified)
- [x] **Checkpoint 3:** scripted live Q&A passed 2026-10-05 (all figures match their tool output; prediction/advice question declined without tools). FRED also verified live (120 rows).

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
- [x] Gemini key + FRED key added by Fedor to `.streamlit/secrets.toml` (they had first been pasted into the TRACKED secrets.toml.example; caught before any commit, moved, example restored, guard test added)
- [x] Real `run.bat` run from the offline zip (2026-10-05): created the venv, installed offline, healthy app on 8510. Launch it as `.\run.bat`: this machine sets NoDefaultCurrentDirectoryInExePath=1, so a bare `run.bat` typed in a shell is not found (double-click is fine).
- [x] US CPI, Unemployment, PPI, retail sales, participation, earnings and payrolls context verified on real data via AppTest (core CPI unmapped as designed); real-browser pass earlier on payrolls and EUR CPI.
- [x] Test + review phases done 2026-10-05: 237 offline tests, 7 live pass; review found no Critical and 6 Important, all fixed in 4bd71fd. Git history scanned: no real secrets (only a fake test key, since renamed).
- [ ] Ship: secret scan of full history -> public repo -> Streamlit Cloud (check yfinance on its Python) -> confirm ecocal-dashboard still loads -> /obsidian-save
