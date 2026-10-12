"""Daily closes via yfinance, returned as Polars.

The only module allowed to handle pandas (yfinance returns pandas); it converts
at the boundary with pl.from_pandas and nothing pandas leaves this file.
"""

import polars as pl
import yfinance as yf


def fetch_closes(tickers: list[str], period: str = "3mo") -> pl.DataFrame:
    """Return long-format daily closes [date, ticker, close], nulls dropped."""
    raw = yf.download(
        tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        multi_level_index=True,
    )
    if raw is None or raw.empty:
        raise ValueError(f"yfinance returned no data for {tickers}")
    wide = pl.from_pandas(raw["Close"].reset_index())
    date_col = wide.columns[0]
    return (
        wide.rename({date_col: "date"})
        .unpivot(index="date", variable_name="ticker", value_name="close")
        .drop_nulls("close")
        .with_columns(pl.col("date").cast(pl.Date))
        .sort("ticker", "date")
    )
