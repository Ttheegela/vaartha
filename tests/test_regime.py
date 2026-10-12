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


def test_infinite_price_raises():
    bno = [100.0] * 40
    bno[-5] = math.inf
    with pytest.raises(ValueError, match="need >= 30|finite"):
        compute_regime(bno[-30:], [100.0] * 40, [1800.0] * 40)
