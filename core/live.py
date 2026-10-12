"""Live regime: fetch recent closes and run the pure regime engine."""

from collections.abc import Callable

import polars as pl

from core.prices import fetch_closes
from core.regime import Regime, compute_regime

REGIME_TICKERS = ("BNO", "SPY", "GLD")
REGIME_PERIOD = "3mo"


def live_regime(fetch: Callable[[list[str], str], pl.DataFrame] = fetch_closes) -> Regime:
    """Compute today's regime from ~3 months of BNO, SPY and GLD closes."""
    df = fetch(list(REGIME_TICKERS), REGIME_PERIOD)
    series = {
        t: df.filter(pl.col("ticker") == t).sort("date")["close"].to_list()
        for t in REGIME_TICKERS
    }
    return compute_regime(series["BNO"], series["SPY"], series["GLD"])
