"""Read-only advisor toolbox: compact, validated views over the finance and news handlers.

Tools never see Plaid tokens, account ids or masks. `Toolbox.call` never raises.
"""

import json
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from fastapi import HTTPException

from api.finance import MONTH_RE, build_finance_router
from api.news_read import build_news_router
from core.regime import Regime
from core.risk import portfolio_risk

MAX_NEWS_TOOL_ITEMS = 10
MAX_HISTORY_POINTS = 12
PRICE_UP_EPSILON = 0.005
BENCHMARK = "SPY"
MARKET = "MARKET"
MAX_ERROR_CHARS = 200
MONEY_DIGITS = 2
RATIO_DIGITS = 4


def _m(x: float | None) -> float | None:
    """Round money to 2 decimals."""
    return None if x is None else round(x, MONEY_DIGITS)


def _r(x: float | None) -> float | None:
    """Round a weight or sentiment to 4 decimals."""
    return None if x is None else round(x, RATIO_DIGITS)


class Toolbox:
    """Dispatches validated tool calls to the read-only handlers."""

    def __init__(self, db_path: Path, today: Callable[[], date],
                 regime_provider: Callable[[], Regime],
                 closes_provider: Callable[[list[str]], pl.DataFrame]) -> None:
        """Bind to a database and the injected clock, regime and price providers."""
        self.today = today
        self.regime_provider = regime_provider
        self.closes_provider = closes_provider
        self.fin = {r.path: r.endpoint for r in build_finance_router(db_path, today).routes}
        self.news = {r.path: r.endpoint for r in build_news_router(db_path, today).routes}
        self.specs = SPECS

    def call(self, name: str, arguments: str | dict) -> dict:
        """Validate and run one tool; any failure becomes {"error": "<tool>: <message>"}."""
        try:
            if name not in _TOOLS:
                return {"error": f"unknown tool {name}"}
            args = _parse(arguments)
            _, props, _ = _TOOLS[name]
            if unknown := set(args) - set(props):
                raise ValueError(f"unknown argument {sorted(unknown)[0]}")
            clean = {k: _coerce(k, v, props[k]) for k, v in args.items() if v is not None}
            return _FUNCS[name](self, **clean)
        except HTTPException as exc:
            return {"error": f"{name}: {exc.detail}"[:MAX_ERROR_CHARS]}
        except Exception as exc:  # the loop must never see a raise
            return {"error": f"{name}: {exc}"[:MAX_ERROR_CHARS]}


