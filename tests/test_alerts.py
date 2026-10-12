"""Alert rules on the FakePlaid-seeded DB."""

from datetime import UTC, date, datetime

import pytest

from api.agent_tools import build_toolbox
from api.alerts import generate_alerts
from api.crypto import TokenBox, new_key
from api.db import connect, init_db
from api.plaid_fake import FakePlaid
from api.sync import link_item
from core.regime import Regime, compute_regime

TODAY = date(2026, 10, 12)
NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)
ELEVATED = Regime(**{**NORMAL.__dict__, "label": "Elevated"})


@pytest.fixture
def env(tmp_path):
    conn = connect(tmp_path / "v.db")
    init_db(conn)
    link_item(conn, FakePlaid(TODAY), TokenBox(new_key()), "public-fake-1", TODAY)
    conn.commit()
    label = {"v": NORMAL}
    box = build_toolbox(tmp_path / "v.db", lambda: TODAY, lambda: label["v"], lambda t: None)
    return conn, box, label


def _texts(conn, kind):
    return [r["text"] for r in conn.execute("SELECT text FROM alerts WHERE kind = ?", (kind,))]


def test_bill_and_price_up(env):
    conn, box, _ = env
    generate_alerts(conn, box)
    assert any(t.startswith("Con Edison") and t.endswith("due Oct 14")
               for t in _texts(conn, "bill_due"))
    assert any(t.startswith("Netflix went up $") for t in _texts(conn, "price_up"))
    row = conn.execute("SELECT * FROM alerts WHERE kind = 'bill_due'").fetchone()
    assert (row["action_label"], row["action_href"]) == ("View bills", "/bills")


def test_budget(env):
    conn, box, _ = env
    conn.execute("INSERT INTO budgets VALUES ('FOOD_AND_DRINK', 1)")
    conn.commit()
    generate_alerts(conn, box)
    assert any(t.startswith("Food and drink at ") and t.endswith("% of $1 budget")
               for t in _texts(conn, "budget"))


def test_dedupe(env):
    conn, box, _ = env
    assert generate_alerts(conn, box) > 0
    assert generate_alerts(conn, box) == 0


def test_regime_change(env):
    conn, box, label = env
    generate_alerts(conn, box)
    assert _texts(conn, "regime") == []
    assert conn.execute("SELECT value FROM app_state").fetchone()[0] == "Normal"
    label["v"] = ELEVATED
    generate_alerts(conn, box)
    assert _texts(conn, "regime") == ["Market regime moved from Normal to Elevated"]


def test_sentiment_flip(env):
    conn, box, _ = env
    ticker = box.call("get_holdings", {})["items"][0]["ticker"]
    conn.execute("DELETE FROM news_scores")
    for i, (day, s) in enumerate([("2026-10-04", 0.6), ("2026-10-07", 0.5),
                                  ("2026-10-11", -0.5), ("2026-10-12", -0.6)]):
        conn.execute("INSERT INTO news_items (id, published_at, source, title) "
                     "VALUES (?, ?, 'x', 't')",
                     (i + 1, f"{day}T12:00:00+00:00"))
        conn.execute("INSERT INTO news_scores (news_id, ticker, sentiment, sentiment_conf, "
                     "scored_at) VALUES (?, ?, ?, 1, ?)",
                     (i + 1, ticker, s, datetime.now(UTC).isoformat()))
    conn.commit()
    generate_alerts(conn, box)
    assert _texts(conn, "sentiment") == [f"{ticker} news sentiment turned negative"]
