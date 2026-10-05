# MacroCal

A Streamlit app that puts the **economic calendar next to the macro data behind it**, with market
views and an optional **AI analyst** that answers only from the app's own data.

Separate from [ecocal-dashboard](https://github.com/Fedor1971/ecocal-dashboard) (which stays as it
is). Code and styling were copied from it, not imported.

## What it does

| View | What you get | Needs |
|---|---|---|
| **Calendar** | World economic calendar for a date range, impact/currency filters, per-event details, CSV export. Selecting a US release (CPI, unemployment, payrolls, PPI, retail sales, earnings, participation) shows its series, latest vs previous and year over year next to the event. | internet (fxstreet, economy-intel) |
| **Macro** | US monthly series (BLS/Census), World Bank country comparison and profile, optional FRED series. | internet; FRED needs a free key |
| **Markets** | S&P 500, US 10-year yield, gold, WTI oil, EUR/USD, VNQ: rebased price chart, correlation heatmap, 2008 / COVID / 2022 presets. | internet (Yahoo Finance) |
| **Ask** | Chat with a Gemini-powered analyst that answers from the tools above and lists which ones it used. | `GEMINI_API_KEY` |

Each view loads only when opened and degrades on its own: if one source is down or a key is
missing, that view shows a short message and the rest of the app keeps working.

## Run it

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8510 --server.address localhost
```

Port 8510 avoids the other local Streamlit apps on this machine (8501-8503).

### One-click (Windows, for colleagues)

Unzip a release folder and double-click **`run.bat`**. The first start builds a private `.venv`
(from the bundled `wheels` folder if present, so no PyPI access is needed) and opens
http://localhost:8510. It listens on `localhost` only.

Maintainer, build a release:

```powershell
.venv\Scripts\python.exe tools\make_release.py --python 3.13          # offline zip with wheels -> dist/
.venv\Scripts\python.exe tools\make_release.py --no-wheels            # small online zip
```

The builder uses an allow-list and never bundles `.streamlit/secrets.toml` or `.env`. Wheels are
tied to the recipient's Python version (`python --version`) and Windows x64. **The app itself still
needs internet at run time**; offline, each view shows a "could not reach ..." message.

## Keys (both optional)

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (gitignored), or paste the same
lines into Streamlit Community Cloud > App settings > Secrets.

| Key | Enables | Where |
|---|---|---|
| `FRED_API_KEY` | FRED section in Macro | free: https://fred.stlouisfed.org/docs/api/api_key.html |
| `GEMINI_API_KEY` | Ask view | Google AI Studio: https://aistudio.google.com/apikey (outside the Claude subscription) |
| `GEMINI_MODEL` | override the default model name | optional |

Without a key the feature is hidden and says why.

## Ask: what to know before enabling it

- The model's only source of numbers is a fixed set of tools over this app's loaders. It is told
  never to quote numbers from memory and to name the tool, source and as-of date.
- **Caps** protect your quota on a public app: 15 questions per session and 200 per day (whole
  app). A question uses one unit however many lookups it needs.
- **Privacy:** questions are sent to Google's Gemini API. On the free tier Google may use inputs and
  outputs to improve its models, so the tab warns users not to enter sensitive information.
- The default model name (`gemini-2.5-flash`) was **not verified against the live API** at build
  time (no key was available). Set `GEMINI_MODEL` if Google has retired it.
- Not investment advice.

## Hosting on Streamlit Community Cloud

1. Make the repo public (the single private-repo slot belongs to another app), after scanning the
   whole git history for secrets.
2. share.streamlit.io > New app > repo `macrocal`, branch `master`, main file `app.py`.
3. App settings > Secrets: add the optional keys above.
4. First deploy: confirm `yfinance` installs on the cloud's Python (it was verified locally on 3.13).

`vendor/ecocal/` is a vendored copy of [ecocal](https://github.com/lcsrodriguez/ecocal) 1.2.1 (MIT,
license kept) so no special install step is needed. Do not edit it.

## Data sources and their risks

| Source | Used for | Risk |
|---|---|---|
| fxstreet via ecocal | calendar | undocumented third-party API; can change or break; ToS unclear |
| [economy-intel](https://github.com/datakoot/economy-intel-mcp) MCP (`economy.datakoot.com`) | BLS/Census series, World Bank | small third-party host, source **not audited**; BLS rate-limits shared IPs. Only series and country names are sent to it. |
| Yahoo Finance via `yfinance` | prices | unofficial; may be delayed, rate-limited or break |
| FRED | optional series | free key; the key never appears in logs or errors (tested) |
| Gemini API | Ask | see above |

Attribution: World Bank data is CC-BY 4.0; BLS and Census data are public domain. Informational
only. The idea of the correlation heatmap and crisis windows comes from
[Triumph-KT/macroeconomic-dashboard](https://github.com/Triumph-KT/macroeconomic-dashboard) (MIT);
no code was copied.

## Develop

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q                 # offline, ~10 s
.venv\Scripts\python.exe -m pytest -q -m live         # real APIs, run manually before shipping
.venv\Scripts\python.exe -m ruff check . --fix
```

Layout: `app.py` (view switcher), `macrocal/` (`events`, `intel`, `fred`, `markets`, `mapping`,
`context`, `bot`, `panels`, `result`, `config`), `tests/`, `tools/make_release.py`, `vendor/ecocal/`.
Every loader returns a `Result(data, error, source, as_of)` so views can degrade without try/except
in UI code. See `SPEC.md` for the design and `tasks/` for the plan.
