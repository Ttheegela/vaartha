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
