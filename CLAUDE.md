# CLAUDE.md — GeoSentinel Terminal (VARTA)
# Master Reference v1.1 — April 15, 2026
# Team 7 Lambda | Advanced Python SP2026 | Rutgers University

Read this file before touching anything. It overrides all default Claude Code behavior.

---

## What This Project Is

**GeoSentinel Terminal** — a historically-validated geopolitical regime detection and return prediction engine.

Built on the Vaartha midterm causal chain: GPR → GSCPI → mineral supply → CapEx.
Validated across **14 distinct geopolitical shocks from 2010–2024**.

> "We built a historically-validated regime detection engine that identifies Crisis vs Normal regimes
> using GPR and Brent volatility, and shows that regime-conditional return patterns are persistent
> and repeatable across 14 independent geopolitical events spanning 14 years."

**Due dates:** Presentation May 5, 2026 · Full submission May 9, 2026

**Team:** Tarun Theegela (Ttheegela) · Sai Raunak Bidesi (ssb196) · Chaitanya Deogaonkar (cmd517) · Satwik Nadipelli (srn91)

---

## Professor Feedback (April 14, 2026) — Applied

- No live crisis framing — use historical data to predict historical outcomes
- Clean train/test split — results must be defensible and interpretable
- Signals must be persistent and repeatable across events, not crisis-specific
- Results can still be framed as applicable to future crises — without modeling one live

---

## Working Directory

`/Users/taruntheegela/Desktop/VARTA/`

---

## Tech Stack (Locked — No Changes Without Team Approval)

| Layer | Tool |
|-------|------|
| Frontend | Streamlit 1.42+ |
| Charts | Plotly only (no matplotlib) |
| Maps | Folium + streamlit-folium |
| DataFrames | **Polars** (never pandas) |
| SQL queries | DuckDB |
| Data sources | yfinance, FRED API, GDELT |
| Regime detection | HMM/GMM (hmmlearn / sklearn) |
| Signal model | XGBoost walk-forward |
| Foundation model | Kronos-base (AAAI 2026, Amazon Chronos) |
| LLM | Ollama — Gemma 4 12B (deep) + Gemma 4 4B (fast) |
| Device | Apple M3 Pro, MPS backend |

**NOT in stack:** pandas, matplotlib, Reddit/PRAW, Vercel, Supabase, TypeScript, any cloud API.

---

## 12 Assets (Locked — No Additions)

REMX, LIT, ALB, FCX, NVDA, TSM, AMD, BNO, XOM, CVX, GLD, SPY

- REMX (Mar 2010), LIT (Jul 2010), BNO (Jun 2010) are the binding inception constraints
- All 12 have clean data from **2010-08-01** — no nulls across the full window

---

## Data Window (Locked)

| Window | Dates | Purpose |
|--------|-------|---------|
| **Full training** | 2010-08-01 → 2024-12-31 | All 12 tickers clean, 14 years, 14 geopolitical events |

No live window. No 2025–2026 data. Historical prediction of historical outcomes only.

---

## 14 Key Geopolitical Events (training window)

| Date | Event |
|------|-------|
| 2010-12-18 | Arab Spring |
| 2011-03-11 | Fukushima Disaster |
| 2014-02-27 | Russia-Crimea Annexation |
| 2014-06-20 | Oil Price Collapse |
| 2015-06-12 | China Market Crash |
| 2016-06-23 | Brexit Vote |
| 2017-09-03 | N. Korea ICBM Test |
| 2018-03-01 | US-China Trade War |
| 2019-09-14 | Aramco Attack |
| 2020-01-03 | Soleimani Strike |
| 2020-03-11 | COVID Declared |
| 2022-02-24 | Ukraine Invasion |
| 2023-10-07 | Hamas Attack |
| 2024-01-12 | Red Sea Disruption |

---

## Module Build Order (Hard — Do Not Skip Ahead)

1. `config.py` ✓ done
2. `src/data/fetchers.py` + `validators.py` + `loaders.py`
3. `scripts/build_demo_bundle.py` → **confirm demo works offline**
4. `src/models/regime.py` → `signals.py` → `llm.py` → `kronos.py`
5. `src/tabs/tab1` → `tab2` → `tab3` → `tab4` → `tab5`
6. Demo freeze before May 3

---

## 5 Dashboard Tabs

| Tab | File | Content |
|-----|------|---------|
| 1 | tab1_watchlist.py | 2010-2024 prices, regime label, GeoRisk Score 0-100 |
| 2 | tab2_crisis_timeline.py | 14-event historical timeline, GPR+GSCPI, GDELT headlines per event |
| 3 | tab3_regime.py | HMM/GMM regime visualization + 6-model quant risk stack |
| 4 | tab4_signals.py | XGBoost walk-forward OOS results + Kronos forecasts |
| 5 | tab5_maps.py | Supply chain geography — mineral sites + shipping chokepoints |

---

## Hard Rules — Never Break These

### Code
- **Polars only** — never import pandas
- **All constants in config.py** — never hardcode tickers, dates, paths
- **Docstring before every function body**
- **No magic numbers**
- **Walk-forward OOS metrics only** — never report in-sample accuracy anywhere
- **No business logic in tab files** — display code only; data via loaders.py
- **Never call Gemma 4 12B on user interaction** — pre-compute and cache
- **Verify actual library API signature before using it**

### Data
- **Demo mode default** — app must work fully offline
- **Parquet in data/processed/**, **CSV in data/demo/** — no other formats
- **Never read, print, or log API keys**
- **No Reddit** — removed; use GDELT for news signal

### Charts
- **Plotly only** — no matplotlib
- **Dark theme** via `set_dark_theme()` in utils.py
- **Annotate all 14 events** via `annotate_events()` on every time-series chart
- **Every chart saved to outputs/charts/** with a companion 2-sentence caption .txt

### Git
- **Never commit**: .env, data/raw/, data/processed/, data/demo/, outputs/
- **Never force-push**
- **No "Co-Authored-By: Claude" in commit messages**

---

## Claude Code Operating Instructions

### State at the top of every response:
1. Which module you are modifying
2. What you verified vs what you assumed
3. File and line number when referencing existing code

### Never:
- Suggest pandas (use Polars)
- Suggest matplotlib (use Plotly)
- Suggest Reddit or any social media API
- Suggest adding assets beyond the locked 12
- Report in-sample accuracy
- Hallucinate library APIs — verify the actual function signature first

### When you lack verified data:
Say exactly: "I don't have verified data on this. Please search and share the source so I can give you a precise answer."

---

## Key Data Facts from Vaartha (Midterm)

- GPR → GSCPI transmission lag: 1-2 months
- Gallium HHI: 0.77 | Germanium: 0.76 | Rare Earths: 0.71
- GSCPI → semiconductor CapEx r=0.71
- Renewables share → CapEx r=0.82
- GPR → CapEx r=0.56
- Semiconductor/hyperscaler CapEx response lag: 1-2 years after GPR spikes

---

## Timeline

| Week | Dates | Focus |
|------|-------|-------|
| W1 | Apr 14–20 | config.py ✓ · fetchers · validators · loaders · demo mode confirmed offline |
| W2 | Apr 21–27 | regime.py · signals.py · llm.py · kronos.py · all tabs wired |
| W3 | Apr 28–May 4 | integration · demo freeze · dry run · report |
| Presentation | May 5 | 15-20 min, ≤20 slides |
| Submission | May 9 | Report (4+ pages) + code |
