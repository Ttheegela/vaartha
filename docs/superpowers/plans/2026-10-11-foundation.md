# Vārtā v2 — Sub-project 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze v1 in `legacy/`, stand up the v2 Python project (`core/` + `api/`), port the regime engine with a parity test against legacy, and add SQLite schema, a FastAPI skeleton, CI, and a rewritten CLAUDE.md.

**Architecture:** `core/` is a pure Python library (Polars, no web deps); the regime math is a pure function and fetching lives in a separate module. `api/` is a FastAPI app built by a factory (`create_app`), so nothing touches the network or disk at import time. SQLite through stdlib `sqlite3` (WAL mode); the schema is one `schema.sql` file applied idempotently.

**Tech Stack:** Python 3.12, uv, Polars, yfinance, FastAPI, uvicorn, pytest, ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-11-varta-v2-design.md` (§2 architecture, §3 tables, §7 hardening/testing, §8 build order item 1)

## Global Constraints

- Python `>=3.12`; dependencies managed with `uv` (`pyproject.toml` + committed `uv.lock`).
- Polars for all dataframes. pandas may appear only in `core/prices.py` (via yfinance output) and in tests that fake yfinance output.
- No Streamlit imports outside `legacy/`. `legacy/` is frozen: never edit it except in Task 1's move.
- No network calls or disk writes at import time; side effects happen in functions or the app factory.
- Docstring on every public function and module.
- Secrets are never read, printed, or logged by code in this plan.
- Commit messages: Conventional Commits, **no `Co-Authored-By` line** (project rule in CLAUDE.md).
- Never commit: `.env`, `*.db`, `data/` runtime files outside `legacy/data/demo/`.

## Review Focus

1. **Price series with missing values** (yfinance returns NaN for one ticker on a holiday): regime must drop them and produce the same result as the gap-free series. Test in Task 2.
2. **Too little history** (new data outage, fewer than 30 prices): `compute_regime` raises `ValueError`; `/api/regime` returns HTTP 503, never 500 or a made-up "Normal". Tests in Tasks 2 and 5.
3. **Zero or negative price in the data**: raises `ValueError` instead of `ZeroDivisionError`. Test in Task 2.
4. **Fresh volume with no `data/` directory**: `connect()` creates the parent directory. Test in Task 4.
5. **API and worker both run `init_db` on the same file**: second run is a no-op and keeps existing rows. Test in Task 4.

---

## File map

```
legacy/                      v1, moved verbatim (app.py, config.py, src/, scripts/, notebooks/, data/,
                             requirements.txt, Procfile, .streamlit/, .devcontainer/, README.md, .env.example)
pyproject.toml               project + deps + ruff + pytest config
uv.lock                      generated
core/__init__.py
core/regime.py               pure regime math (Regime dataclass, compute_regime)
core/prices.py               yfinance → Polars adapter (fetch_closes)
core/live.py                 live_regime(): fetch + compute
api/__init__.py
api/settings.py              Settings.from_env()
api/db.py                    connect(), init_db()
api/schema.sql               all spec §3 tables
api/main.py                  create_app(): /healthz, /api/regime
scripts/make_regime_golden.py one-off: record legacy outputs for parity
tests/fixtures/regime_windows.json   recorded input windows
tests/fixtures/regime_golden.json    recorded legacy outputs
tests/test_regime.py
tests/test_prices.py
tests/test_db.py
tests/test_api.py
.github/workflows/ci.yml
CLAUDE.md                    rewritten for v2
README.md                    short v2 readme
.env.example                 v2 env vars
.gitignore                   updated
```

---

### Task 1: Freeze v1 in `legacy/` and create the uv project

**Files:**
- Move: `app.py config.py src/ scripts/ notebooks/ data/ requirements.txt Procfile .streamlit/ .devcontainer/ README.md .env.example` → `legacy/`
- Create: `pyproject.toml`, `core/__init__.py`, `api/__init__.py`, `tests/test_smoke.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: importable packages `core` and `api`; `uv run pytest` and `uv run ruff check .` work from repo root; legacy data at `legacy/data/demo/prices.csv`.

- [ ] **Step 1: Move v1 files with git**

```bash
mkdir -p legacy
git mv app.py config.py src scripts notebooks data requirements.txt Procfile .streamlit .devcontainer README.md .env.example legacy/
git status --short | head
```
Expected: lines starting with `R ` (renames) into `legacy/`.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "varta"
version = "2.0.0"
description = "Vārtā — personal finance and investing advisor"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn>=0.30",
  "polars>=1.0",
  "pyarrow>=16",
  "yfinance>=0.2.66",
]

