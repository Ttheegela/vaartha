"""
Offline regime labeling demo — fixtures only, no network.

Loads geopolitical/market events from ``data/fixtures/regime_events.json``,
assigns coarse regime labels, and runs a simple change-point stats stub.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

# Repo root: .../vaartha/src/regime/offline_demo.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FIXTURE = _REPO_ROOT / "data" / "fixtures" / "regime_events.json"

_RISK_OFF_TAGS = {
    "risk-off",
    "geopolitics",
    "energy",
    "oil",
    "vol",
    "pandemic",
    "tariffs",
    "trade",
}
_RISK_ON_TAGS = {"risk-on", "de-escalation"}
_TRANSITION_TAGS = {"transition", "supply-chain", "shipping", "fx", "politics"}


def load_fixture_events(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load fake-but-plausible regime events from the offline fixture JSON."""
    fixture_path = Path(path) if path else _DEFAULT_FIXTURE
    with fixture_path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, list):
        raise ValueError(f"Expected list of events in {fixture_path}")
    return raw


def label_regimes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign coarse regime labels while preserving source / evidence fields.

    Labels: ``risk-on``, ``risk-off``, ``transition`` (heuristic on tags/title).
    """
    labeled: list[dict[str, Any]] = []
    for ev in events:
        tags = {str(t).lower() for t in ev.get("tags", [])}
        title = str(ev.get("title", "")).lower()

        if tags & _RISK_ON_TAGS or "ceasefire" in title or "de-escalat" in title:
            regime = "risk-on"
        elif tags & _TRANSITION_TAGS and not (tags & _RISK_OFF_TAGS - {"geopolitics"}):
            regime = "transition"
        elif tags & _RISK_OFF_TAGS or any(
            k in title for k in ("invasion", "attack", "tariff", "pandemic", "war")
        ):
            regime = "risk-off"
        elif tags & _TRANSITION_TAGS:
            regime = "transition"
        else:
            regime = "transition"

        out = dict(ev)
        out["regime"] = regime
        # Preserve evidence / source fields explicitly
        out["evidence_urls"] = list(
            ev.get("evidence_urls")
            or ([ev["source_url"]] if ev.get("source_url") else [])
        )
        out["source"] = ev.get("source")
        out["source_url"] = ev.get("source_url")
        labeled.append(out)
    return labeled


def change_point_check(series: list[float], window: int = 3) -> dict[str, Any]:
    """Simple rolling-mean shift stub (no external deps).

    Flags a change when |recent_mean - prior_mean| exceeds 1× prior stdev
    (or a small epsilon if prior stdev is ~0).
    """
    if len(series) < window * 2:
        return {
            "n": len(series),
            "shift_flag": False,
            "reason": "series_too_short",
            "recent_mean": None,
            "prior_mean": None,
            "delta": None,
        }

    prior = series[:-window]
    recent = series[-window:]
    prior_mean = statistics.fmean(prior)
    recent_mean = statistics.fmean(recent)
    prior_std = statistics.pstdev(prior) if len(prior) > 1 else 0.0
    threshold = max(prior_std, 1e-6)
    delta = recent_mean - prior_mean
    shift_flag = abs(delta) > threshold

    return {
        "n": len(series),
        "window": window,
        "prior_mean": round(prior_mean, 6),
        "recent_mean": round(recent_mean, 6),
        "prior_std": round(prior_std, 6),
        "delta": round(delta, 6),
        "shift_flag": shift_flag,
        "reason": "rolling_mean_shift" if shift_flag else "stable",
    }


def llm_validate(labeled: list[dict[str, Any]], use_llm: bool = False) -> dict[str, Any]:
    """Optional LLM validation stub.

    When ``use_llm`` is False (default), returns an offline heuristic summary.
    When True, returns NotImplemented status (no paid / network LLM calls).
    """
    if use_llm:
        return {
            "status": "NotImplemented",
            "detail": "LLM validate deferred; offline heuristic only.",
        }

    counts: dict[str, int] = {}
    for row in labeled:
        counts[row["regime"]] = counts.get(row["regime"], 0) + 1
    return {
        "status": "offline_heuristic",
        "n_events": len(labeled),
        "regime_counts": counts,
        "all_have_evidence": all(bool(r.get("evidence_urls")) for r in labeled),
    }


def run_offline_demo(fixture_path: Path | str | None = None) -> dict[str, Any]:
    """End-to-end offline demo: fixtures → labels → change-point → summary."""
    events = load_fixture_events(fixture_path)
    labeled = label_regimes(events)

    # Numeric series stub: map regime to ordinal for change-point check
    ordinal = {"risk-on": 1.0, "transition": 0.0, "risk-off": -1.0}
    # Sort chronologically for a pseudo time series
    ordered = sorted(labeled, key=lambda e: str(e.get("date", "")))
    series = [ordinal.get(e["regime"], 0.0) for e in ordered]
    cp = change_point_check(series)
    validation = llm_validate(labeled, use_llm=False)

    return {
        "mode": "offline",
        "n_events": len(events),
        "labeled": labeled,
        "change_point": cp,
        "validation": validation,
        "feeds": {
            "gpr": "deferred (NotImplemented)",
            "mri": "deferred (NotImplemented)",
        },
    }


if __name__ == "__main__":
    summary = run_offline_demo()
    # Compact printable summary (full labeled list included for inspection)
    print(json.dumps(summary, indent=2, default=str))
