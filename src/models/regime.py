"""
regime.py — GeoSentinel Terminal (VARTA)
Regime detection using HMM + GMM on GPR and Brent volatility features.
Exposes pre-computed regime data and summary statistics.
All computation is pre-run via notebooks — this module only accesses results.
"""

import polars as pl
from src.data.loaders import load_regimes, load_fred, load_prices
from src.utils import log
from config import REGIME_CRISIS, REGIME_NORMAL, DATE_TRAIN_START, DATE_TRAIN_END


def get_regime_series(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load regime label time series with crisis probability.

    Args:
        demo_mode: If True, load from data/demo/. If False, from data/processed/.
    Returns:
        DataFrame with columns: date, regime_label, regime_prob
    Example:
        df = get_regime_series(demo_mode=True)
    """
    return load_regimes(demo_mode)


def get_current_regime(demo_mode: bool = True) -> dict:
    """
    Return the most recent regime label and probability.

    Args:
        demo_mode: passed to get_regime_series.
    Returns:
        dict with keys: label (str), prob (float), date (str)
    Example:
        r = get_current_regime()
        # {'label': 'Crisis', 'prob': 0.87, 'date': '2024-12-31'}
    """
    df = get_regime_series(demo_mode)
    if df.is_empty():
        return {"label": REGIME_NORMAL, "prob": 0.5, "date": "N/A"}
    latest = df.sort("date").tail(1)
    return {
        "label": latest["regime_label"][0],
        "prob":  float(latest["regime_prob"][0]),
        "date":  str(latest["date"][0]),
    }


def get_regime_stats(demo_mode: bool = True) -> dict:
    """
    Compute regime distribution statistics over the training window.

    Args:
        demo_mode: passed to get_regime_series.
    Returns:
        dict with keys: crisis_pct, normal_pct, n_crisis_days, n_normal_days,
                        avg_crisis_duration_days, n_episodes
    Example:
        stats = get_regime_stats()
    """
    df = get_regime_series(demo_mode)
    if df.is_empty():
        return {}

    counts = df.group_by("regime_label").agg(pl.len().alias("n"))
    total = len(df)
    crisis_n = counts.filter(pl.col("regime_label") == REGIME_CRISIS)["n"]
    normal_n = counts.filter(pl.col("regime_label") == REGIME_NORMAL)["n"]
    crisis_count = int(crisis_n[0]) if len(crisis_n) > 0 else 0
    normal_count = int(normal_n[0]) if len(normal_n) > 0 else 0

    # Count contiguous crisis episodes
    labels = df.sort("date")["regime_label"].to_list()
    episodes = sum(
        1 for i in range(len(labels))
        if labels[i] == REGIME_CRISIS and (i == 0 or labels[i - 1] != REGIME_CRISIS)
    )
    avg_duration = (crisis_count / episodes) if episodes > 0 else 0

    return {
        "crisis_pct":             round(crisis_count / total * 100, 1),
        "normal_pct":             round(normal_count / total * 100, 1),
        "n_crisis_days":          crisis_count,
        "n_normal_days":          normal_count,
        "avg_crisis_duration_days": round(avg_duration, 1),
        "n_episodes":             episodes,
    }


def get_regime_conditional_returns(demo_mode: bool = True) -> pl.DataFrame:
    """
    Compute mean 1-day return per regime for each of the 12 assets.

    Args:
        demo_mode: passed to loaders.
    Returns:
        DataFrame with columns: ticker, regime_label, mean_return, n
    Example:
        df = get_regime_conditional_returns()
    """
    prices  = load_prices(demo_mode)
    regimes = get_regime_series(demo_mode)
    if prices.is_empty() or regimes.is_empty():
        return pl.DataFrame()

    joined = prices.join(
        regimes.select(["date", "regime_label"]),
        on="date",
        how="left",
    ).drop_nulls("regime_label")

    return (
        joined.group_by(["ticker", "regime_label"])
        .agg([
            pl.col("return_1d").mean().alias("mean_return"),
            pl.len().alias("n"),
        ])
        .sort(["ticker", "regime_label"])
    )