[dependency-groups]
dev = [
  "pytest>=8",
  "httpx>=0.27",
  "ruff>=0.6",
]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
extend-exclude = ["legacy"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- [ ] **Step 3: Create package markers and a smoke test**

`core/__init__.py`:
```python
"""Vārtā core library: pure analytics, no web dependencies."""
```

`api/__init__.py`:
```python
"""Vārtā FastAPI application."""
```

`tests/test_smoke.py`:
```python
"""Smoke test: packages import without side effects."""


def test_packages_import():
    import api  # noqa: F401
    import core  # noqa: F401
```

- [ ] **Step 4: Update `.gitignore`** — append:

```gitignore

# v2 runtime data
data/
*.db
*.db-wal
*.db-shm
```

(`legacy/data/demo/` is already tracked; the `data/` pattern only matches untracked runtime files.)

- [ ] **Step 5: Lock, then run tests and lint**

Run: `uv lock && uv sync && uv run pytest -q && uv run ruff check .`
Expected: `1 passed`, ruff `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add -A legacy pyproject.toml uv.lock core api tests .gitignore
git commit -m "chore: freeze v1 in legacy/ and scaffold v2 uv project"
```

---

### Task 2: Port the regime engine with a parity test

**Files:**
- Create: `scripts/make_regime_golden.py`, `tests/fixtures/regime_windows.json`, `tests/fixtures/regime_golden.json` (generated), `core/regime.py`, `tests/test_regime.py`

**Interfaces:**
- Consumes: `legacy/src/models/regime_live.py::get_live_regime` (only inside the one-off script).
- Produces:
  ```python
  @dataclass(frozen=True)
  class Regime:
      label: str            # "Normal" | "Elevated" | "Crisis"
      prob: float           # crisis probability [0, 1], 4 dp
      brent_vol: float      # 30d annualized Brent vol, 4 dp
      spy_dd: float         # SPY drawdown from window max, 4 dp
      gold_oil: float       # GLD/BNO ratio, 2 dp
      signals: dict[str, float]  # vol_score, dd_score, gold_oil_score (3 dp)

  def compute_regime(bno: list[float], spy: list[float], gld: list[float]) -> Regime
  ```
  Raises `ValueError` on fewer than 30 valid prices or any non-positive price.

- [ ] **Step 1: Write the golden-recording script**

`scripts/make_regime_golden.py`:
```python
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
```

- [ ] **Step 2: Run it**

Run the command in the script docstring.
Expected: three lines like `calm_2024 Normal 0.1234`, then `tests/fixtures/regime_windows.json` and `tests/fixtures/regime_golden.json` exist. If it fails on an import from `legacy/src/utils.py`, add the missing package with another `--with`. Do not edit `legacy/`.

- [ ] **Step 3: Write the failing tests**

`tests/test_regime.py`:
```python
"""Regime engine: parity with v1, label thresholds, and bad-input handling."""

import json
import math
from pathlib import Path

import pytest

from core.regime import compute_regime

FIXTURES = Path(__file__).parent / "fixtures"
WINDOWS = json.loads((FIXTURES / "regime_windows.json").read_text())
GOLDEN = json.loads((FIXTURES / "regime_golden.json").read_text())


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_matches_legacy(name):
    w = WINDOWS[name]
    r = compute_regime(w["BNO"], w["SPY"], w["GLD"])
    g = GOLDEN[name]
    assert r.label == g["label"]
    assert r.prob == pytest.approx(g["prob"], abs=1e-4)
    assert r.brent_vol == pytest.approx(g["brent_vol"], abs=1e-4)
    assert r.spy_dd == pytest.approx(g["spy_dd"], abs=1e-4)
    assert r.gold_oil == pytest.approx(g["gold_oil"], abs=1e-2)
    for k, v in g["signals"].items():
        assert r.signals[k] == pytest.approx(v, abs=1e-3)


def test_flat_market_is_normal():
    r = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)
    assert r.label == "Normal"
    assert r.prob == 0.0


def test_stressed_market_is_crisis():
    bno = [100.0 if i % 2 == 0 else 105.0 for i in range(40)]  # ~5% daily swings
    spy = [100.0 - i * 0.5 for i in range(40)]                # -19.5% from window max
    gld = [30.0 * bno[-1]] * 40                                # gold/oil ratio 30
    r = compute_regime(bno, spy, gld)
    assert r.label == "Crisis"
    assert r.prob == 1.0


def test_missing_values_are_dropped():
    w = WINDOWS["calm_2024"]
    clean = compute_regime(w["BNO"], w["SPY"], w["GLD"])
    gappy_bno = w["BNO"][:10] + [math.nan, None] + w["BNO"][10:]
    assert compute_regime(gappy_bno, w["SPY"], w["GLD"]) == clean


def test_too_little_history_raises():
    with pytest.raises(ValueError, match="need >= 30"):
        compute_regime([100.0] * 29, [100.0] * 40, [1800.0] * 40)


def test_non_positive_price_raises():
    bno = [100.0] * 40
    bno[20] = 0.0
    with pytest.raises(ValueError, match="positive"):
        compute_regime(bno, [100.0] * 40, [1800.0] * 40)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_regime.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.regime'`

- [ ] **Step 5: Implement `core/regime.py`**

```python
"""Market regime proxy: Brent vol, SPY drawdown and gold/oil ratio → crisis probability.

Ported from legacy/src/models/regime_live.py. Pure math, no I/O.
Kept for parity with v1: the SPY "peak" is the max over the window passed in
(v1 passed ~3 months), not a true 252-day high.
"""

import math
from dataclasses import dataclass

BRENT_VOL_NORMAL = 0.22
BRENT_VOL_CRISIS = 0.42
SPY_DD_NORMAL = -0.04
SPY_DD_CRISIS = -0.12
GOLD_OIL_NORMAL = 18.0
GOLD_OIL_CRISIS = 28.0
W_VOL, W_DD, W_RATIO = 0.45, 0.35, 0.20
CRISIS_AT = 0.55
ELEVATED_AT = 0.30
MIN_POINTS = 30
TRADING_DAYS = 252
VOL_WINDOW = 31  # 31 prices → 30 daily returns
RATIO_WINDOW = 30
_EPS = 1e-6


@dataclass(frozen=True)
class Regime:
    """Regime label, crisis probability and the signals behind it."""

    label: str
    prob: float
    brent_vol: float
    spy_dd: float
    gold_oil: float
    signals: dict[str, float]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _normalize(v: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.5
    return _clamp((v - lo) / (hi - lo))


def _clean(prices: list[float | None]) -> list[float]:
    out = [float(p) for p in prices if p is not None and not math.isnan(p)]
    if len(out) < MIN_POINTS:
        raise ValueError(f"need >= {MIN_POINTS} prices, got {len(out)}")
    if min(out) <= 0:
        raise ValueError("prices must be positive")
    return out


def compute_regime(bno: list[float], spy: list[float], gld: list[float]) -> Regime:
    """Compute the regime from daily closes of BNO (Brent), SPY and GLD, oldest first."""
    bno, spy, gld = _clean(bno), _clean(spy), _clean(gld)

    window = bno[-VOL_WINDOW:]
    rets = [window[i] / window[i - 1] - 1 for i in range(1, len(window))]
    mean_r = sum(rets) / len(rets)
    variance = sum((r - mean_r) ** 2 for r in rets) / len(rets)
    brent_vol = math.sqrt(variance) * math.sqrt(TRADING_DAYS)

    spy_dd = spy[-1] / max(spy) - 1.0

    gold_oil_now = gld[-1] / max(bno[-1], _EPS)
    gld_avg = sum(gld[-RATIO_WINDOW:]) / len(gld[-RATIO_WINDOW:])
    bno_avg = sum(bno[-RATIO_WINDOW:]) / len(bno[-RATIO_WINDOW:])
    momentum = gold_oil_now / max(gld_avg / max(bno_avg, _EPS), _EPS)
    go_level = max(gold_oil_now, momentum * GOLD_OIL_NORMAL)
    go_sig = _normalize(go_level, GOLD_OIL_NORMAL, GOLD_OIL_CRISIS)

    vol_sig = _normalize(brent_vol, BRENT_VOL_NORMAL, BRENT_VOL_CRISIS)
    dd_sig = _normalize(-spy_dd, -SPY_DD_NORMAL, -SPY_DD_CRISIS)
    prob = _clamp(W_VOL * vol_sig + W_DD * dd_sig + W_RATIO * go_sig)

    if prob >= CRISIS_AT:
        label = "Crisis"
    elif prob >= ELEVATED_AT:
        label = "Elevated"
    else:
        label = "Normal"

    return Regime(
        label=label,
        prob=round(prob, 4),
        brent_vol=round(brent_vol, 4),
        spy_dd=round(spy_dd, 4),
        gold_oil=round(gold_oil_now, 2),
        signals={
            "vol_score": round(vol_sig, 3),
            "dd_score": round(dd_sig, 3),
            "gold_oil_score": round(go_sig, 3),
        },
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_regime.py -q && uv run ruff check .`
Expected: `8 passed` (3 parity + 5 others), ruff clean. If a parity case fails, the port differs from legacy: compare line by line with `legacy/src/models/regime_live.py:69-130`; do not loosen tolerances.

- [ ] **Step 7: Commit**

```bash
git add scripts/make_regime_golden.py tests/fixtures tests/test_regime.py core/regime.py
git commit -m "feat(core): port regime engine with legacy parity tests"
```

---

### Task 3: Price fetching and live regime

**Files:**
- Create: `core/prices.py`, `core/live.py`, `tests/test_prices.py`

**Interfaces:**
- Consumes: `core.regime.compute_regime`, `core.regime.Regime`.
- Produces:
  ```python
  def fetch_closes(tickers: list[str], period: str = "3mo") -> pl.DataFrame
      # columns: date (pl.Date), ticker (str), close (f64); nulls dropped; sorted by ticker, date
      # raises ValueError if yfinance returns nothing
  REGIME_TICKERS: tuple[str, str, str] = ("BNO", "SPY", "GLD")
  def live_regime(fetch: Callable[[list[str], str], pl.DataFrame] = fetch_closes) -> Regime
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_prices.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prices.py -q`
Expected: FAIL with `ImportError` / `ModuleNotFoundError` for `core.prices`.

- [ ] **Step 3: Implement `core/prices.py`**

```python
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
```

- [ ] **Step 4: Implement `core/live.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass (`12 passed`), ruff clean. If `unpivot` is missing, the installed Polars is < 1.0; check `uv run python -c "import polars; print(polars.__version__)"` and fix the lock, do not switch to `melt`.

- [ ] **Step 6: Optional live check (network; not in CI)**

Run: `uv run python -c "from core.live import live_regime; print(live_regime())"`
Expected: a `Regime(label=..., prob=...)` line. A network error here is acceptable; note it and continue.

- [ ] **Step 7: Commit**

```bash
git add core/prices.py core/live.py tests/test_prices.py
git commit -m "feat(core): yfinance price adapter and live regime"
```

---

### Task 4: SQLite schema and connection helpers

**Files:**
- Create: `api/settings.py`, `api/db.py`, `api/schema.sql`, `tests/test_db.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Settings:
      db_path: Path
      instance: str  # "owner" | "demo"
      @classmethod
      def from_env(cls) -> "Settings"   # VARTA_DB_PATH (default data/varta.db), VARTA_INSTANCE (default demo)

  def connect(path: Path) -> sqlite3.Connection   # WAL, foreign keys, Row factory, creates parent dir
  def init_db(conn: sqlite3.Connection) -> None   # idempotent
  TABLES: tuple[str, ...]                          # names created by schema.sql
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_db.py`:
```python
"""SQLite helpers: schema, WAL, idempotent init, settings."""

import pytest

from api.db import TABLES, connect, init_db
from api.settings import Settings


def test_init_creates_all_tables(tmp_path):
    conn = connect(tmp_path / "v.db")
    init_db(conn)
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLES) <= names


