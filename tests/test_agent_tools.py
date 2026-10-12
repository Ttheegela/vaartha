"""Advisor toolbox over a DB seeded through the real sync path and offline news."""

import json
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from api.agent_tools import TOOL_NAMES, build_toolbox
from api.crypto import TokenBox, new_key
from api.db import connect, init_db
from api.plaid_fake import FakePlaid
from api.settings import Settings
from api.sync import link_item
from core.regime import compute_regime
from scripts.refresh_news import run

TODAY = date(2026, 10, 12)
NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)
DAYS = 60


def _closes(tickers: list[str]) -> pl.DataFrame:
    rows = [{"date": TODAY - timedelta(days=DAYS - i), "ticker": t,
             "close": 100.0 + i + (3 if i % 2 and t != "SPY" else 0)}
            for t in tickers for i in range(DAYS)]
    return pl.DataFrame(rows)


def _box(path, closes=_closes):
    return build_toolbox(path, lambda: TODAY, lambda: NORMAL, closes)


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "v.db"
    conn = connect(path)
    init_db(conn)
    link_item(conn, FakePlaid(TODAY), TokenBox(new_key()), "public-fake-1", TODAY)
    conn.execute("INSERT INTO budgets VALUES ('FOOD_AND_DRINK', 500)")
    conn.commit()
    conn.close()
    run(Settings(db_path=path, instance="demo"), offline=True,
        now=datetime(2026, 10, 12, 12, tzinfo=UTC))
    return _box(path)


@pytest.fixture
def empty(tmp_path):
    path = tmp_path / "e.db"
    conn = connect(path)
    init_db(conn)
    conn.close()
    return _box(path)


def test_specs_cover_all_tools(seeded):
    assert [s["function"]["name"] for s in seeded.specs] == list(TOOL_NAMES)
    assert len(TOOL_NAMES) == 12
    for s in seeded.specs:
        assert s["type"] == "function"
        assert s["function"]["parameters"]["type"] == "object"


def test_net_worth_has_no_account_identifiers(seeded):
    out = seeded.call("get_net_worth", {})
    assert out["net"] == pytest.approx(79481.57)
    text = json.dumps(out)
    for bad in ("acc-", "1234", "9012", "access"):
        assert bad not in text
    assert 1 <= len(out["history"]) <= 12


def test_upcoming_bills_window(seeded):
    out = seeded.call("get_upcoming_bills", {"days": 7})
    assert out["from"] == TODAY.isoformat()
    for it in out["items"]:
        assert TODAY.isoformat() <= it["due"] <= (TODAY + timedelta(days=7)).isoformat()
    assert out["total"] == pytest.approx(sum(i["amount"] for i in out["items"]), abs=0.02)


def test_subscriptions_flag_netflix_price_up(seeded):
    items = {i["merchant"]: i for i in seeded.call("get_subscriptions", {})["items"]}
    assert items["Netflix"]["price_up"] > 0
    assert items["Spotify"]["price_up"] is None


def test_get_news_ids_and_topic_filter(seeded):
    out = seeded.call("get_news", {})
    assert out["items"] and len(out["items"]) <= 10
    assert all(isinstance(i["id"], int) for i in out["items"])
    assert seeded.call("get_news", {"topic": "no-such-topic"})["items"] == []


def test_bad_calls_return_errors(seeded):
    for name, args in [("nope", {}), ("get_goals", "{not json"), ("get_goals", {"x": 1}),
                       ("get_spending", {"month": "2026-13"}),
                       ("get_upcoming_bills", {"days": "abc"})]:
        assert "error" in seeded.call(name, args)


def test_days_are_clamped(seeded):
    out = seeded.call("get_upcoming_bills", {"days": 10_000})
    assert out["to"] == (TODAY + timedelta(days=60)).isoformat()


def test_risk_uses_closes_provider(tmp_path, seeded):
    assert "volatility" in seeded.call("get_portfolio_risk", {})

    def boom(_):
        raise RuntimeError("down")

    broken = _box(tmp_path / "v.db", boom)
    assert "error" in broken.call("get_portfolio_risk", {})


def test_remaining_tools_run(seeded):
    for name in ("get_cash_flow", "get_spending", "get_budget_status", "get_goals",
                 "get_holdings", "get_market_regime", "get_sentiment"):
        args = {"ticker": "NVDA"} if name == "get_sentiment" else {}
        assert "error" not in seeded.call(name, args), name
    assert seeded.call("get_budget_status", {})["items"][0]["limit"] == 500


def test_empty_db(empty):
    for name in TOOL_NAMES:
        out = empty.call(name, {"ticker": "NVDA"} if name == "get_sentiment" else {})
        if name == "get_portfolio_risk":
            assert out == {"error": "no holdings"}
        else:
            assert "error" not in out, (name, out)
    assert empty.call("get_news", {})["items"] == []
