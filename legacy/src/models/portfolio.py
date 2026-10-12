"""
portfolio.py — GeoSentinel Terminal (VARTA)
Portfolio analytics: P&L, risk metrics, regime stress test, efficient frontier.
All functions accept Polars DataFrames — never pandas.
"""

import polars as pl
import numpy as np
from scipy.optimize import minimize
from src.utils import log
from config import RISK_FREE_RATE, VAR_CONFIDENCE, N_FRONTIER_PORTFOLIOS, REGIME_TARGET_WEIGHTS


# ── P&L ───────────────────────────────────────────────────────────────────────

def compute_portfolio_pnl(positions: pl.DataFrame) -> pl.DataFrame:
    """
    Compute P&L metrics for Alpaca positions.

    Args:
        positions: DataFrame from fetch_alpaca_portfolio() with ticker, qty,
                   avg_entry_price, current_price, market_value, unrealized_pl, unrealized_plpc
    Returns:
        Same DataFrame with added weight_pct column (% of total portfolio).
    Example:
        df = compute_portfolio_pnl(fetch_alpaca_portfolio())
    """
    if positions.is_empty():
        return positions
    total_value = positions["market_value"].sum()
    return positions.with_columns(
        (pl.col("market_value") / total_value * 100).alias("weight_pct")
    )


# ── Risk Metrics ──────────────────────────────────────────────────────────────

def compute_risk_metrics(
    weights: dict,
    returns_df: pl.DataFrame,
) -> dict:
    """
    Compute portfolio risk metrics from historical returns.

    Args:
        weights: Dict of {ticker: weight} — must sum to 1.0.
        returns_df: DataFrame with columns: date, ticker, return_1d
    Returns:
        Dict with sharpe, sortino, max_drawdown, var_95, cvar_95, annual_vol,
        annual_return, beta_spy.
    Example:
        metrics = compute_risk_metrics({"GLD": 0.4, "NVDA": 0.6}, returns_df)
    """
    if returns_df.is_empty() or not weights:
        return {}

    tickers = list(weights.keys())
    w = np.array([weights.get(t, 0.0) for t in tickers])
    if w.sum() == 0:
        return {}
    w = w / w.sum()

    # Pivot returns: rows=date, cols=ticker
    pivot = (
        returns_df.filter(pl.col("ticker").is_in(tickers))
        .pivot(index="date", on="ticker", values="return_1d")
        .sort("date")
        .fill_null(0.0)
    )
    available = [t for t in tickers if t in pivot.columns]
    if not available:
        return {}

    mat = pivot.select(available).to_numpy()
    w_avail = np.array([weights.get(t, 0.0) for t in available])
    w_avail = w_avail / w_avail.sum()

    port_returns = mat @ w_avail
    n = len(port_returns)

    annual_factor  = 252
    annual_ret     = float(np.mean(port_returns) * annual_factor)
    annual_vol     = float(np.std(port_returns) * np.sqrt(annual_factor))
    excess         = port_returns - RISK_FREE_RATE / annual_factor
    sharpe         = float(np.mean(excess) / np.std(excess) * np.sqrt(annual_factor)) if np.std(excess) > 0 else 0.0
    downside       = port_returns[port_returns < 0]
    sortino        = float(np.mean(excess) / np.std(downside) * np.sqrt(annual_factor)) if len(downside) > 0 else 0.0
    cum             = np.cumprod(1 + port_returns)
    rolling_max    = np.maximum.accumulate(cum)
    drawdowns      = (cum - rolling_max) / rolling_max
    max_dd         = float(np.min(drawdowns))
    var_95         = float(np.percentile(port_returns, (1 - VAR_CONFIDENCE) * 100))
    cvar_95        = float(np.mean(port_returns[port_returns <= var_95]))

    # Beta vs SPY
    beta_spy = 0.0
    if "SPY" in pivot.columns:
        spy_ret = pivot["SPY"].to_numpy()
        cov = np.cov(port_returns, spy_ret)
        beta_spy = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else 0.0

    return {
        "annual_return": annual_ret,
        "annual_vol":    annual_vol,
        "sharpe":        sharpe,
        "sortino":       sortino,
        "max_drawdown":  max_dd,
        "var_95":        var_95,
        "cvar_95":       cvar_95,
        "beta_spy":      beta_spy,
    }


# ── Regime Stress Test ────────────────────────────────────────────────────────

