# GeoSentinel Terminal (VARTA)

**Regime-aware geopolitical intelligence and paper trading terminal**

---

## What this is

GeoSentinel Terminal is a Bloomberg-style intelligence dashboard built on top of a historically-validated geopolitical regime detection engine. It identifies whether global markets are in a **Crisis**, **Elevated**, or **Normal** regime using real market signals, and uses that regime classification to drive portfolio rebalancing recommendations and per-asset risk scoring — backed by 14+ years of validated historical data across 16 geopolitical events (2010–2025).

The terminal runs fully offline in demo mode and connects to live market data and Alpaca paper trading when API keys are provided.

---

## The research thesis

This project originated from the Vaartha midterm causal chain analysis:

```
GPR spike → GSCPI pressure → critical mineral supply disruption
         → semiconductor / clean-energy CapEx cuts
         → regime-conditional return divergence across 12 assets
```

Key validated relationships from that analysis:

| Relationship | Correlation | Lag |
|---|---|---|
| GPR → GSCPI | — | 1–2 months |
| GSCPI → semiconductor CapEx | r = 0.71 | — |
| Renewables share → CapEx | r = 0.82 | — |
| GPR → CapEx (direct) | r = 0.56 | 1–2 years |
| Gallium supply concentration (HHI) | 0.77 | — |
| Germanium supply concentration (HHI) | 0.76 | — |
| Rare Earths supply concentration (HHI) | 0.71 | — |

The terminal validates this chain across **16 geopolitical shocks from 2010 to 2025** and demonstrates that regime-conditional return patterns are **persistent and repeatable** — the signal generalises, it is not crisis-specific.

### The 16 validated events

| Date | Event |
|------|-------|
| 2010-12-18 | Arab Spring |
| 2011-03-11 | Fukushima Disaster |
| 2014-02-27 | Russia–Crimea Annexation |
| 2014-06-20 | Oil Price Collapse |
| 2015-06-12 | China Market Crash |
| 2016-06-23 | Brexit Vote |
| 2017-09-03 | North Korea ICBM Test |
| 2018-03-01 | US–China Trade War |
| 2019-09-14 | Aramco Attack |
| 2020-01-03 | Soleimani Strike |
| 2020-03-11 | COVID Declared |
| 2022-02-24 | Ukraine Invasion |
| 2023-10-07 | Hamas Attack |
| 2024-01-12 | Red Sea Disruption |
| 2025-01-19 | Gaza Ceasefire |
| 2025-04-02 | US Liberation Day Tariffs |

---

## Why we built it this way

**Historical prediction of historical outcomes.** Following professor feedback, results are framed with a clean train/test split. The engine applies historically-derived thresholds to live market signals without modelling an ongoing live crisis.

**Regime detection, not price prediction.** The signal is a daily-resolution macro regime label. This mirrors how institutional macro funds use regime models — for strategic allocation shifts over days to weeks, not millisecond execution. The rebalancing engine generates target weight orders that a prime broker would execute via TWAP/VWAP.

**Offline-first.** The terminal works fully without any API keys. All demo data is pre-built into `data/demo/`. Critical for presentations and reproducible grading.

**Polars everywhere.** Every dataframe operation in app code uses Polars. pandas is only used as a thin adapter in `kronos_live.py` because the Kronos model requires it internally.

---

## Asset universe (12 assets, locked)

| Ticker | Name | Category | GeoRisk Sensitivity |
|--------|------|----------|-------------------|
| TSM | Taiwan Semiconductor | Semiconductor Fab | 1.40 (anchor) |
| REMX | VanEck Rare Earth/Strategic Metals | Critical Minerals | 1.35 |
| LIT | Global X Lithium & Battery Tech | Battery Metals | 1.30 |
| ALB | Albemarle Corporation | Lithium Processing | 1.25 |
| FCX | Freeport-McMoRan | Critical Minerals | 1.20 |
| BNO | United States Brent Oil Fund | Hormuz Direct | 1.20 |
| NVDA | NVIDIA Corporation | AI Hardware | 1.15 |
| AMD | Advanced Micro Devices | Semiconductor | 1.10 |
| XOM | ExxonMobil | Energy | 1.10 |
| CVX | Chevron | Energy | 1.05 |
| SPY | SPDR S&P 500 ETF | Benchmark | 0.70 |
| GLD | SPDR Gold Shares | Crisis Hedge | 0.55 |