def test_wal_and_foreign_keys(tmp_path):
    conn = connect(tmp_path / "v.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_missing_parent_dir_is_created(tmp_path):
    path = tmp_path / "fresh" / "volume" / "v.db"
    init_db(connect(path))
    assert path.exists()


def test_init_twice_keeps_rows(tmp_path):
    path = tmp_path / "v.db"
    conn = connect(path)
    init_db(conn)
    conn.execute("INSERT INTO budgets VALUES ('FOOD_AND_DRINK', 600)")
    conn.commit()
    init_db(connect(path))
    assert conn.execute("SELECT monthly_limit FROM budgets").fetchone()[0] == 600


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VARTA_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("VARTA_INSTANCE", "owner")
    s = Settings.from_env()
    assert s.db_path == tmp_path / "x.db"
    assert s.instance == "owner"


def test_settings_rejects_unknown_instance(monkeypatch):
    monkeypatch.setenv("VARTA_INSTANCE", "prod")
    with pytest.raises(ValueError, match="VARTA_INSTANCE"):
        Settings.from_env()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.db'`

- [ ] **Step 3: Write `api/schema.sql`** (spec §3, plus `kind` and `alerts`/`briefings`)

```sql
CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  access_token_enc BLOB NOT NULL,
  institution TEXT,
  txn_cursor TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  last_synced_at TEXT
);
CREATE TABLE IF NOT EXISTS accounts (
  account_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  name TEXT, type TEXT, subtype TEXT, mask TEXT,
  balance_current REAL, balance_available REAL, currency TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
  txn_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
  date TEXT NOT NULL, amount REAL NOT NULL, merchant TEXT,
  pfc_primary TEXT, pfc_detailed TEXT, pending INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_transactions_date ON transactions(date);
CREATE TABLE IF NOT EXISTS securities (
  security_id TEXT PRIMARY KEY, ticker TEXT, name TEXT, type TEXT
);
CREATE TABLE IF NOT EXISTS holdings (
  account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
  security_id TEXT NOT NULL REFERENCES securities(security_id),
  quantity REAL, cost_basis REAL, value REAL, as_of TEXT,
  PRIMARY KEY (account_id, security_id)
);
CREATE TABLE IF NOT EXISTS recurring_streams (
  stream_id TEXT PRIMARY KEY,
  account_id TEXT REFERENCES accounts(account_id) ON DELETE CASCADE,
  direction TEXT NOT NULL CHECK (direction IN ('inflow', 'outflow')),
  kind TEXT NOT NULL CHECK (kind IN ('subscription', 'bill', 'income')),
  merchant TEXT, avg_amount REAL, last_amount REAL, frequency TEXT,
  last_date TEXT, predicted_next_date TEXT, status TEXT, is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS budgets (
  pfc_primary TEXT PRIMARY KEY, monthly_limit REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, target_amount REAL NOT NULL,
  target_date TEXT, account_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS networth_snapshots (
  date TEXT PRIMARY KEY, assets REAL NOT NULL, liabilities REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS news_items (
  id INTEGER PRIMARY KEY, published_at TEXT, source TEXT NOT NULL, url TEXT,
  title TEXT NOT NULL, text TEXT, tickers TEXT NOT NULL DEFAULT '[]', topics TEXT NOT NULL DEFAULT '[]',
  url_hash TEXT UNIQUE, title_hash TEXT
);
CREATE INDEX IF NOT EXISTS ix_news_title_hash ON news_items(title_hash);
CREATE TABLE IF NOT EXISTS news_scores (
  news_id INTEGER NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  sentiment REAL, sentiment_conf REAL, material REAL, stress REAL, event TEXT, noise REAL,
  raw_json TEXT, scored_at TEXT,
  PRIMARY KEY (news_id, ticker)
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
  action_label TEXT, action_href TEXT, dismissed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS briefings (
  date TEXT PRIMARY KEY, items_json TEXT NOT NULL, model TEXT, generated_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_messages (
  id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT,
  tool_calls TEXT, model TEXT, latency_ms INTEGER, tokens_in INTEGER, tokens_out INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_agent_messages_conv ON agent_messages(conversation_id);
```

- [ ] **Step 4: Implement `api/settings.py`**

```python
"""Instance settings from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

INSTANCES = ("owner", "demo")


@dataclass(frozen=True)
class Settings:
    """Per-instance configuration."""

    db_path: Path
    instance: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Read VARTA_DB_PATH and VARTA_INSTANCE; reject unknown instances."""
        instance = os.environ.get("VARTA_INSTANCE", "demo")
        if instance not in INSTANCES:
            raise ValueError(f"VARTA_INSTANCE must be one of {INSTANCES}, got {instance!r}")
        db_path = Path(os.environ.get("VARTA_DB_PATH", "data/varta.db"))
        return cls(db_path=db_path, instance=instance)
```

- [ ] **Step 5: Implement `api/db.py`**

```python
"""SQLite connection and schema setup (stdlib sqlite3, WAL mode)."""

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
TABLES = (
    "items", "accounts", "transactions", "securities", "holdings", "recurring_streams",
    "budgets", "goals", "networth_snapshots", "news_items", "news_scores", "alerts",
    "briefings", "agent_messages",
)
BUSY_TIMEOUT_MS = 5000


def connect(path: Path) -> sqlite3.Connection:
    """Open the database, creating its directory; WAL + foreign keys on."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if missing. Safe to run repeatedly."""
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass (`18 passed`), ruff clean.

- [ ] **Step 7: Commit**

```bash
git add api/settings.py api/db.py api/schema.sql tests/test_db.py
git commit -m "feat(api): SQLite schema, WAL connection helper and settings"
```

---

### Task 5: FastAPI app factory with `/healthz` and `/api/regime`

**Files:**
- Create: `api/main.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `Settings`, `connect`, `init_db` (Task 4); `live_regime`, `Regime` (Tasks 2–3).
- Produces:
  ```python
  REGIME_TTL_SECONDS = 300
  def create_app(settings: Settings | None = None,
                 regime_provider: Callable[[], Regime] = live_regime,
                 clock: Callable[[], float] = time.monotonic) -> FastAPI
  # GET /healthz    → 200 {"status": "ok", "instance": "<owner|demo>"}
  # GET /api/regime → 200 asdict(Regime) | 503 {"detail": "regime unavailable"}
  ```
  Run with: `uv run uvicorn --factory api.main:create_app`

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:
```python
"""API: health, regime endpoint, caching and failure handling."""

from fastapi.testclient import TestClient

from api.main import REGIME_TTL_SECONDS, create_app
from api.settings import Settings
from core.regime import compute_regime

NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)


def _client(tmp_path, provider, clock=lambda: 0.0):
    settings = Settings(db_path=tmp_path / "v.db", instance="demo")
    return TestClient(create_app(settings, regime_provider=provider, clock=clock))


def test_healthz(tmp_path):
    r = _client(tmp_path, lambda: NORMAL).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "instance": "demo"}
    assert (tmp_path / "v.db").exists()


def test_regime_ok(tmp_path):
    r = _client(tmp_path, lambda: NORMAL).get("/api/regime")
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Normal"
    assert set(body["signals"]) == {"vol_score", "dd_score", "gold_oil_score"}


def test_regime_failure_is_503_not_fake_normal(tmp_path):
    def broken():
        raise ValueError("need >= 30 prices, got 3")

    r = _client(tmp_path, broken).get("/api/regime")
    assert r.status_code == 503
    assert r.json() == {"detail": "regime unavailable"}


def test_regime_is_cached_within_ttl(tmp_path):
    calls = []
    now = [0.0]

    def provider():
        calls.append(1)
        return NORMAL

    client = _client(tmp_path, provider, clock=lambda: now[0])
    client.get("/api/regime")
    client.get("/api/regime")
    assert len(calls) == 1
    now[0] = REGIME_TTL_SECONDS + 1
    client.get("/api/regime")
    assert len(calls) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.main'`

- [ ] **Step 3: Implement `api/main.py`**

```python
"""FastAPI app factory. No side effects at import.

Run: uvicorn --factory api.main:create_app
"""

import logging
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from api.db import connect, init_db
from api.settings import Settings
from core.live import live_regime
from core.regime import Regime

log = logging.getLogger("varta.api")
REGIME_TTL_SECONDS = 300


def create_app(
    settings: Settings | None = None,
    regime_provider: Callable[[], Regime] = live_regime,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    """Build the API: initialise the DB and register routes."""
    settings = settings or Settings.from_env()
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)

    app = FastAPI(title="Vārtā API")
    # ponytail: single-process in-memory cache; move to the DB if the api runs >1 worker
    cache: dict[str, tuple[float, Regime]] = {}

    @app.get("/healthz")
    def healthz() -> dict:
        """Liveness plus a trivial DB query."""
        with closing(connect(settings.db_path)) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "instance": settings.instance}

    @app.get("/api/regime")
    def regime() -> dict:
        """Current market regime, cached for REGIME_TTL_SECONDS."""
        hit = cache.get("regime")
        if hit and clock() - hit[0] < REGIME_TTL_SECONDS:
            return asdict(hit[1])
        try:
            result = regime_provider()
        except Exception as exc:  # network, short history, bad prices
            log.warning("regime unavailable: %s", exc)
            raise HTTPException(status_code=503, detail="regime unavailable") from exc
        cache["regime"] = (clock(), result)
        return asdict(result)

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass (`22 passed`), ruff clean.

- [ ] **Step 5: Manual run (network for `/api/regime`)**

Run: `VARTA_DB_PATH=/tmp/varta-dev.db uv run uvicorn --factory api.main:create_app --port 8000` and in another shell `curl -s localhost:8000/healthz` then `curl -s -w ' %{http_code}\n' localhost:8000/api/regime`
Expected: `{"status":"ok","instance":"demo"}`; regime returns JSON with 200, or `{"detail":"regime unavailable"} 503` when offline. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add api/main.py tests/test_api.py
git commit -m "feat(api): app factory with healthz and cached regime endpoint"
```

---

### Task 6: CI, CLAUDE.md, README and env template

**Files:**
- Create: `.github/workflows/ci.yml`, `README.md`, `.env.example`
- Modify: `CLAUDE.md` (full rewrite)

**Interfaces:**
- Consumes: everything above. Produces: green CI on push; project rules for future sessions.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
  pull_request:

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run pytest -q
```

- [ ] **Step 2: Write `.env.example`**

```bash
# Instance: owner (real Plaid, Tailscale-only) or demo (Plaid Sandbox, public)
VARTA_INSTANCE=demo
VARTA_DB_PATH=data/varta.db
# Later sub-projects add: PLAID_*, LLM_BASE_URL, LLM_MODEL, OPENROUTER_API_KEY,
# TYPESAFE_API_KEY, ALPACA_*, FINNHUB_API_KEY, REDDIT_*, TOKEN_ENCRYPTION_KEY
```

- [ ] **Step 3: Write `README.md`**

````markdown
# Vārtā

A personal finance and investing advisor with an AI agent: linked accounts (Plaid), a bills and
subscriptions calendar, budgets and goals, and investing advice informed by live news, crowd
sentiment and a market-regime engine. Not financial advice.

Design: [`docs/superpowers/specs/2026-10-11-varta-v2-design.md`](docs/superpowers/specs/2026-10-11-varta-v2-design.md)
v1 (course project, Streamlit) is frozen in [`legacy/`](legacy/).

## Develop

```bash
uv sync
uv run pytest
uv run uvicorn --factory api.main:create_app --reload
```
````

- [ ] **Step 4: Rewrite `CLAUDE.md`**

```markdown
# CLAUDE.md — Vārtā v2

Read before changing anything. Design spec: `docs/superpowers/specs/2026-10-11-varta-v2-design.md`.
Plans: `docs/superpowers/plans/`.

## What this is
Personal finance + investing advisor agent (Origin-style). Two instances from one codebase:
- owner: Tarun's real accounts (Plaid Trial), Tailscale-only, LLM = Ollama on his Mac
- demo: public, Plaid Sandbox, LLM = OpenRouter, rate-limited

## Layout
- `core/` pure Python analytics (Polars, no web deps, no I/O at import)
- `api/` FastAPI app (`uvicorn --factory api.main:create_app`), SQLite via stdlib sqlite3 (WAL)
- `worker/` scheduled jobs (later), `web/` Next.js from v0 (later), `evals/` (later), `deploy/` (later)
- `legacy/` v1 Streamlit app — frozen, reference only, never edit

## Rules
- Polars only. pandas allowed only in `core/prices.py` and tests that fake yfinance.
- Docstring on every public function and module. No magic numbers: name constants at module top.
- No network or disk side effects at import time.
- Tests: pytest, no live network (fake/replay external APIs). `uv run pytest && uv run ruff check .` must pass before commit.
- The agent's tools are read-only. Never pass Plaid tokens or account numbers to any LLM.
- Never read, print or log secrets. Never commit `.env`, `*.db`, runtime `data/`.
- Commits: Conventional Commits, no `Co-Authored-By` line. Never force-push.
- Verify library APIs against installed versions or docs before using them.
- When data is missing or unverified, say so; never invent numbers.
```

- [ ] **Step 5: Verify everything locally**

Run: `uv sync --locked && uv run ruff check . && uv run pytest -q`
Expected: ruff clean, `22 passed`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml .env.example README.md CLAUDE.md
git commit -m "chore: CI, v2 CLAUDE.md, README and env template"
```

- [ ] **Step 7: Push and confirm CI (ask the user before pushing)**

Run: `git push -u origin HEAD` then `gh run watch` (or `gh run list --limit 1`).
Expected: the `ci` workflow passes.
