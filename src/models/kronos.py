"""
kronos.py — GeoSentinel Terminal (VARTA)
Exposes pre-computed Kronos (Chronos T5-base) zero-shot price forecasts.
All inference done in notebooks/07_kronos_forecasts.ipynb — never at runtime.
"""

import polars as pl
from pathlib import Path
from src.utils import log
from config import DATA_PROC, DATA_DEMO, TICKERS


def load_kronos(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load Kronos 21-day price forecasts for all 12 tickers.

    Args:
        demo_mode: If True, load from data/demo/. If False, from data/processed/.
    Returns:
        DataFrame with columns: ticker, forecast_date, mean, low_80, high_80, last_close
    Example:
        df = load_kronos(demo_mode=True)
    """
    if demo_mode:
        path = DATA_DEMO / "kronos.csv"
        if not path.exists():
            log.warning("Demo kronos.csv not found — run scripts/build_demo_bundle.py first")
            return pl.DataFrame()
        return pl.read_csv(path, try_parse_dates=True)
    path = DATA_PROC / "kronos_forecasts.parquet"
    if not path.exists():
        log.warning("kronos_forecasts.parquet not found — run notebooks/07_kronos_forecasts.ipynb first")
        return pl.DataFrame()
    return pl.read_parquet(path)


def get_ticker_forecast(ticker: str, demo_mode: bool = True) -> pl.DataFrame:
    """
    Return the 21-day Kronos forecast for a single ticker.

    Args:
        ticker: Asset ticker string, e.g. 'NVDA'.
        demo_mode: passed to load_kronos.
    Returns:
        DataFrame with columns: forecast_date, mean, low_80, high_80, last_close
        Sorted by forecast_date ascending.
    Example:
        df = get_ticker_forecast('TSM')
    """
    df = load_kronos(demo_mode)
    if df.is_empty():
        return df
    return df.filter(pl.col("ticker") == ticker).sort("forecast_date")


def get_forecast_summary(demo_mode: bool = True) -> pl.DataFrame:
    """
    Compute per-ticker 21-day expected return from Kronos forecasts.

    Args:
        demo_mode: passed to load_kronos.
    Returns:
        DataFrame with columns: ticker, last_close, forecast_end_mean,
                                expected_return_pct
        Sorted by expected_return_pct descending.
    Example:
        df = get_forecast_summary()
    """
    df = load_kronos(demo_mode)
    if df.is_empty():
        return pl.DataFrame()

    summaries = []
    for ticker in TICKERS:
        t = df.filter(pl.col("ticker") == ticker).sort("forecast_date")
        if t.is_empty():
            continue
        last_close = float(t["last_close"][0])
        end_mean   = float(t["mean"][-1])
        exp_ret    = ((end_mean - last_close) / last_close * 100) if last_close > 0 else 0.0
        summaries.append({
            "ticker":              ticker,
            "last_close":          round(last_close, 2),
            "forecast_end_mean":   round(end_mean, 2),
            "expected_return_pct": round(exp_ret, 2),
        })

    if not summaries:
        return pl.DataFrame()
    return (
        pl.DataFrame(summaries)
        .sort("expected_return_pct", descending=True)
    )
