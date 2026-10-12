"""Portfolio risk metrics over long-format closes."""

import math
from datetime import date, timedelta

import polars as pl
import pytest

from core.risk import portfolio_risk


def _closes(series: dict[str, list[float]]) -> pl.DataFrame:
    start = date(2026, 1, 1)
    rows = [(start + timedelta(days=i), t, p) for t, ps in series.items() for i, p in enumerate(ps)]
    return pl.DataFrame(rows, schema=["date", "ticker", "close"], orient="row")


def test_flat_prices_have_zero_risk():
    r = portfolio_risk(_closes({"AAA": [10.0] * 30, "SPY": [100.0] * 30}), {"AAA": 1.0})
    assert r["volatility"] == 0 and r["max_drawdown"] == 0 and r["days"] == 29
    assert r["beta"] is None  # zero benchmark variance


def test_drawdown_and_beta_of_benchmark_itself():
    spy = [100, 110, 99, 105, 120.0]
    r = portfolio_risk(_closes({"SPY": spy}), {"SPY": 1.0})
    assert r["max_drawdown"] == pytest.approx(99 / 110 - 1)
    assert r["beta"] == pytest.approx(1.0)
    assert r["volatility"] > 0 and math.isfinite(r["volatility"])


def test_weights_renormalize_over_covered_tickers():
    r = portfolio_risk(_closes({"AAA": [1, 2, 3.0], "SPY": [1, 1, 1.0]}),
                       {"AAA": 0.6, "ZZZ": 0.4})
    assert r["covered_weight"] == pytest.approx(0.6)


def test_no_covered_tickers_raises():
    with pytest.raises(ValueError):
        portfolio_risk(_closes({"SPY": [1, 2, 3.0]}), {"ZZZ": 1.0})