def regime_stress_test(
    weights: dict,
    returns_df: pl.DataFrame,
    regimes_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Compute risk metrics separately for Crisis and Normal regime periods.

    Args:
        weights: Dict of {ticker: weight}.
        returns_df: DataFrame with date, ticker, return_1d.
        regimes_df: DataFrame with date, regime_label.
    Returns:
        DataFrame with columns: metric, normal, crisis, delta.
    Example:
        df = regime_stress_test(weights, returns_df, regimes_df)
    """
    if returns_df.is_empty() or regimes_df.is_empty():
        return pl.DataFrame()

    results = []
    for regime in ["Normal", "Crisis"]:
        regime_dates = (
            regimes_df.filter(pl.col("regime_label") == regime)
            .select("date")
        )
        filtered = returns_df.join(regime_dates, on="date", how="inner")
        m = compute_risk_metrics(weights, filtered)
        if m:
            results.append({"regime": regime, **m})

    if len(results) < 2:
        return pl.DataFrame()

    normal = {r["regime"]: r for r in results}.get("Normal", {})
    crisis = {r["regime"]: r for r in results}.get("Crisis", {})

    metrics = ["annual_return", "annual_vol", "sharpe", "sortino", "max_drawdown", "var_95", "beta_spy"]
    labels  = ["Annual Return", "Annual Volatility", "Sharpe Ratio", "Sortino Ratio",
               "Max Drawdown", "VaR 95% (1D)", "Beta vs SPY"]

    rows = []
    for key, label in zip(metrics, labels):
        n_val = normal.get(key, 0.0)
        c_val = crisis.get(key, 0.0)
        rows.append({
            "Metric":       label,
            "Normal":       round(n_val, 4),
            "Crisis":       round(c_val, 4),
            "Delta":        round(c_val - n_val, 4),
        })
    return pl.DataFrame(rows)


# ── Efficient Frontier ────────────────────────────────────────────────────────

def efficient_frontier(
    returns_df: pl.DataFrame,
    tickers: list[str],
) -> pl.DataFrame:
    """
    Monte Carlo efficient frontier — random weight portfolios.

    Args:
        returns_df: DataFrame with date, ticker, return_1d.
        tickers: List of tickers to include.
    Returns:
        DataFrame with columns: vol, ret, sharpe, weights_json (top 500 by Sharpe).
    Example:
        df = efficient_frontier(returns_df, ["NVDA", "GLD", "TSM"])
    """
    if returns_df.is_empty() or len(tickers) < 2:
        return pl.DataFrame()

    pivot = (
        returns_df.filter(pl.col("ticker").is_in(tickers))
        .pivot(index="date", on="ticker", values="return_1d")
        .sort("date")
        .fill_null(0.0)
    )
    available = [t for t in tickers if t in pivot.columns]
    if len(available) < 2:
        return pl.DataFrame()

    mat = pivot.select(available).to_numpy()
    n   = len(available)
    rng = np.random.default_rng(42)

    vols, rets, sharpes, weight_strs = [], [], [], []
    for _ in range(N_FRONTIER_PORTFOLIOS):
        w = rng.dirichlet(np.ones(n))
        r = mat @ w
        ann_ret = float(np.mean(r) * 252)
        ann_vol = float(np.std(r) * np.sqrt(252))
        sharpe  = (ann_ret - RISK_FREE_RATE) / ann_vol if ann_vol > 0 else 0.0
        vols.append(ann_vol)
        rets.append(ann_ret)
        sharpes.append(sharpe)
        weight_strs.append(",".join(f"{available[i]}:{w[i]:.3f}" for i in range(n)))

    return pl.DataFrame({
        "vol":          vols,
        "ret":          rets,
        "sharpe":       sharpes,
        "weights_json": weight_strs,
    })


# ── Regime-Aware Optimizer ────────────────────────────────────────────────────

def optimize_weights(
    returns_df: pl.DataFrame,
    tickers: list[str],
    method: str = "max_sharpe",
    regime: str = "all",
    regimes_df: pl.DataFrame | None = None,
) -> dict:
    """
    Optimize portfolio weights using scipy.

    Args:
        returns_df: DataFrame with date, ticker, return_1d.
        tickers: Tickers to include.
        method: 'max_sharpe' | 'min_variance' | 'risk_parity' | 'regime_target'
        regime: 'all' | 'Crisis' | 'Normal' — filter returns to regime periods.
        regimes_df: Required if regime != 'all'.
    Returns:
        Dict of {ticker: weight}.
    Example:
        w = optimize_weights(returns_df, ["GLD", "NVDA", "TSM"], method="max_sharpe")
    """
    if method == "regime_target":
        label = "Crisis" if regime == "Crisis" else "Normal"
        target = REGIME_TARGET_WEIGHTS.get(label, {})
        return {t: target.get(t, 1 / len(tickers)) for t in tickers}

    # Filter to regime if requested
    df = returns_df
    if regime != "all" and regimes_df is not None and not regimes_df.is_empty():
        regime_dates = regimes_df.filter(pl.col("regime_label") == regime).select("date")
        df = returns_df.join(regime_dates, on="date", how="inner")

    pivot = (
        df.filter(pl.col("ticker").is_in(tickers))
        .pivot(index="date", on="ticker", values="return_1d")
        .sort("date")
        .fill_null(0.0)
    )
    available = [t for t in tickers if t in pivot.columns]
    if len(available) < 2:
        return {t: 1 / len(tickers) for t in tickers}

    mat = pivot.select(available).to_numpy()
    n   = len(available)
    w0  = np.ones(n) / n
    bounds      = [(0.02, 0.40)] * n    # min 2%, max 40% per asset
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    def neg_sharpe(w):
        r   = mat @ w
        ret = np.mean(r) * 252
        vol = np.std(r) * np.sqrt(252)
        return -(ret - RISK_FREE_RATE) / vol if vol > 0 else 0.0

    def portfolio_vol(w):
        return float(np.std(mat @ w) * np.sqrt(252))

    def risk_parity_obj(w):
        r      = mat @ w
        cov    = np.cov(mat.T)
        mrc    = cov @ w
        rc     = w * mrc
        target = np.ones(n) / n
        return float(np.sum((rc / rc.sum() - target) ** 2))

    obj = neg_sharpe if method == "max_sharpe" else (
        portfolio_vol if method == "min_variance" else risk_parity_obj
    )

    try:
        res = minimize(obj, w0, method="SLSQP", bounds=bounds, constraints=constraints,
                       options={"maxiter": 1000, "ftol": 1e-9})
        w_opt = res.x if res.success else w0
    except Exception:
        w_opt = w0

    w_opt = np.clip(w_opt, 0, 1)
    w_opt = w_opt / w_opt.sum()
    return {available[i]: round(float(w_opt[i]), 4) for i in range(n)}
