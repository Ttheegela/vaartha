"""
signals.py — GeoSentinel Terminal (VARTA)
Exposes pre-computed XGBoost walk-forward OOS results.
Never reports in-sample metrics — OOS only. All computation done in notebooks.
"""

import polars as pl
from pathlib import Path
from src.utils import log
from config import DATA_PROC, DATA_DEMO


def load_signals(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load XGBoost walk-forward signal predictions.

    Args:
        demo_mode: If True, load from data/demo/. If False, from data/processed/.
    Returns:
        DataFrame with columns: date, ticker, predicted_direction, confidence,
                                actual_direction, regime
    Example:
        df = load_signals(demo_mode=True)
    """
    if demo_mode:
        path = DATA_DEMO / "signals.csv"
        if not path.exists():
            log.warning("Demo signals.csv not found — run scripts/build_demo_bundle.py first")
            return pl.DataFrame()
        return pl.read_csv(path, try_parse_dates=True)
    path = DATA_PROC / "signals.parquet"
    if not path.exists():
        log.warning("signals.parquet not found — run notebook 05_signals.ipynb first")
        return pl.DataFrame()
    return pl.read_parquet(path)


def load_oos_metrics(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load per-ticker per-fold OOS performance metrics.

    Args:
        demo_mode: If True, load from data/demo/. If False, from data/processed/.
    Returns:
        DataFrame with columns: ticker, fold, test_start, test_end,
                                oos_accuracy, oos_precision, oos_recall, n_test
    Example:
        df = load_oos_metrics(demo_mode=True)
    """
    if demo_mode:
        path = DATA_DEMO / "oos_metrics.csv"
        if not path.exists():
            log.warning("Demo oos_metrics.csv not found — run scripts/build_demo_bundle.py first")
            return pl.DataFrame()
        return pl.read_csv(path, try_parse_dates=True)
    path = DATA_PROC / "oos_metrics.parquet"
    if not path.exists():
        log.warning("oos_metrics.parquet not found — run notebook 05_signals.ipynb first")
        return pl.DataFrame()
    return pl.read_parquet(path)


def get_ticker_oos_summary(ticker: str, demo_mode: bool = True) -> dict:
    """
    Return mean OOS metrics aggregated across all folds for one ticker.

    Args:
        ticker: Asset ticker string, e.g. 'NVDA'.
        demo_mode: passed to load_oos_metrics.
    Returns:
        dict with keys: ticker, mean_accuracy, mean_precision, mean_recall, n_folds
    Example:
        s = get_ticker_oos_summary('NVDA')
    """
    df = load_oos_metrics(demo_mode)
    if df.is_empty():
        return {}
    t = df.filter(pl.col("ticker") == ticker)
    if t.is_empty():
        return {}
    return {
        "ticker":         ticker,
        "mean_accuracy":  round(float(t["oos_accuracy"].mean()), 3),
        "mean_precision": round(float(t["oos_precision"].mean()), 3),
        "mean_recall":    round(float(t["oos_recall"].mean()), 3),
        "n_folds":        len(t),
    }


def get_all_tickers_oos_summary(demo_mode: bool = True) -> pl.DataFrame:
    """
    Return aggregated OOS metrics for all tickers, sorted by mean accuracy desc.

    Args:
        demo_mode: passed to load_oos_metrics.
    Returns:
        DataFrame with columns: ticker, mean_accuracy, mean_precision, mean_recall, n_folds
    Example:
        df = get_all_tickers_oos_summary()
    """
    df = load_oos_metrics(demo_mode)
    if df.is_empty():
        return pl.DataFrame()
    return (
        df.group_by("ticker")
        .agg([
            pl.col("oos_accuracy").mean().alias("mean_accuracy"),
            pl.col("oos_precision").mean().alias("mean_precision"),
            pl.col("oos_recall").mean().alias("mean_recall"),
            pl.len().alias("n_folds"),
        ])
        .with_columns([
            pl.col("mean_accuracy").round(3),
            pl.col("mean_precision").round(3),
            pl.col("mean_recall").round(3),
        ])
        .sort("mean_accuracy", descending=True)
    )
