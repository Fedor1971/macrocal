# MacroCal v1: task list

Plan: `plan.md`. Spec: `../SPEC.md`.

## Phase 1: Foundation and the core flow
- [x] T1 Scaffold (Result, config, style, vendor, hello app) · S/M
- [x] T2 Calendar slice: browse, filter, detail, export · M
- [x] T3 `economy-intel` client + `us_series` · S
- [x] T4 Event → macro context (mapping + panel) · S
- [x] **Checkpoint 1:** verified in a real browser 2026-10-05: USD Nonfarm Payrolls shows its series (event Actual +29k = series change +29), EUR "Consumer Price Index (YoY)" shows "No linked series". US CPI and Unemployment not in the visible window (CPI due ~Oct 14); covered by tests, recheck in the test phase

## Phase 2: Data tabs
- [ ] T5 Macro tab: US series + World Bank · M
- [ ] T6 FRED optional section · S
- [ ] T7 Markets tab (+ yfinance compat check) · M
- [ ] **Checkpoint 2:** every tab works alone with other sources blocked

## Phase 3: AI bot
- [ ] T8 Bot core: tools, validation, caps (no UI) · M
- [ ] T9 Ask tab + Gemini wiring (live test needs `GEMINI_API_KEY`) · S
- [ ] **Checkpoint 3:** scripted Q&A verified (or flagged as waiting on the key)

## Phase 4: Ship-readiness
- [ ] T10 Degradation states, `run.bat`, offline release · M
- [ ] T11 README, secrets example, live smoke tests · S
- [ ] **Checkpoint 4:** SPEC success criteria 1–6 and 8 met

## Then
- [ ] Test phase · [ ] Review phase · [ ] Ship gate (secret scan → public repo → Cloud → verify EcoCal → vault save)

## Waiting on Fedor
- [ ] `GEMINI_API_KEY` from Google AI Studio (before T9 live test)
- [ ] Optional `FRED_API_KEY`
