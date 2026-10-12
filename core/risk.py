"""Portfolio risk metrics: annualized volatility, max drawdown and beta. Pure Polars."""

import math

import polars as pl

TRADING_DAYS = 252


def portfolio_risk(closes: pl.DataFrame, weights: dict[str, float],
                   benchmark: str = "SPY") -> dict:
    """Risk of a weighted portfolio from long-format closes [date, ticker, close].

    Weights are renormalized over tickers that have prices; covered_weight says how
    much of the original weight that was. Beta is None without benchmark variance.
    """
    wide = closes.pivot(on="ticker", index="date", values="close").sort("date")
    tickers = [c for c in wide.columns if c != "date"]
    # ponytail: rows with any missing close are dropped; per-pair alignment if histories
    # differ a lot
    rets = wide.select(pl.col(t).pct_change() for t in tickers).slice(1).drop_nulls()
    held = [t for t in weights if t in rets.columns and weights[t] > 0]
    if not held or rets.height == 0:
        raise ValueError("no price history for any holding")
    covered = sum(weights[t] for t in held)
    port = rets.select(sum(pl.col(t) * (weights[t] / covered) for t in held).alias("p"))["p"]
    equity = pl.concat([pl.Series([1.0]), (port + 1).cum_prod()])  # start at 1.0
    drawdown = float((equity / equity.cum_max() - 1).min())
    beta = None
    if benchmark in rets.columns:
        bench = rets[benchmark]
        var = float(bench.var())
        if var > 0:
            cov = pl.DataFrame({"p": port, "b": bench}).select(pl.cov("p", "b")).item()
            beta = float(cov) / var
    vol = float(port.std() or 0.0) * math.sqrt(TRADING_DAYS)
    return {"volatility": round(vol, 4), "max_drawdown": round(min(drawdown, 0.0), 4),
            "beta": None if beta is None else round(beta, 3),
            "covered_weight": round(covered, 4), "days": rets.height}
