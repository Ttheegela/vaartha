"""
config.py — GeoSentinel Terminal (VARTA)
Single source of truth for all constants, paths, and settings.
Import this at the top of every module. Never hardcode values elsewhere.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Root Paths ────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent
DATA_RAW   = ROOT / "data" / "raw"
DATA_PROC  = ROOT / "data" / "processed"
DATA_DEMO  = ROOT / "data" / "demo"
OUTPUTS    = ROOT / "outputs"
CHARTS     = OUTPUTS / "charts"
TABLES     = OUTPUTS / "tables"

for p in [DATA_RAW, DATA_PROC, DATA_DEMO, CHARTS, TABLES]:
    p.mkdir(parents=True, exist_ok=True)

# ── API Keys ──────────────────────────────────────────────────────────────────
FRED_API_KEY   = os.getenv("FRED_API_KEY", "")
TIINGO_API_KEY = os.getenv("TIINGO_API_KEY", "")
FINNHUB_API_KEY= os.getenv("FINNHUB_API_KEY", "")

# ── Data Windows (Locked) ─────────────────────────────────────────────────────
# Aug 2010: earliest date all 12 tickers have clean data (REMX, LIT, BNO inception)
DATE_TRAIN_START = "2010-08-01"
DATE_TRAIN_END   = "2024-12-31"

# ── 12 Assets (Locked — No Additions) ────────────────────────────────────────
ASSETS = {
    "REMX": {"name": "VanEck Rare Earth/Strategic Metals ETF", "category": "Critical Minerals"},
    "LIT":  {"name": "Global X Lithium and Battery Tech ETF",  "category": "Battery Metals"},
    "ALB":  {"name": "Albemarle Corporation",                   "category": "Lithium Processing"},
    "FCX":  {"name": "Freeport-McMoRan",                       "category": "Copper / Critical Minerals"},
    "NVDA": {"name": "NVIDIA",                                  "category": "AI Hardware"},
    "TSM":  {"name": "Taiwan Semiconductor",                    "category": "Semiconductor Fab"},
    "AMD":  {"name": "Advanced Micro Devices",                  "category": "Semiconductor"},
    "BNO":  {"name": "United States Brent Oil ETF",            "category": "Energy / Hormuz Direct"},
    "XOM":  {"name": "ExxonMobil",                             "category": "Energy"},
    "CVX":  {"name": "Chevron",                                 "category": "Energy"},
    "GLD":  {"name": "SPDR Gold ETF",                          "category": "Crisis Hedge / Safe Haven"},
    "SPY":  {"name": "S&P 500 ETF",                            "category": "Benchmark"},
}
TICKERS = list(ASSETS.keys())  # ['REMX', 'LIT', 'ALB', 'FCX', 'NVDA', 'TSM', 'AMD', 'BNO', 'XOM', 'CVX', 'GLD', 'SPY']

# ── FRED Series (fetched via fredapi) ─────────────────────────────────────────
FRED_SERIES = {
    "OIL_BRENT":   "DCOILBRENTEU",   # Brent crude daily (EIA via FRED)
    "CPI":         "CPIAUCSL",        # Consumer Price Index (BLS via FRED)
    "YIELD_CURVE": "T10Y2Y",          # 10Y-2Y Treasury spread (FRED)
}

# ── External Data Sources (fetched directly — not on FRED public API) ─────────
GPR_URL   = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
GSCPI_URL = "https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/GSCPI_current.xlsx"
# GOLD is not needed separately — GLD ETF already in prices.parquet

# ── Regime Labels ─────────────────────────────────────────────────────────────
REGIME_CRISIS = "Crisis"
REGIME_NORMAL = "Normal"
REGIME_LABELS = [REGIME_NORMAL, REGIME_CRISIS]

# ── HMM / GMM Hyperparameters ─────────────────────────────────────────────────
HMM_N_COMPONENTS   = 2      # 2 regimes: normal vs crisis
HMM_N_ITER         = 100
HMM_COVARIANCE     = "full"
GMM_N_COMPONENTS   = 2
GMM_MAX_ITER       = 300

# ── XGBoost Walk-Forward ──────────────────────────────────────────────────────
WF_TRAIN_MONTHS    = 36     # rolling training window in months
WF_TEST_MONTHS     = 3      # out-of-sample test window per fold
XGB_N_ESTIMATORS   = 200
XGB_MAX_DEPTH      = 4
XGB_LEARNING_RATE  = 0.05
XGB_SUBSAMPLE      = 0.8

# ── Kronos Model ─────────────────────────────────────────────────────────────
KRONOS_MODEL_ID    = "amazon/chronos-t5-base"  # Kronos-base via HuggingFace
KRONOS_CONTEXT_LEN = 512
KRONOS_DEVICE      = "mps"   # Apple Silicon; falls back to cpu

# ── Ollama LLM ────────────────────────────────────────────────────────────────
OLLAMA_HOST        = "http://localhost:11434"
OLLAMA_DEEP_MODEL  = "gemma4:26b"    # Gemma 4 26B MoE (Google, Apr 2025) — deep geopolitical analysis, 128K ctx, ~4B active params
OLLAMA_FAST_MODEL  = "gemma4:e4b"    # Gemma 4 4B efficient (Google, Apr 2025) — rapid headline classification
LLM_MAX_TOKENS     = 512

# ── GeoRisk Score ─────────────────────────────────────────────────────────────
GEORISK_SCALE      = (0, 100)        # output range for all risk scores
GPR_SMOOTH_WINDOW  = 3               # rolling mean months

# ── GDELT Filter Terms (broad geopolitical + supply chain coverage) ───────────
GDELT_FILTER_TERMS = [
    "geopolitical risk", "supply chain", "critical minerals", "semiconductor",
    "trade war", "sanctions", "Ukraine", "Russia", "China", "Taiwan",
    "Iran", "Strait", "oil", "lithium", "rare earth",
]

# ── Visual Standards ──────────────────────────────────────────────────────────
TEAM_PALETTE = {
    "Critical Minerals":  "#00FFB2",
    "Battery Metals":     "#00FFB2",
    "Lithium Processing": "#00FFB2",
    "AI Hardware":        "#FF6B35",
    "Semiconductor Fab":  "#FF6B35",
    "Semiconductor":      "#FF6B35",
    "Energy":             "#A78BFA",
    "Hormuz Direct":      "#A78BFA",
    "Crisis Hedge":       "#FACC15",
    "Benchmark":          "#94A3B8",
    "regime_crisis":      "#EF4444",
    "regime_normal":      "#22C55E",
}

# ── Key Geopolitical Events (for chart annotation) ────────────────────────────
# Full historical set 2010-2024 — used to annotate all time-series charts
KEY_EVENTS = [
    ("2010-12-18", "Arab Spring"),
    ("2011-03-11", "Fukushima Disaster"),
    ("2014-02-27", "Russia-Crimea Annexation"),
    ("2014-06-20", "Oil Price Collapse"),
    ("2015-06-12", "China Market Crash"),
    ("2016-06-23", "Brexit Vote"),
    ("2017-09-03", "N. Korea ICBM Test"),
    ("2018-03-01", "US-China Trade War"),
    ("2019-09-14", "Aramco Attack"),
    ("2020-01-03", "Soleimani Strike"),
    ("2020-03-11", "COVID Declared"),
    ("2022-02-24", "Ukraine Invasion"),
    ("2023-10-07", "Hamas Attack"),
    ("2024-01-12", "Red Sea Disruption"),
]

# ── Demo Mode ─────────────────────────────────────────────────────────────────
DEMO_MODE = True   # default — switches to live fetch when False
