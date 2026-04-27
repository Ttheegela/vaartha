"""
loaders.py — GeoSentinel Terminal (VARTA)
Unified data access layer. All tab files call loaders — never fetchers directly.
Switches between live fetch and demo CSV fallback based on demo_mode flag.
Demo mode must work fully offline. Build and verify before writing model code.
"""

import polars as pl
from pathlib import Path
from src.utils import log
from config import DATA_PROC, DATA_DEMO


def load_prices(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load asset prices. Returns processed Parquet in live mode, demo CSV as fallback.

    Args:
        demo_mode: If True, load from data/demo/. If False, load from data/processed/.
    Returns:
        DataFrame with columns: date, ticker, close, return_1d
    Example:
        df = load_prices(demo_mode=True)
    """
    if demo_mode:
        path = DATA_DEMO / "prices.csv"
        if not path.exists():
            log.warning("Demo prices CSV not found — run scripts/build_demo_bundle.py first")
            return pl.DataFrame()
        return pl.read_csv(path, try_parse_dates=True)
    path = DATA_PROC / "prices.parquet"
    if not path.exists():
        log.warning("Processed prices.parquet not found — run scripts/fetch_all_data.py first")
        return pl.DataFrame()
    return pl.read_parquet(path)


def load_fred(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load FRED series (GPR, GSCPI, Brent, CPI).

    Args:
        demo_mode: If True, load from data/demo/. If False, load from data/processed/.
    Returns:
        DataFrame with columns: date, series_id, value
    Example:
        df = load_fred(demo_mode=True)
    """
    if demo_mode:
        path = DATA_DEMO / "fred.csv"
        if not path.exists():
            log.warning("Demo fred CSV not found — run scripts/build_demo_bundle.py first")
            return pl.DataFrame()
        return pl.read_csv(path, try_parse_dates=True)
    path = DATA_PROC / "fred.parquet"
    if not path.exists():
        log.warning("Processed fred.parquet not found")
        return pl.DataFrame()
    return pl.read_parquet(path)


def load_gdelt(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load GDELT Iran/Hormuz headlines.

    Args:
        demo_mode: If True, load from data/demo/. If False, load from data/processed/.
    Returns:
        DataFrame with columns: date, headline, tone, llm_score
    Example:
        df = load_gdelt(demo_mode=True)
    """
    if demo_mode:
        path = DATA_DEMO / "gdelt.csv"
        if not path.exists():
            log.warning("Demo gdelt CSV not found — run scripts/build_demo_bundle.py first")
            return pl.DataFrame()
        return pl.read_csv(path, try_parse_dates=True)
    path = DATA_PROC / "gdelt.parquet"
    if not path.exists():
        log.warning("Processed gdelt.parquet not found")
        return pl.DataFrame()
    return pl.read_parquet(path)


def load_regimes(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load pre-computed regime labels (output of regime.py).

    Args:
        demo_mode: If True, load from data/demo/. If False, load from data/processed/.
    Returns:
        DataFrame with columns: date, regime_label, regime_prob
    Example:
        df = load_regimes(demo_mode=True)
    """
    if demo_mode:
        path = DATA_DEMO / "regimes.csv"
        if not path.exists():
            log.warning("Demo regimes CSV not found")
            return pl.DataFrame()
        return pl.read_csv(path, try_parse_dates=True)
    path = DATA_PROC / "regimes.parquet"
    if not path.exists():
        log.warning("Processed regimes.parquet not found")
        return pl.DataFrame()
    return pl.read_parquet(path)


def load_signals(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load XGBoost walk-forward OOS signal predictions.

    Args:
        demo_mode: If True, load from data/demo/. If False, load from data/processed/.
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
        log.warning("signals.parquet not found — run notebooks/05_signals.ipynb first")
        return pl.DataFrame()
    return pl.read_parquet(path)


def load_oos_metrics(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load per-ticker per-fold OOS performance metrics.

    Args:
        demo_mode: If True, load from data/demo/. If False, load from data/processed/.
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
        log.warning("oos_metrics.parquet not found — run notebooks/05_signals.ipynb first")
        return pl.DataFrame()
    return pl.read_parquet(path)


def load_kronos(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load Kronos (Chronos T5-base) 21-day price forecasts.

    Args:
        demo_mode: If True, load from data/demo/. If False, load from data/processed/.
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
