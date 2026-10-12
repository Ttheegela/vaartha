"""Rule-based alerts over the advisor toolbox; deduped by kind and text."""

import sqlite3
from datetime import UTC, datetime, timedelta

from api.agent_tools import Toolbox

BILL_DUE_DAYS = 4
BUDGET_WARN = 0.8
DEDUPE_DAYS = 7
SENTIMENT_FLIP_MIN = 0.2
SENTIMENT_DAYS = 10
RECENT_DAYS = 3
NEWS_CHANNEL = "news"
REGIME_KEY = "regime_label"


def _label(category: str) -> str:
    return category.replace("_", " ").capitalize()


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _candidates(conn: sqlite3.Connection, tb: Toolbox) -> list[tuple[str, str, str, str]]:
    """(kind, text, action_label, action_href) for every rule that fires now."""
    out = []
    bills = tb.call("get_upcoming_bills", {"days": BILL_DUE_DAYS})
    for b in bills.get("items", []):
        due = datetime.fromisoformat(b["due"]).strftime("%b %d").replace(" 0", " ")
        out.append(("bill_due", f"{b['merchant']} {_money(b['amount'])} due {due}",
                    "View bills", "/bills"))
    for s in tb.call("get_subscriptions", {}).get("items", []):
        if s["price_up"]:
            out.append(("price_up", f"{s['merchant']} went up {_money(s['price_up'])} "
                        f"to {_money(s['amount'])}", "View bills", "/bills"))
    for b in tb.call("get_budget_status", {}).get("items", []):
        if b["pct_used"] >= BUDGET_WARN:
            out.append(("budget", f"{_label(b['category'])} at {round(b['pct_used'] * 100)}% "
                        f"of ${b['limit']:,.0f} budget", "View spending", "/spending"))
    regime = tb.call("get_market_regime", {})
    if "label" in regime:
        row = conn.execute("SELECT value FROM app_state WHERE key = ?", (REGIME_KEY,)).fetchone()
        if row and row["value"] != regime["label"]:
            out.append(("regime", f"Market regime moved from {row['value']} to {regime['label']}",
                        "View investments", "/investments"))
        conn.execute("INSERT OR REPLACE INTO app_state VALUES (?, ?)",
                     (REGIME_KEY, regime["label"]))
    cutoff = (tb.today() - timedelta(days=RECENT_DAYS)).isoformat()
    for h in tb.call("get_holdings", {}).get("items", []):
        if not h["ticker"]:
            continue
        pts = [p for p in tb.call("get_sentiment", {"ticker": h["ticker"], "days": SENTIMENT_DAYS})
               .get("points", []) if p["channel"] == NEWS_CHANNEL]
        recent = _mean([p["sentiment"] for p in pts if p["date"] > cutoff])
        prior = _mean([p["sentiment"] for p in pts if p["date"] <= cutoff])
        if (recent is not None and prior is not None and recent * prior < 0
                and min(abs(recent), abs(prior)) >= SENTIMENT_FLIP_MIN):
            word = "positive" if recent > 0 else "negative"
            out.append(("sentiment", f"{h['ticker']} news sentiment turned {word}",
                        "View news", "/news"))
    return out


def generate_alerts(conn: sqlite3.Connection, toolbox: Toolbox) -> int:
    """Insert alerts for rules that fire and have no same kind+text alert in DEDUPE_DAYS."""
    now = datetime.now(UTC)
    since = (now - timedelta(days=DEDUPE_DAYS)).isoformat()
    added = 0
    for kind, text, label, href in _candidates(conn, toolbox):
        if conn.execute("SELECT 1 FROM alerts WHERE kind = ? AND text = ? AND created_at >= ?",
                        (kind, text, since)).fetchone():
            continue
        conn.execute("INSERT INTO alerts (created_at, kind, text, action_label, action_href) "
                     "VALUES (?, ?, ?, ?, ?)", (now.isoformat(), kind, text, label, href))
        added += 1
    conn.commit()
    return added