def _parse(arguments: str | dict) -> dict:
    """Arguments as a dict; empty or null JSON means no arguments."""
    if isinstance(arguments, str):
        arguments = json.loads(arguments) if arguments.strip() else {}
    if arguments is None:
        return {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object")
    return arguments


def _coerce(key: str, value, prop: dict):
    """Coerce one argument to its schema type, clamping integers into range."""
    kind = prop["type"]
    if kind == "integer":
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be an integer") from None
        return min(prop["maximum"], max(prop["minimum"], n))
    if kind == "array":
        if not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        return [str(v) for v in value]
    value = str(value)
    if "enum" in prop and value not in prop["enum"]:
        raise ValueError(f"{key} must be one of {prop['enum']}")
    if "pattern" in prop and not re.match(prop["pattern"], value):
        raise ValueError(f"{key} must be YYYY-MM")
    return value


def _int(lo: int, hi: int, default: int) -> dict:
    return {"type": "integer", "minimum": lo, "maximum": hi, "default": default}


def _holdings(tb: Toolbox) -> list:
    return tb.news["/api/holdings"]()


def get_net_worth(tb: Toolbox, days: int = 90) -> dict:
    """Totals, account balances (no ids) and a downsampled net-worth history."""
    acc = tb.fin["/api/accounts"]()
    hist = tb.fin["/api/networth"](days=days)
    n = len(hist)
    idx = list(range(n)) if n <= MAX_HISTORY_POINTS else sorted({
        round(i * (n - 1) / (MAX_HISTORY_POINTS - 1)) for i in range(MAX_HISTORY_POINTS)})
    return {"net": _m(acc.assets - acc.liabilities), "assets": _m(acc.assets),
            "liabilities": _m(acc.liabilities),
            "accounts": [{"name": a.name, "type": a.type, "subtype": a.subtype,
                          "institution": a.institution, "balance": _m(a.balance_current)}
                         for a in acc.accounts],
            "history": [{"date": hist[i].date, "net": _m(hist[i].net)} for i in idx]}


def get_cash_flow(tb: Toolbox, months: int = 6) -> dict:
    """Income, spend and net for the last `months` months."""
    flows = tb.fin["/api/spending"](month=None).cash_flow[-months:]
    return {"months": [{"month": f.month, "income": _m(f.income), "spend": _m(f.spend),
                        "net": _m(f.income - f.spend)} for f in flows]}


def get_spending(tb: Toolbox, month: str | None = None, group_by: str = "category") -> dict:
    """Spend for a month by category or by top merchant."""
    s = tb.fin["/api/spending"](month=month)
    if group_by == "merchant":
        items = [{"name": m.merchant, "amount": _m(m.amount), "count": m.count}
                 for m in s.by_merchant]
    else:
        items = [{"name": c.category, "amount": _m(c.amount)} for c in s.by_category]
    return {"month": s.month, "group_by": group_by,
            "total": _m(sum(c.amount for c in s.by_category)), "items": items}


def get_budget_status(tb: Toolbox) -> dict:
    """Each budget with spend so far this month and the share used."""
    return {"month": tb.today().strftime("%Y-%m"),
            "items": [{"category": b.category, "limit": _m(b.limit), "spent": _m(b.spent),
                       "pct_used": _r(b.spent / b.limit) if b.limit else 0}
                      for b in tb.fin["/api/budgets"]()]}


def get_upcoming_bills(tb: Toolbox, days: int = 7) -> dict:
    """Active subscriptions and bills due within `days` days."""
    start, end = tb.today(), tb.today() + timedelta(days=days)
    rec = tb.fin["/api/recurring"]()
    due = sorted((s for s in rec.subscriptions + rec.bills if s.is_active
                  and start.isoformat() <= s.predicted_next_date <= end.isoformat()),
                 key=lambda s: s.predicted_next_date)
    return {"from": start.isoformat(), "to": end.isoformat(),
            "total": _m(sum(s.last_amount for s in due)),
            "items": [{"merchant": s.merchant, "kind": s.kind, "amount": _m(s.last_amount),
                       "due": s.predicted_next_date} for s in due]}


def get_subscriptions(tb: Toolbox) -> dict:
    """Active subscriptions with monthly cost and any price increase."""
    subs = [s for s in tb.fin["/api/recurring"]().subscriptions if s.is_active]
    return {"monthly_total": _m(sum(s.monthly_amount for s in subs)),
            "items": [{"merchant": s.merchant, "frequency": s.frequency,
                       "amount": _m(s.last_amount), "monthly": _m(s.monthly_amount),
                       "last_date": s.last_date, "next_date": s.predicted_next_date,
                       "price_up": _m(s.last_amount - s.avg_amount)
                       if s.last_amount - s.avg_amount > PRICE_UP_EPSILON else None}
                      for s in subs]}


def get_goals(tb: Toolbox) -> dict:
    """Savings goals with progress and the monthly amount still needed."""
    items = []
    for g in tb.fin["/api/goals"]():
        need = (g.target_amount - g.current) / g.months_left \
            if g.months_left and g.current < g.target_amount else None
        items.append({"name": g.name, "target": _m(g.target_amount), "current": _m(g.current),
                      "progress": _r(g.progress), "target_date": g.target_date,
                      "months_left": g.months_left, "needed_per_month": _m(need)})
    return {"items": items}


def get_holdings(tb: Toolbox) -> dict:
    """Holdings by value with weights."""
    hs = _holdings(tb)
    return {"total_value": _m(sum(h.value or 0 for h in hs)),
            "top_weight": _r(max((h.weight for h in hs), default=0.0)),
            "items": [{"ticker": h.ticker, "name": h.name, "value": _m(h.value),
                       "weight": _r(h.weight)} for h in hs]}


def get_portfolio_risk(tb: Toolbox) -> dict:
    """Volatility, drawdown and beta of the current holdings."""
    hs = _holdings(tb)
    weights = {h.ticker: h.weight for h in hs if h.ticker and h.weight > 0}
    if not weights:
        return {"error": "no holdings"}
    closes = tb.closes_provider(list(dict.fromkeys([*weights, BENCHMARK])))
    return {**portfolio_risk(closes, weights, BENCHMARK),
            "top_weight": _r(max(weights.values())), "as_of": tb.today().isoformat()}


def get_market_regime(tb: Toolbox) -> dict:
    """Current market regime and its signals."""
    return asdict(tb.regime_provider())


def get_news(tb: Toolbox, tickers: list[str] | None = None, topic: str | None = None,
             days: int = 7) -> dict:
    """Material news, newest first, deduped, optionally by tickers and topic."""
    found = {}
    for t in tickers or [None]:
        for n in tb.news["/api/news"](ticker=t, source=None, days=days, material_only=True):
            found[n.id] = n
    rows = sorted(found.values(), key=lambda n: (n.published_at, n.id), reverse=True)
    if topic:
        rows = [n for n in rows if topic.lower() in (x.lower() for x in n.topics)]
    out = []
    for n in rows[:MAX_NEWS_TOOL_ITEMS]:
        sents = [s.sentiment for s in n.scores]
        out.append({"id": n.id, "title": n.title, "source": n.source,
                    "published_at": n.published_at, "tickers": n.tickers, "topics": n.topics,
                    "sentiment": _r(sum(sents) / len(sents)) if sents else None})
    return {"items": out}


def get_sentiment(tb: Toolbox, ticker: str, days: int = 30) -> dict:
    """Daily sentiment per channel for a ticker (use MARKET for the broad market)."""
    pts = tb.news["/api/sentiment"](ticker=ticker, days=days)
    return {"ticker": ticker, "points": [{"date": p.date, "channel": p.channel,
                                          "sentiment": _r(p.sentiment), "items": p.items}
                                         for p in pts]}


_NONE: dict = {}
# name -> (description, properties, required)
_TOOLS: dict[str, tuple[str, dict, list[str]]] = {
    "get_net_worth": ("Net worth, assets, liabilities, account balances and recent history.",
                      {"days": _int(1, 3650, 90)}, []),
    "get_cash_flow": ("Monthly income, spend and net for recent months.",
                      {"months": _int(1, 6, 6)}, []),
    "get_spending": ("Spending for a month grouped by category or merchant.",
                     {"month": {"type": "string", "pattern": MONTH_RE.pattern,
                                "description": "YYYY-MM, default current month"},
                      "group_by": {"type": "string", "enum": ["category", "merchant"],
                                   "default": "category"}}, []),
    "get_budget_status": ("Monthly budgets with spend so far and share used.", _NONE, []),
    "get_upcoming_bills": ("Subscriptions and bills due in the next N days.",
                           {"days": _int(1, 60, 7)}, []),
    "get_subscriptions": ("Active subscriptions with monthly cost and price increases.",
                          _NONE, []),
    "get_goals": ("Savings goals with progress and monthly amount needed.", _NONE, []),
    "get_holdings": ("Investment holdings by value with portfolio weights.", _NONE, []),
    "get_portfolio_risk": ("Volatility, max drawdown and beta of the portfolio.", _NONE, []),
    "get_market_regime": ("Current market regime (Normal, Elevated, Crisis) and signals.",
                          _NONE, []),
    "get_news": ("Material news, newest first, optionally for tickers or a topic.",
                 {"tickers": {"type": "array", "items": {"type": "string"}},
                  "topic": {"type": "string"}, "days": _int(1, 30, 7)}, []),
    "get_sentiment": ("Daily news and crowd sentiment for a ticker; MARKET for the market.",
                      {"ticker": {"type": "string"}, "days": _int(1, 90, 30)}, ["ticker"]),
}
_FUNCS: dict[str, Callable[..., dict]] = {n: globals()[n] for n in _TOOLS}
TOOL_NAMES = tuple(_TOOLS)
SPECS = [{"type": "function", "function": {
    "name": n, "description": d,
    "parameters": {"type": "object", "properties": p, "required": req}}}
    for n, (d, p, req) in _TOOLS.items()]


def build_toolbox(db_path: Path, today: Callable[[], date],
                  regime_provider: Callable[[], Regime],
                  closes_provider: Callable[[list[str]], pl.DataFrame]) -> Toolbox:
    """Toolbox over one database with injected clock, regime and price providers."""
    return Toolbox(db_path, today, regime_provider, closes_provider)
