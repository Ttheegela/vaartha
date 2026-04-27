# GeoSentinel Terminal (VARTA)

**Regime-Aware Geopolitical Risk Intelligence for Critical Mineral Investors**  
Team 7 Lambda · Rutgers Advanced Python SP2026 · Final Project  
Tarun Theegela · Sai Raunak Bidesi · Chaitanya Deogaonkar · Satwik Nadipelli

---

## What This Is

VARTA is a Bloomberg-style geopolitical risk intelligence terminal built on the causal chain established in our Vaartha midterm:

```
Geopolitical Shock (GPR spike)
      ↓  1–2 month lag
Supply Chain Pressure (GSCPI rise)
      ↓
Mineral Supply Disruption (HHI-concentrated commodities)
      ↓  1–2 year lag
Corporate CapEx Restructuring (semiconductor + hyperscaler response)
```

Validated across **14 independent geopolitical events from 2010–2024** (Arab Spring → Red Sea Disruption).  
Data window: **2010-08-01 → 2024-12-31**. No live data — historical prediction of historical outcomes.

---

## Key Findings (from Vaartha midterm)

| Signal | Value |
|--------|-------|
| GPR → GSCPI transmission lag | 1–2 months |
| Gallium supply HHI | 0.77 (near-monopoly) |
| Germanium supply HHI | 0.76 |
| Rare Earths HHI | 0.71 |
| GSCPI → semiconductor CapEx correlation | r = 0.71 |
| Renewables share → CapEx correlation | r = 0.82 |
| GPR → CapEx correlation | r = 0.56 |
| CapEx response lag after GPR spike | 1–2 years |

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Frontend | Streamlit 1.42+ |
| Charts | Plotly (dark theme throughout) |
| Maps | Folium + streamlit-folium |
| DataFrames | Polars (never pandas) |
| SQL queries | DuckDB |
| Price data | yfinance |
| Macro data | FRED API (GPR, GSCPI, Brent, CPI, T10Y2Y) |
| News data | GDELT Project (8,614 headlines) |
| Regime detection | HMM (hmmlearn) — Crisis / Normal labels |
| Signal model | XGBoost walk-forward OOS (never in-sample) |
| Foundation model | **Kronos T5-base** (Amazon Chronos, AAAI 2026) — price forecasting |
| LLM scoring | **Ollama Gemma 4 12B/4B** — GDELT headline sentiment, pre-computed |
| HPC | **Amarel (Rutgers HPC)** — SLURM job for Gemma 4 scoring (12h, 583KB output) |
| Device | Apple M3 Pro, MPS backend |

---

## 12 Tracked Assets

| Ticker | Description |
|--------|-------------|
| REMX | VanEck Rare Earth/Strategic Metals ETF |
| LIT | Global X Lithium & Battery Tech ETF |
| ALB | Albemarle (lithium producer) |
| FCX | Freeport-McMoRan (copper) |
| NVDA | NVIDIA |
| TSM | Taiwan Semiconductor |
| AMD | Advanced Micro Devices |
| BNO | United States Brent Oil Fund |
| XOM | ExxonMobil |
| CVX | Chevron |
| GLD | SPDR Gold Shares |
| SPY | S&P 500 benchmark |

All 12 have clean daily data from **2010-08-01** — no nulls across the full window.

---

## Data Pipeline (8 Notebooks)

| Notebook | Output |
|----------|--------|
| `01_fetch_prices` | `prices.parquet` — 43,474 rows, 12 tickers |
| `02_fetch_fred` | `fred.parquet` — GPR, GSCPI, Brent, CPI, T10Y2Y |
| `03_fetch_gdelt` | `gdelt.parquet` — 8,614 headlines 2010–2024 |
| `04_regime_detection` | `regimes.parquet` — HMM Crisis/Normal labels + probability |
| `05_xgboost_signals` | `signals.parquet` + `oos_metrics.parquet` — walk-forward OOS |
| `06_llm_scoring` | `gdelt_scored.parquet` — Gemma 4 scores (run on Amarel SLURM) |
| `07_kronos_forecasts` | `kronos_forecasts.parquet` — 252 rows, 0 nulls |
| `08_integration` | `data/demo/*.csv` — frozen offline demo bundle |