Data window: **2010-08-01 → present (live, rolling)** — all 12 tickers have clean data from 2010-08-01 with no nulls. REMX, LIT, and BNO inception dates (mid-2010) are the binding constraint.

---

## GeoRisk Score

Every asset gets a live GeoRisk Score (0–100):

```
GeoRisk = (sensitivity / 1.40) × (40 + 60 × crisis_prob) × 100
```

- **`sensitivity`** — asset's inherent exposure derived from the GPR → supply chain causal chain analysis
- **`crisis_prob`** — live P(Crisis) from the regime engine, refreshed every 5 minutes
- Normal regime (P=0): TSM = 40, GLD = 16
- Full crisis (P=100%): TSM = 100, GLD = 39

---

## Regime detection

**Live signal (primary):** Three market proxies from daily OHLCV via yfinance, `@st.cache_data(ttl=300)`:

| Signal | Weight | Crisis threshold |
|--------|--------|-----------------|
| Brent Oil 30-day annualized realized vol | 45% | > 42% |
| SPY 20-day drawdown from 252-day rolling high | 35% | < −12% |
| Gold/Oil ratio trend (safe-haven flight) | 20% | ratio > 28 or +15% over 30d |

Composite: `prob = 0.45×vol_signal + 0.35×dd_signal + 0.20×gold_oil_signal`
Labels: **Crisis** (≥ 0.55) · **Elevated** (≥ 0.30) · **Normal** (below 0.30)

**Historical fallback:** Pre-computed HMM/GMM regime labels from the 2010–present training window in `data/demo/`.

---

## Terminal tabs

| Tab | File | Content |
|-----|------|---------|
| PORTFOLIO | `tab3_portfolio.py` | Live Alpaca paper holdings, P&L, Sharpe/Sortino/VaR metrics, regime stress test, regime rebalancing engine, efficient frontier (Monte Carlo), configurable alerts engine |
| LIVE NEWS | `tab1_news.py` | Alpaca + Finnhub + WSJ/MarketWatch RSS, Polymarket signals, live FRED macro panel (5 indicators + yield curve), auto-refresh every 2 min |
| RESEARCH | `tab2_research.py` | Per-ticker DCF model, analyst consensus, Kronos OHLCV 21-day forecast, regime overlay, 5-period price chart with MA-50/MA-200 |
| SCENARIO | `tab8_scenario.py` | GPR shock simulator — live yfinance sensitivities, live FRED causal chain coefficients, live Alpaca portfolio weights, comparable historical events auto-detected from live GPR index |
| SETTINGS | `tab4_settings.py` | Alpaca API credentials, asset universe selector, strategy preferences, GeoRisk sensitivity viewer |

All regime data, portfolio value, day P&L, and buying power are shown in the persistent **top bar** across all tabs. No sidebar.

---

## Kronos OHLCV forecast

The Research tab uses **shiyu-coder/Kronos** (AAAI 2026) — a decoder-only Transformer trained on OHLCV candlestick data from 45+ global exchanges. Model: `NeoQuasar/Kronos-small` (24.7M parameters).

Unlike general time-series models, Kronos understands OHLCV structure: it forecasts full candlestick bars (open, high, low, close, volume) and enforces OHLC validity constraints. It forecasts **21 trading days** (~1 month) ahead. When the selected chart period is 1M (only ~21 bars), inference automatically uses a 1Y context window while the chart axis stays pinned to the 1M view.

Kronos degrades gracefully if the repo is not cloned — the tab falls back to pre-computed demo forecasts.

---

## Tech stack

| Layer | Tool |
|-------|------|
| Frontend | Streamlit 1.42+ |
| Charts | Plotly only (no matplotlib) |
| Maps | Folium + streamlit-folium |
| DataFrames | Polars (never pandas in app code) |
| SQL queries | DuckDB |
| Market data | yfinance, FRED API |
| News | Alpaca News API, Finnhub, WSJ/MarketWatch RSS |
| Crowd signals | Polymarket REST API |
| GPR index | Caldara-Iacoviello (matteoiacoviello.com, daily, live fetch) |
| Regime detection | HMM / GMM (hmmlearn / sklearn) |
| Walk-forward signal | XGBoost |
| OHLCV foundation model | shiyu-coder/Kronos (AAAI 2026, NeoQuasar/Kronos-small) |
| LLM crisis scoring (offline only) | Ollama — Gemma 4 26B (deep) + Gemma 4 4B (fast) |
| Persistent settings | SQLite via stdlib `sqlite3` |
| Brokerage | Alpaca paper trading (alpaca-py) |
| Device | Apple M3 Pro, MPS backend (auto-falls back to CPU) |

