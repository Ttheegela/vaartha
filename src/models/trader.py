"""
trader.py — GeoSentinel Terminal (VARTA)
Regime-to-trade pipeline: translates VARTA regime signals into Alpaca paper orders.
Never touches real money — ALPACA_PAPER=True is hardcoded in fetchers.py.
"""

import polars as pl
from src.utils import log
from src.models.portfolio import optimize_weights
from config import REGIME_TARGET_WEIGHTS, TICKERS


def generate_regime_orders(
    positions: pl.DataFrame,
    regime: str,
    regime_prob: float,
    returns_df: pl.DataFrame,
    regimes_df: pl.DataFrame,
    total_equity: float,
    method: str = "regime_target",
) -> pl.DataFrame:
    """
    Generate rebalancing orders based on VARTA regime signal.

    Args:
        positions: Current Alpaca positions from fetch_alpaca_portfolio().
        regime: 'Crisis' or 'Normal'.
        regime_prob: Probability of current regime (0–1).
        returns_df: Historical returns for weight optimization.
        regimes_df: Historical regime labels.
        total_equity: Total portfolio equity in dollars.
        method: 'regime_target' | 'max_sharpe' | 'min_variance'
    Returns:
        DataFrame with columns: ticker, action, current_shares, target_shares,
        order_qty, current_weight_pct, target_weight_pct, rationale, estimated_value
    Example:
        orders = generate_regime_orders(positions, "Crisis", 0.73, returns_df, regimes_df, 100000)
    """
    if positions.is_empty() or total_equity <= 0:
        return pl.DataFrame()

    # Get current prices per ticker
    current = {
        row["ticker"]: {
            "shares": row["qty"],
            "price":  row["current_price"],
            "value":  row["market_value"],
        }
        for row in positions.to_dicts()
    }

    # Get target weights from regime optimizer
    tickers_held = list(current.keys())
    target_weights = optimize_weights(
        returns_df=returns_df,
        tickers=tickers_held,
        method=method,
        regime=regime,
        regimes_df=regimes_df,
    )

    # Current weights
    current_weights = {
        t: v["value"] / total_equity
        for t, v in current.items()
    }

    # Build order list
    rows = []
    for ticker in tickers_held:
        price = current[ticker]["price"]
        if price <= 0:
            continue

        cur_shares  = current[ticker]["shares"]
        cur_weight  = current_weights.get(ticker, 0.0)
        tgt_weight  = target_weights.get(ticker, cur_weight)
        tgt_value   = tgt_weight * total_equity
        tgt_shares  = tgt_value / price
        delta_shares = tgt_shares - cur_shares

        # Only generate orders above 0.5 share threshold to avoid noise
        if abs(delta_shares) < 0.5:
            continue

        action   = "BUY" if delta_shares > 0 else "SELL"
        rationale = _get_rationale(ticker, action, regime)

        rows.append({
            "ticker":             ticker,
            "action":             action,
            "current_shares":     round(cur_shares, 2),
            "target_shares":      round(tgt_shares, 2),
            "order_qty":          round(abs(delta_shares), 2),
            "current_weight_pct": round(cur_weight * 100, 1),
            "target_weight_pct":  round(tgt_weight * 100, 1),
            "current_price":      round(price, 2),
            "estimated_value":    round(abs(delta_shares) * price, 2),
            "rationale":          rationale,
        })

    if not rows:
        return pl.DataFrame()

    return (
        pl.DataFrame(rows)
        .sort("estimated_value", descending=True)
    )


def execute_strategy(orders: pl.DataFrame) -> pl.DataFrame:
    """
    Execute all orders in the orders DataFrame via Alpaca paper trading.
    Imports fetchers here to avoid circular imports.

    Args:
        orders: DataFrame from generate_regime_orders().
    Returns:
        DataFrame with execution results: ticker, action, qty, status, filled_price, error.
    Example:
        results = execute_strategy(orders_df)
    """
    from src.data.fetchers import submit_market_order

    if orders.is_empty():
        return pl.DataFrame()

    results = []
    for row in orders.to_dicts():
        ticker = row["ticker"]
        qty    = row["order_qty"]
        side   = row["action"].lower()

        result = submit_market_order(ticker, qty, side)
        results.append({
            "ticker":        ticker,
            "action":        row["action"],
            "qty":           qty,
            "status":        result.get("status", "error"),
            "filled_price":  result.get("filled_avg_price", 0.0),
            "error":         result.get("error", ""),
        })
        log.info(f"Executed: {side.upper()} {qty:.1f} {ticker} → {result.get('status','error')}")

    return pl.DataFrame(results)


def _get_rationale(ticker: str, action: str, regime: str) -> str:
    """
    Return a human-readable rationale for a regime-driven order.

    Args:
        ticker: Ticker symbol.
        action: 'BUY' or 'SELL'.
        regime: Current regime label.
    Returns:
        One-line rationale string.
    Example:
        r = _get_rationale("GLD", "BUY", "Crisis")
    """
    rationales = {
        "Crisis": {
            "GLD":  "Safe haven demand surges during geopolitical Crisis",
            "BNO":  "Brent hedge — Hormuz / Red Sea disruption risk elevated",
            "XOM":  "Integrated energy — benefits from oil price spike",
            "CVX":  "Diversified energy — defensive in Crisis regime",
            "SPY":  "Reduce benchmark exposure — Crisis beta drag",
            "TSM":  "Taiwan Strait escalation risk — reduce semiconductor fab",
            "NVDA": "TSM fab dependency — reduce AI hardware in Crisis",
            "AMD":  "Semiconductor — reduce on supply chain stress",
            "REMX": "Rare earth supply chain disruption risk",
            "LIT":  "Lithium supply chain concentrated in crisis regions",
            "ALB":  "Upstream lithium — exposed to China export restrictions",
            "FCX":  "Copper — industrial demand contracts in Crisis",
        },
        "Normal": {
            "NVDA": "AI hardware — hyperscaler CapEx boom in Normal regime",
            "TSM":  "Semiconductor fab — demand recovery in Normal regime",
            "AMD":  "Semiconductor upside — Normal regime growth",
            "REMX": "Rare earth recovery — supply chain normalizing",
            "LIT":  "Lithium EV demand — Normal regime growth",
            "ALB":  "Lithium processing — Normal regime demand",
            "FCX":  "Copper industrial demand recovers in Normal regime",
            "GLD":  "Reduce safe haven — Normal regime risk-on",
            "BNO":  "Reduce oil hedge — geopolitical pressure easing",
            "XOM":  "Energy demand stable in Normal regime",
            "CVX":  "Energy stable — Normal regime baseline",
            "SPY":  "Add benchmark — Normal regime equity upside",
        },
    }
    return rationales.get(regime, {}).get(ticker, f"{action} — regime rebalancing")
