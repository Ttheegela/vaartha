"""Read endpoints over a DB seeded through the real sync path (FakePlaid)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.crypto import TokenBox, new_key
from api.db import connect, init_db
from api.main import create_app
from api.plaid_fake import FakePlaid
from api.settings import Settings
from api.sync import link_item
from core.regime import compute_regime

TODAY = date(2026, 10, 12)
NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)


def _client(path):
    app = create_app(Settings(db_path=path, instance="demo"), regime_provider=lambda: NORMAL,
                     today=lambda: TODAY)
    return TestClient(app)


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "v.db"
    conn = connect(path)
    init_db(conn)
    link_item(conn, FakePlaid(TODAY), TokenBox(new_key()), "public-fake-1", TODAY)
    return _client(path)


@pytest.fixture
def empty(tmp_path):
    return _client(tmp_path / "v.db")


def test_accounts(seeded):
    body = seeded.get("/api/accounts").json()
    assert len(body["accounts"]) == 4
    card = next(a for a in body["accounts"] if a["type"] == "credit")
    assert card["is_liability"] is True and card["institution"] == "First Platypus Bank"
    assert body["assets"] == pytest.approx(80722.12)
    assert body["liabilities"] == pytest.approx(1240.55)
    assert body["items"][0]["status"] == "active"
    assert "access_token" not in str(body)


def test_networth(seeded):
    pts = seeded.get("/api/networth?days=30").json()
    assert pts == [{"date": "2026-10-12", "assets": pytest.approx(80722.12),
                    "liabilities": pytest.approx(1240.55), "net": pytest.approx(79481.57)}]
    assert seeded.get("/api/networth?days=0").status_code == 422


def test_recurring_split_and_totals(seeded):
    body = seeded.get("/api/recurring").json()
    subs = {s["merchant"]: s for s in body["subscriptions"]}
    bills = {b["merchant"] for b in body["bills"]}
    assert {"Rent", "Con Edison", "Verizon", "Geico"} == bills
    assert subs["Amazon Prime"]["monthly_amount"] == pytest.approx(139 / 12)
    expected = sum(s["monthly_amount"] for s in body["subscriptions"] if s["is_active"])
    assert body["subscriptions_monthly"] == pytest.approx(expected)
    assert body["bills_monthly"] == pytest.approx(2450 + 96.43 + 88 + 142.5)


def test_empty_db_returns_empty(empty):
    assert empty.get("/api/accounts").json() == {
        "accounts": [], "items": [], "assets": 0, "liabilities": 0}
    assert empty.get("/api/networth").json() == []
    assert empty.get("/api/recurring").json() == {"subscriptions": [], "bills": [],
                                                  "subscriptions_monthly": 0, "bills_monthly": 0}
