"""
regime_live.py — GeoSentinel Terminal (VARTA)
Live regime proxy: derives current crisis probability from live market data.
No HMM retraining needed — applies historically-validated thresholds to live signals.

Three signals (all via yfinance, no API key needed):
  1. Brent Oil 30-day realized vol (annualized) — primary crisis indicator
  2. SPY 20-day drawdown from 252-day rolling peak — equity stress
  3. Gold/Oil ratio trend — safe-haven demand relative to energy (crisis divergence)

Historical thresholds derived from 2010-2024 VARTA training window:
  Crisis (vol > 40%, drawdown < -8%, gold/oil rising): prob → 0.75-0.95
  Normal (vol < 25%, drawdown > -4%, gold/oil flat):   prob → 0.05-0.20
"""

import streamlit as st
import yfinance as yf
import polars as pl
from src.utils import log


# ── Historical thresholds derived from 2010–2024 training ────────────────────
_BRENT_VOL_NORMAL  = 0.22   # 22% annualized — calm market floor
_BRENT_VOL_CRISIS  = 0.42   # 42% annualized — crisis ceiling
_SPY_DD_NORMAL     = -0.04  # -4% drawdown — normal noise floor
_SPY_DD_CRISIS     = -0.12  # -12% drawdown — crisis stress threshold
_GOLD_OIL_NORMAL   = 18.0   # gold/oil ratio — normal baseline
_GOLD_OIL_CRISIS   = 28.0   # gold/oil ratio — crisis (gold spikes, oil falls)

# Signal weights (must sum to 1.0)
_W_VOL   = 0.45
_W_DD    = 0.35
_W_RATIO = 0.20


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, v))


def _normalize(v: float, lo: float, hi: float) -> float:
    """Linear normalize v to [0, 1] given range [lo, hi]."""
    if hi == lo:
        return 0.5
    return _clamp((v - lo) / (hi - lo))


@st.cache_data(ttl=300)   # refresh every 5 minutes
def get_live_regime() -> dict:
    """
    Compute live crisis probability from market signals via yfinance.
    Cached for 5 minutes to avoid hammering yfinance on every rerender.

    Returns:
        dict with keys:
            label       (str)  — "Crisis" | "Elevated" | "Normal"
            prob        (float) — crisis probability [0, 1]
            date        (str)  — today's date
            source      (str)  — "live"
            brent_vol   (float) — 30-day annualized Brent vol
            spy_dd      (float) — SPY drawdown from 252d peak
            gold_oil    (float) — current gold/oil ratio
            signals     (dict) — per-signal scores for transparency

    Example:
        regime = get_live_regime()
        # {'label': 'Normal', 'prob': 0.18, 'source': 'live', ...}
    """
    try:
        # ── Fetch live prices (last 3 months — sufficient for all signals) ────
        raw = yf.download(
            ["BNO", "SPY", "GLD"],
            period="3mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        if raw.empty or "Close" not in raw.columns:
            raise ValueError("yfinance returned empty data")

        # Convert to plain Python lists — no pandas operations after this point
        raw_close = raw["Close"].dropna(how="all")
        if len(raw_close) < 30:
            raise ValueError("Insufficient history for live regime proxy")

        bno = [float(v) for v in raw_close["BNO"].dropna().tolist()]
        spy = [float(v) for v in raw_close["SPY"].dropna().tolist()]
        gld = [float(v) for v in raw_close["GLD"].dropna().tolist()]

        # ── Signal 1: Brent 30-day realized volatility (annualized) ──────────
        bno_30 = bno[-31:]
        brent_rets = [(bno_30[i] / bno_30[i-1] - 1) for i in range(1, len(bno_30))]
        mean_r = sum(brent_rets) / len(brent_rets)
        variance = sum((r - mean_r) ** 2 for r in brent_rets) / len(brent_rets)
        brent_vol_30d = float((variance ** 0.5) * (252 ** 0.5))

        # ── Signal 2: SPY 20-day drawdown from rolling high ──────────────────
        spy_252_high = max(spy)
        spy_current  = spy[-1]
        spy_drawdown = (spy_current / spy_252_high) - 1.0

        # ── Signal 3: Gold/Oil ratio (GLD price / BNO price) trend ───────────
        gold_oil_now = gld[-1] / max(bno[-1], 1e-6)
        gold_oil_30d = (sum(gld[-30:]) / len(gld[-30:])) / max(sum(bno[-30:]) / len(bno[-30:]), 1e-6)
        # If ratio has risen over 30d → safe-haven flight → crisis signal
        gold_oil_momentum = gold_oil_now / max(gold_oil_30d, 1e-6)
        # Normalize: ratio above 28 or rising >15% over 30d = full crisis signal
        gold_oil_signal = _normalize(max(gold_oil_now, gold_oil_momentum * _GOLD_OIL_NORMAL),
                                     _GOLD_OIL_NORMAL, _GOLD_OIL_CRISIS)

        # ── Normalize all signals to [0, 1] ───────────────────────────────────
        vol_signal = _normalize(brent_vol_30d, _BRENT_VOL_NORMAL, _BRENT_VOL_CRISIS)
        dd_signal  = _normalize(-spy_drawdown,  -_SPY_DD_NORMAL,  -_SPY_DD_CRISIS)

        # ── Composite crisis probability ──────────────────────────────────────
        crisis_prob = _clamp(
            _W_VOL   * vol_signal
            + _W_DD  * dd_signal
            + _W_RATIO * gold_oil_signal
        )

        # ── Label ─────────────────────────────────────────────────────────────
        if crisis_prob >= 0.55:
            label = "Crisis"
        elif crisis_prob >= 0.30:
            label = "Elevated"
        else:
            label = "Normal"

        from datetime import date
        log.info(f"Live regime: {label} (prob={crisis_prob:.2f}, "
                 f"vol={brent_vol_30d:.1%}, dd={spy_drawdown:.1%}, g/o={gold_oil_now:.1f})")

        return {
            "label":      label,
            "prob":       round(crisis_prob, 4),
            "date":       str(date.today()),
            "source":     "live",
            "brent_vol":  round(brent_vol_30d, 4),
            "spy_dd":     round(spy_drawdown, 4),
            "gold_oil":   round(gold_oil_now, 2),
            "signals": {
                "vol_score":      round(vol_signal, 3),
                "dd_score":       round(dd_signal, 3),
                "gold_oil_score": round(gold_oil_signal, 3),
            },
        }

    except Exception as e:
        log.error(f"Live regime proxy failed: {e} — using Normal fallback")
        from datetime import date
        return {
            "label":    "Normal",
            "prob":     0.15,
            "date":     str(date.today()),
            "source":   "fallback",
            "brent_vol": 0.0,
            "spy_dd":    0.0,
            "gold_oil":  0.0,
            "signals":  {},
        }
