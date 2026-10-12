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
    Return current regime using live market proxy (primary) with historical fallback.

    Live proxy: Brent 30-day vol + SPY drawdown + Gold/Oil ratio via yfinance.
    Historical fallback: last row of pre-computed regime CSV (frozen at 2024-12-31).

    Args:
        demo_mode: controls historical fallback source (demo CSV vs processed parquet).
    Returns:
        dict with keys: label (str), prob (float), date (str), source (str),
                        and optional live signal details.
    Example:
        r = get_current_regime()
        # {'label': 'Normal', 'prob': 0.18, 'date': '2026-04-30', 'source': 'live'}
    """
    try:
        from src.models.regime_live import get_live_regime
        result = get_live_regime()
        if result.get("source") != "fallback":
            return result
    except Exception:
        pass

    # Historical fallback — last row of pre-computed regime CSV
    df = get_regime_series(demo_mode)
    if df.is_empty():
        return {"label": REGIME_NORMAL, "prob": 0.15, "date": "N/A", "source": "fallback"}
    latest = df.sort("date").tail(1)
    return {
        "label":  latest["regime_label"][0],
        "prob":   float(latest["regime_prob"][0]),
        "date":   str(latest["date"][0]),
        "source": "historical",
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


def get_gpr_gscpi_lag_data(demo_mode: bool = True, lag_days: int = 30) -> pl.DataFrame:
    """
    Align GPR and GSCPI at a given lag to visualise the causal transmission chain.

    Args:
        demo_mode: passed to load_fred.
        lag_days: number of calendar days to shift GSCPI backward (default 30).
    Returns:
        DataFrame with columns: date, gpr, gscpi, gscpi_lagged, rolling_corr_90d
        Rows are the intersection where both series have data.
    Example:
        df = get_gpr_gscpi_lag_data()
    """
    fred = load_fred(demo_mode)
    if fred.is_empty() or "series_id" not in fred.columns:
        return pl.DataFrame()

    gpr   = fred.filter(pl.col("series_id") == "GPR").select(["date", "value"]).rename({"value": "gpr"}).sort("date")
    gscpi = fred.filter(pl.col("series_id") == "GSCPI").select(["date", "value"]).rename({"value": "gscpi"}).sort("date")

    # Shift GSCPI dates back by lag_days so GSCPI(T+lag) aligns with GPR(T)
    gscpi_lagged = gscpi.with_columns(
        (pl.col("date") - pl.duration(days=lag_days)).alias("date")
    ).rename({"gscpi": "gscpi_lagged"})

    joined = gpr.join(gscpi_lagged, on="date", how="inner")

    # Rolling 90-day Pearson correlation
    n = 90
    gpr_vals   = joined["gpr"].to_list()
    gscpi_vals = joined["gscpi_lagged"].to_list()
    import math
    roll_corr = []
    for i in range(len(gpr_vals)):
        if i < n - 1:
            roll_corr.append(None)
        else:
            x = gpr_vals[i - n + 1: i + 1]
            y = gscpi_vals[i - n + 1: i + 1]
            mx, my = sum(x) / n, sum(y) / n
            num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
            dx  = math.sqrt(sum((xi - mx) ** 2 for xi in x))
            dy  = math.sqrt(sum((yi - my) ** 2 for yi in y))
            roll_corr.append(num / (dx * dy) if dx * dy > 0 else None)

    return joined.with_columns(pl.Series("rolling_corr_90d", roll_corr))


def get_quant_risk_metrics(demo_mode: bool = True) -> dict:
    """
    Compute all 6 quantitative risk stack metrics from pre-computed regime data.

    Args:
        demo_mode: passed to loaders.
    Returns:
        dict with keys: rolling_posterior, edge_ratio, vol_ratio, stoikov, kelly, var_95
        Each value is a Polars DataFrame (or empty DataFrame on missing data).
    Example:
        metrics = get_quant_risk_metrics()
    """
    prices  = load_prices(demo_mode)
    regimes = get_regime_series(demo_mode)
    if prices.is_empty() or regimes.is_empty():
        return {}

    joined = (
        prices
        .join(regimes.select(["date", "regime_label", "regime_prob"]), on="date", how="left")
        .drop_nulls("regime_label")
    )
    crisis = joined.filter(pl.col("regime_label") == REGIME_CRISIS)
    normal = joined.filter(pl.col("regime_label") == REGIME_NORMAL)

    # 1. Bayesian Regime Posterior — rolling 30-day mean crisis probability
    rolling_posterior = (
        regimes.sort("date")
        .with_columns(
            pl.col("regime_prob").rolling_mean(window_size=30).alias("rolling_prob")
        )
        .select(["date", "rolling_prob"])
        .drop_nulls()
    )

    # 2. Edge Ratio — |crisis mean return| / |normal mean return| per ticker
    crisis_means = crisis.group_by("ticker").agg(pl.col("return_1d").mean().alias("crisis_mean"))
    normal_means = normal.group_by("ticker").agg(pl.col("return_1d").mean().alias("normal_mean"))
    edge_ratio = (
        crisis_means.join(normal_means, on="ticker")
        .with_columns(
            (pl.col("crisis_mean").abs() / (pl.col("normal_mean").abs() + 1e-9)).alias("edge_ratio")
        )
        .sort("edge_ratio", descending=True)
    )

    # 3. Bid-Ask Spread Proxy — return std-dev ratio Crisis/Normal per ticker
    crisis_vol = crisis.group_by("ticker").agg(pl.col("return_1d").std().alias("vol_crisis"))
    normal_vol = normal.group_by("ticker").agg(pl.col("return_1d").std().alias("vol_normal"))
    vol_ratio = (
        crisis_vol.join(normal_vol, on="ticker")
        .with_columns(
            (pl.col("vol_crisis") / (pl.col("vol_normal") + 1e-9)).alias("vol_ratio")
        )
        .sort("vol_ratio", descending=True)
    )

    # 4. Stoikov Inventory Risk — annualized vol × global crisis frequency
    crisis_pct = crisis.height / max(joined.height, 1)
    stoikov = (
        joined.group_by("ticker")
        .agg((pl.col("return_1d").std() * (252 ** 0.5)).alias("ann_vol"))
        .with_columns((pl.col("ann_vol") * crisis_pct).alias("stoikov_score"))
        .sort("stoikov_score", descending=True)
    )

    # 5. Kelly Criterion — f* = (p*b - (1-p)) / b per ticker in crisis regime
    kelly_rows = []
    for ticker in sorted(crisis["ticker"].unique().to_list()):
        df_t = crisis.filter(pl.col("ticker") == ticker)
        wins   = df_t.filter(pl.col("return_1d") > 0)
        losses = df_t.filter(pl.col("return_1d") <= 0)
        p = len(wins) / max(len(df_t), 1)
        mean_win  = float(wins["return_1d"].mean())   if len(wins)   > 0 else 1e-6
        mean_loss = abs(float(losses["return_1d"].mean())) if len(losses) > 0 else 1e-6
        b = mean_win / max(mean_loss, 1e-9)
        kelly_f = (p * b - (1 - p)) / max(b, 1e-9)
        kelly_rows.append({"ticker": ticker, "kelly_f": round(kelly_f, 4)})
    kelly = pl.DataFrame(kelly_rows).sort("kelly_f", descending=True)

    # 6. Historical VaR 95% — 5th-percentile daily return, crisis vs normal
    var_95 = (
        crisis.group_by("ticker")
        .agg(pl.col("return_1d").quantile(0.05).alias("var_95_crisis"))
        .join(
            normal.group_by("ticker").agg(pl.col("return_1d").quantile(0.05).alias("var_95_normal")),
            on="ticker",
        )
        .sort("var_95_crisis")
    )

    return {
        "rolling_posterior": rolling_posterior,
        "edge_ratio":        edge_ratio,
        "vol_ratio":         vol_ratio,
        "stoikov":           stoikov,
        "kelly":             kelly,
        "var_95":            var_95,
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
