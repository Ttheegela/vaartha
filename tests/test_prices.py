"""Price adapter and live regime, with yfinance faked (no network)."""

import pandas as pd
import polars as pl
import pytest

from core import prices
from core.live import live_regime


def _fake_yf_frame(closes: dict[str, list[float | None]]) -> pd.DataFrame:
    n = len(next(iter(closes.values())))
    idx = pd.date_range("2024-01-01", periods=n, freq="B", name="Date")
    cols = pd.MultiIndex.from_tuples(
        [(field, t) for field in ("Close", "Open") for t in closes], names=["Price", "Ticker"]
    )
    data = {(f, t): v for f in ("Close", "Open") for t, v in closes.items()}
    return pd.DataFrame(data, index=idx, columns=cols)


def test_fetch_closes_long_format(monkeypatch):
    frame = _fake_yf_frame({"SPY": [1.0, 2.0, None], "GLD": [3.0, 4.0, 5.0]})
    monkeypatch.setattr(prices.yf, "download", lambda *a, **k: frame)
    df = prices.fetch_closes(["SPY", "GLD"])
    assert df.columns == ["date", "ticker", "close"]
    assert df.schema["date"] == pl.Date
    assert df.filter(pl.col("ticker") == "SPY")["close"].to_list() == [1.0, 2.0]
    assert df.filter(pl.col("ticker") == "GLD").height == 3


def test_fetch_closes_empty_raises(monkeypatch):
    monkeypatch.setattr(prices.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError, match="no data"):
        prices.fetch_closes(["SPY"])


def test_live_regime_uses_fetch():
    def fake_fetch(tickers, period):
        rows = [
            {"date": i, "ticker": t, "close": {"BNO": 100.0, "SPY": 100.0, "GLD": 1800.0}[t]}
            for t in tickers
            for i in range(40)
        ]
        return pl.DataFrame(rows)

    r = live_regime(fetch=fake_fetch)
    assert r.label == "Normal"
