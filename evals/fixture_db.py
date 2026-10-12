"""Deterministic fixture database and toolbox for the advisor evals (fake Plaid + offline news)."""

import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from api.agent_tools import Toolbox, build_toolbox
from api.crypto import new_key
from api.settings import Settings
from core.regime import Regime
from scripts.refresh_news import run as refresh_news_run
from scripts.seed_demo import seed

EVAL_TODAY = date(2026, 10, 12)
EVAL_NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
EVAL_REGIME = Regime(label="Elevated", prob=0.55, brent_vol=0.42, spy_dd=-0.06, gold_oil=36.5,
                     signals={"vol_score": 0.6, "dd_score": 0.4, "gold_oil_score": 0.5})
CLOSES_SEED = 7
CLOSES_DAYS = 252
CLOSES_START = 100.0
DAILY_VOL = 0.01


def synthetic_closes(tickers: list[str]) -> pl.DataFrame:
    """Seeded 252-day random walk per ticker, starting at 100 (date, ticker, close)."""
    rng = random.Random(CLOSES_SEED)
    rows = []
    for t in tickers:
        close = CLOSES_START
        for i in range(CLOSES_DAYS):
            if i:
                close *= 1 + rng.gauss(0, DAILY_VOL)
            rows.append({"date": EVAL_TODAY - timedelta(days=CLOSES_DAYS - 1 - i),
                         "ticker": t, "close": close})
    return pl.DataFrame(rows)


def build(path: Path) -> Path:
    """Build the fixture DB at `path`: fake Plaid seed plus offline fixture news."""
    settings = Settings(db_path=path, instance="demo", token_key=new_key())
    seed(settings, "fake", EVAL_TODAY)
    refresh_news_run(settings, offline=True, now=EVAL_NOW)
    return path


def eval_toolbox(path: Path) -> Toolbox:
    """Toolbox over the fixture DB with the frozen clock, regime and synthetic prices."""
    return build_toolbox(path, lambda: EVAL_TODAY, lambda: EVAL_REGIME, synthetic_closes)