---

## How Amarel Was Used

GDELT headline scoring (NB06) requires running Gemma 4 12B across 8,614 headlines — too slow for a laptop. We submitted a SLURM batch job to Rutgers HPC (Amarel):

```bash
# Job spec: 12h walltime, 40GB RAM, 4 CPU, no GPU (Gemma via Ollama CPU on HPC)
sbatch scripts/amarel_score_gdelt.sh
# Job ID: 51107782 — completed successfully
# Output pulled back via SCP: scp tt633@amarel.rutgers.edu:~/gdelt_scored.parquet data/processed/
```

This produced `gdelt_scored.parquet` (583KB) with LLM sentiment scores for every headline, which the app reads from the frozen demo CSV at runtime.

---

## 5 Dashboard Tabs

| Tab | Content |
|-----|---------|
| **1 — Watchlist** | 12-asset price table, regime banner, normalized price index (regime-shaded + 14 events), GPR chart |
| **2 — Crisis Timeline** | GPR+GSCPI dual-axis, event zoom, GDELT headline table, LLM sentiment series, 14-event summary |
| **3 — Regime Analysis** | HMM regime probability series, KPI cards, crisis shading on SPY, conditional returns, 6-model risk stack |
| **4 — Signals & Forecasts** | XGBoost OOS leaderboard, per-fold accuracy, Kronos fan chart (mean + 80% CI), expected return bar |
| **5 — Supply Chain Map** | Mineral production sites, shipping chokepoints, 4 trade routes, HHI country circles |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Ttheegela/vaartha.git
cd vaartha

# 2. Create conda env (Python 3.12)
conda activate lambda    # or: python3.12 -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env template and fill in keys
cp .env.example .env
# Fill in: FRED_API_KEY (free at fred.stlouisfed.org)

# 5. Run app in demo mode (offline, no API keys needed)
streamlit run app.py
```

### Demo Mode (offline)

`DEMO_MODE = True` is the default in `config.py`. The app loads from `data/demo/*.csv` — no internet required. Demo bundle is pre-built and committed.

---

## Project Structure

```
vaartha/
├── app.py                  Streamlit entry point
├── config.py               All constants — single source of truth
├── src/
│   ├── data/
│   │   ├── fetchers.py     yfinance, FRED, GDELT fetch logic
│   │   ├── loaders.py      load_prices, load_fred, load_gdelt, load_signals, load_kronos
│   │   └── validators.py   schema + null checks
│   ├── models/
│   │   ├── regime.py       get_current_regime, get_regime_stats, get_regime_conditional_returns
│   │   ├── signals.py      load_signals, load_oos_metrics, get_ticker_oos_summary
│   │   ├── llm.py          get_scored_headlines, get_event_headlines, get_top_headlines
│   │   └── kronos.py       load_kronos, get_ticker_forecast, get_forecast_summary
│   ├── tabs/
│   │   ├── tab1_watchlist.py
│   │   ├── tab2_crisis_timeline.py
│   │   ├── tab3_regime.py
│   │   ├── tab4_signals.py
│   │   └── tab5_maps.py
│   └── utils.py            dark_theme, annotate_events, logger
├── notebooks/              01–08 data pipeline
├── scripts/
│   ├── amarel_score_gdelt.py   Gemma 4 scoring script (run on HPC)
│   ├── amarel_score_gdelt.sh   SLURM batch job spec
│   └── build_report.py         python-docx report builder
├── data/
│   ├── raw/                downloaded source files (gitignored)
│   ├── processed/          Parquet files (gitignored)
│   └── demo/               offline CSV fallback (gitignored)
└── outputs/
    ├── charts/             .png charts + .txt captions
    └── tables/
```

---

## Team & Ownership

| Name | NetID | Primary Tabs |
|------|-------|--------------|
| Tarun Theegela | tt633 | Tab 1, Tab 3, pipeline integration |
| Sai Raunak Bidesi | ssb196 | Tab 4 (Signals & Forecasts) |
| Chaitanya Deogaonkar | cmd517 | Tab 2 (Crisis Timeline) |
| Satwik Nadipelli | srn91 | Tab 5 (Supply Chain Map) |

**Presentation:** May 4, 2026 · **Full Submission:** May 9, 2026