---

## Project structure

```
VARTA/
├── app.py                          # Streamlit entry point — top bar, CSS, 5 tabs
├── config.py                       # All constants — tickers, dates, thresholds, weights
├── requirements.txt
│
├── src/
│   ├── data/
│   │   ├── fetchers.py             # Live API calls — Alpaca, yfinance, Finnhub, FRED, GPR
│   │   ├── loaders.py              # Reads pre-processed parquet/CSV from data/demo/
│   │   └── validators.py           # Schema validation on loaded data
│   │
│   ├── db/
│   │   └── settings_store.py       # SQLite-backed persistent key-value settings
│   │
│   ├── models/
│   │   ├── regime.py               # Regime series loader, quant risk stack (Kelly, VaR, Stoikov)
│   │   ├── regime_live.py          # Live Brent vol + SPY DD + Gold/Oil proxy
│   │   ├── signals.py              # XGBoost walk-forward signal (OOS metrics only)
│   │   ├── kronos.py               # Kronos historical forecast wrapper
│   │   ├── kronos_live.py          # Live Kronos OHLCV forecast (shiyu-coder/Kronos)
│   │   ├── portfolio.py            # Risk metrics, regime stress test, efficient frontier
│   │   ├── trader.py               # Regime order generation + Alpaca paper execution
│   │   └── llm.py                  # Loads pre-computed Gemma crisis scores (read-only)
│   │
│   ├── tabs/
│   │   ├── tab1_news.py            # Live intelligence feed + FRED macro panel
│   │   ├── tab2_research.py        # Equity research + DCF + live Kronos forecast
│   │   ├── tab3_portfolio.py       # Portfolio + regime rebalancing engine + alerts
│   │   ├── tab4_settings.py        # User settings + credential management
│   │   └── tab8_scenario.py        # GPR shock simulator + causal chain propagation
│   │
│   └── utils.py                    # set_dark_theme(), annotate_events(), render_error_card(), log
│
├── data/
│   └── demo/                       # Pre-built offline demo bundle (committed)
│
├── scripts/
│   └── build_demo_bundle.py        # Regenerates data/demo/ from scratch
│
└── notebooks/                      # Analysis notebooks (cell outputs cleared)
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Ttheegela/vaartha.git
cd vaartha
```

### 2. Install Python dependencies

Requires Python 3.12. Tested on macOS ARM64.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Clone Kronos (optional — required for live OHLCV forecasts only)

```bash
git clone https://github.com/shiyu-coder/Kronos src/models/kronos_repo
```

On first use the model downloads `NeoQuasar/Kronos-small` (~100MB) from HuggingFace and caches it locally. If not cloned, the Research tab falls back to pre-computed demo forecasts.

### 4. Set API keys (optional — app works in demo mode without them)

```bash
cp .env.example .env
# edit .env with your keys
```

```
ALPACA_API_KEY=your_paper_key
ALPACA_SECRET_KEY=your_paper_secret
FINNHUB_API_KEY=your_finnhub_key
FRED_API_KEY=your_fred_key
```

Paper trading keys are free at [app.alpaca.markets](https://app.alpaca.markets). Finnhub free tier is sufficient.

### 5. Run

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. In demo mode (default) all historical data loads from `data/demo/` with no API calls required.

---

## Seeding the paper portfolio

After connecting Alpaca keys in Settings, buy these positions manually on [app.alpaca.markets](https://app.alpaca.markets) to activate the portfolio tab:

| Ticker | Amount |
|--------|--------|
| NVDA | $12,000 |
| TSM | $10,000 |
| SPY | $10,000 |
| GLD | $8,000 |
| REMX | $8,000 |
| LIT | $7,000 |
| XOM | $7,000 |
| FCX | $7,000 |
| ALB | $6,000 |
| AMD | $6,000 |
| CVX | $5,000 |
| BNO | $4,000 |
