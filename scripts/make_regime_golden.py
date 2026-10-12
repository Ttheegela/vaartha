"""One-off: record legacy regime outputs so the v2 port can be parity-tested.

Runs the frozen v1 function with yfinance replaced by fixed windows from
legacy/data/demo/prices.csv. Re-run only if the windows change.

Run:
  uv run --no-project --with streamlit --with yfinance --with pandas --with plotly \
    --with polars --with python-dotenv python scripts/make_regime_golden.py
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy"
FIXTURES = ROOT / "tests" / "fixtures"
TICKERS = ("BNO", "SPY", "GLD")
WINDOW_ROWS = 63  # ~3 months of trading days, matching legacy period="3mo"
WINDOWS = {
    "calm_2024": "2024-12-30",
    "covid_2020": "2020-03-23",
    "ukraine_2022": "2022-03-08",
}

sys.path.insert(0, str(LEGACY))
os.chdir(LEGACY)
from src.models import regime_live  # noqa: E402


def window(prices: pl.DataFrame, end: str) -> dict[str, list[float]]:
    """Return the last WINDOW_ROWS closes per ticker on or before `end`."""
    w = prices.filter(pl.col("date") <= end)
    return {
        t: w.filter(pl.col("ticker") == t).sort("date")["close"].tail(WINDOW_ROWS).to_list()
        for t in TICKERS
    }


def fake_download(series: dict[str, list[float]]):
    """Build a yf.download replacement returning a ('Close', ticker) MultiIndex frame."""

    def _download(*_args, **_kwargs):
        cols = pd.MultiIndex.from_tuples([("Close", t) for t in series])
        return pd.DataFrame(list(zip(*series.values(), strict=True)), columns=cols)

    return _download


def main() -> None:
    """Record inputs and legacy outputs for each window."""
    prices = pl.read_csv(LEGACY / "data" / "demo" / "prices.csv").filter(
        pl.col("ticker").is_in(TICKERS)
    )
    inputs, golden = {}, {}
    for name, end in WINDOWS.items():
        series = window(prices, end)
        regime_live.yf.download = fake_download(series)
        regime_live.get_live_regime.clear()
        out = regime_live.get_live_regime()
        assert out["source"] == "live", f"{name}: legacy fell back: {out}"
        inputs[name] = series
        golden[name] = {k: out[k] for k in ("label", "prob", "brent_vol", "spy_dd", "gold_oil")}
        golden[name]["signals"] = out["signals"]
        print(name, golden[name]["label"], golden[name]["prob"])
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "regime_windows.json").write_text(json.dumps(inputs))
    (FIXTURES / "regime_golden.json").write_text(json.dumps(golden, indent=2))


if __name__ == "__main__":
    main()
