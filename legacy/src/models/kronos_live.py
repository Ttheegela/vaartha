"""
kronos_live.py — GeoSentinel Terminal (VARTA)
Wraps shiyu-coder/Kronos (NeoQuasar/Kronos-small) for live OHLCV forecasting.

Kronos is a financial market foundation model trained on 45+ exchanges.
Architecture: specialized OHLCV tokenizer (BSQuantizer) + decoder-only Transformer.
Paper: "Kronos: A Foundation Model for Financial Market Prediction" (AAAI 2026)
Repo:  https://github.com/shiyu-coder/Kronos
HF:    NeoQuasar/Kronos-small (24.7M params), NeoQuasar/Kronos-Tokenizer-base

NOTE: This module uses pandas internally because KronosPredictor requires it.
      All VARTA modules outside this file remain pure Polars.
"""

import sys
import logging
from pathlib import Path
from datetime import timedelta

import polars as pl
import pandas as pd  # required by KronosPredictor.predict() — not used elsewhere
import numpy as np

from config import (
    KRONOS_MODEL_ID, KRONOS_TOKENIZER_ID,
    KRONOS_CONTEXT_LEN, KRONOS_PRED_LEN, KRONOS_SAMPLE_COUNT, KRONOS_DEVICE,
)

log = logging.getLogger(__name__)

# ── Kronos repo on sys.path ───────────────────────────────────────────────────
KRONOS_REPO = Path(__file__).parent / "kronos_repo"

_predictor = None   # module-level singleton — loaded once per interpreter process
_load_error: str | None = None


def _ensure_repo_on_path() -> None:
    """Add the cloned Kronos repo to sys.path so `from model import ...` works."""
    repo_str = str(KRONOS_REPO)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def is_available() -> bool:
    """Return True if the Kronos repo is present and importable."""
    if not KRONOS_REPO.exists():
        return False
    _ensure_repo_on_path()
    try:
        import model  # noqa: F401
        return True
    except ImportError:
        return False


def _detect_device() -> str:
    """Resolve the best available device: mps → cuda → cpu."""
    import torch
    if KRONOS_DEVICE == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def load_predictor():
    """
    Load KronosPredictor once and cache at module level.

    Downloads NeoQuasar/Kronos-small + NeoQuasar/Kronos-Tokenizer-base from
    HuggingFace on first call; subsequent calls return the cached predictor.

    Returns:
        KronosPredictor instance, or None if load failed.
    """
    global _predictor, _load_error
    if _predictor is not None:
        return _predictor
    if _load_error is not None:
        return None  # already tried and failed

    _ensure_repo_on_path()
    try:
        from model import KronosTokenizer, Kronos, KronosPredictor
    except ImportError as e:
        _load_error = f"Kronos import failed: {e}"
        log.error(_load_error)
        return None

    try:
        device = _detect_device()
        log.info(f"Loading Kronos tokenizer from {KRONOS_TOKENIZER_ID}...")
        tokenizer = KronosTokenizer.from_pretrained(KRONOS_TOKENIZER_ID)
        log.info(f"Loading Kronos model from {KRONOS_MODEL_ID}...")
        model_obj = Kronos.from_pretrained(KRONOS_MODEL_ID)
        _predictor = KronosPredictor(
            model=model_obj,
            tokenizer=tokenizer,
            device=device,
            max_context=KRONOS_CONTEXT_LEN,
        )
        log.info(f"Kronos ready on device={device}")
        return _predictor
    except Exception as e:
        _load_error = f"Kronos load failed: {e}"
        log.error(_load_error)
        return None


def get_load_error() -> str | None:
    """Return the last Kronos load error string, or None if clean."""
    return _load_error


def generate_forecast(hist: pl.DataFrame, pred_len: int = KRONOS_PRED_LEN) -> pl.DataFrame | None:
    """
    Run the Kronos OHLCV forecast on historical price data.

    Args:
        hist: Polars DataFrame with columns: date (pl.Date), open, high, low, close, volume.
              Rows must be sorted chronologically. Min 30 rows recommended.
        pred_len: Number of future trading days to forecast (default 21 ≈ 1 month).

    Returns:
        Polars DataFrame with columns: date (pl.Date), open, high, low, close, volume
        indexed by future business days, or None on failure.

    Example:
        hist = _get_price_history("NVDA", "1y")
        fc = generate_forecast(hist, pred_len=21)
    """
    predictor = load_predictor()
    if predictor is None:
        return None

    if hist.is_empty() or len(hist) < 30:
        log.warning("Kronos: insufficient history (need ≥30 bars)")
        return None

    try:
        # ── Build pandas input (Kronos API requires pandas) ───────────────────
        hist_sorted = hist.sort("date")

        # Context window: use up to KRONOS_CONTEXT_LEN most recent bars
        ctx_len  = min(len(hist_sorted), KRONOS_CONTEXT_LEN)
        hist_ctx = hist_sorted.tail(ctx_len)

        # Convert Polars → pandas for Kronos API
        hist_pd = hist_ctx.to_pandas()
        hist_pd["date"] = pd.to_datetime(hist_pd["date"])
        hist_pd = hist_pd.set_index("date")

        # Ensure required columns exist; add amount if missing
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in hist_pd.columns:
                hist_pd[col] = 0.0
        if "amount" not in hist_pd.columns:
            hist_pd["amount"] = hist_pd["volume"] * hist_pd[["open","high","low","close"]].mean(axis=1)

        # calc_time_stamps() inside Kronos expects pandas Series with .dt accessor
        x_timestamp = pd.Series(pd.DatetimeIndex(hist_pd.index))

        # ── Future timestamps: pred_len business days after last historical bar
        last_date    = x_timestamp.iloc[-1]
        future_dates = pd.bdate_range(
            start=last_date + timedelta(days=1),
            periods=pred_len,
        )
        y_timestamp = pd.Series(future_dates)

        # ── Run Kronos inference ──────────────────────────────────────────────
        pred_df = predictor.predict(
            df=hist_pd,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=1.0,
            top_k=0,
            top_p=0.9,
            sample_count=KRONOS_SAMPLE_COUNT,
            verbose=False,
        )

        # ── Convert back to Polars ────────────────────────────────────────────
        pred_df = pred_df.reset_index()
        pred_df = pred_df.rename(columns={"index": "date"})
        pred_df["date"] = pred_df["date"].dt.date

        result = pl.from_pandas(pred_df[["date", "open", "high", "low", "close", "volume"]])
        result = result.with_columns(pl.col("date").cast(pl.Date))

        # Clamp: ensure high ≥ max(open,close) and low ≤ min(open,close)
        result = result.with_columns([
            pl.max_horizontal("high", "open", "close").alias("high"),
            pl.min_horizontal("low", "open", "close").alias("low"),
        ])

        return result

    except Exception as e:
        log.error(f"Kronos inference failed: {e}", exc_info=True)
        return None
