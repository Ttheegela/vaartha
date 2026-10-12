"""Sync service against FakePlaid: storage, encryption, pagination, failures."""

from datetime import date

import pytest

from api.crypto import TokenBox, new_key
from api.db import connect, init_db
from api.plaid_client import PlaidError
from api.plaid_fake import FAKE_ACCESS_TOKEN, FAKE_INSTITUTION, FAKE_ITEM_ID, FakePlaid
from api.sync import link_item, sync_all, sync_item

TODAY = date(2026, 10, 12)


@pytest.fixture
def env(tmp_path):
    conn = connect(tmp_path / "v.db")
    init_db(conn)
    return conn, FakePlaid(TODAY), TokenBox(new_key())


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_link_stores_encrypted_token_and_syncs(env):
    conn, plaid, box = env
    item_id = link_item(conn, plaid, box, "public-fake-1", TODAY)
    assert item_id == FAKE_ITEM_ID
    row = conn.execute(
        "SELECT access_token_enc, institution, txn_cursor, status FROM items").fetchone()
    assert FAKE_ACCESS_TOKEN.encode() not in row["access_token_enc"]
    assert box.open(row["access_token_enc"]) == FAKE_ACCESS_TOKEN
    assert row["institution"] == FAKE_INSTITUTION
    assert row["txn_cursor"] == "done"
    assert row["status"] == "active"
    assert _count(conn, "accounts") == 4
    assert _count(conn, "transactions") == len(plaid.data["transactions"])
    assert _count(conn, "holdings") == 4
    assert _count(conn, "networth_snapshots") == 1


def test_resync_is_idempotent(env):
    conn, plaid, box = env
    link_item(conn, plaid, box, "public-fake-1", TODAY)
    before = _count(conn, "transactions")
    assert sync_item(conn, plaid, box, FAKE_ITEM_ID) == {"added": 0, "modified": 0, "removed": 0}
    assert _count(conn, "transactions") == before


def test_modified_and_removed_applied(env):
    conn, plaid, box = env
    link_item(conn, plaid, box, "public-fake-1", TODAY)
    before = _count(conn, "transactions")
    first, second = plaid.data["transactions"][0], plaid.data["transactions"][1]
    plaid.modify_and_remove(first["transaction_id"], 999.0, second["transaction_id"])
    assert sync_item(conn, plaid, box, FAKE_ITEM_ID) == {"added": 0, "modified": 1, "removed": 1}
    amt = conn.execute("SELECT amount FROM transactions WHERE txn_id=?",
                       (first["transaction_id"],)).fetchone()[0]
    assert amt == 999.0
    gone = conn.execute("SELECT COUNT(*) FROM transactions WHERE txn_id=?",
                        (second["transaction_id"],)).fetchone()[0]
    assert gone == 0
    assert _count(conn, "transactions") == before - 1
    assert sync_item(conn, plaid, box, FAKE_ITEM_ID) == {"added": 0, "modified": 0, "removed": 0}
    assert _count(conn, "transactions") == before - 1
    assert conn.execute("SELECT txn_cursor FROM items").fetchone()[0] == "done"


def test_mutation_during_pagination_restarts(env):
    conn, plaid, box = env
    plaid.mutate_once = True
    link_item(conn, plaid, box, "public-fake-1", TODAY)
    assert conn.execute("SELECT txn_cursor FROM items").fetchone()[0] == "done"
    assert _count(conn, "transactions") == len(plaid.data["transactions"])


def test_failure_mid_sync_saves_no_cursor(env):
    conn, plaid, box = env
    plaid.fail_next["transactions_sync"] = "INTERNAL_SERVER_ERROR"
    with pytest.raises(PlaidError):
        link_item(conn, plaid, box, "public-fake-1", TODAY)
    row = conn.execute("SELECT txn_cursor FROM items").fetchone()
    assert row["txn_cursor"] is None
    assert _count(conn, "transactions") == 0


def test_login_required_marks_item_and_sync_all_reports(env):
    conn, plaid, box = env
    link_item(conn, plaid, box, "public-fake-1", TODAY)
    plaid.fail_next["accounts_get"] = "ITEM_LOGIN_REQUIRED"
    assert sync_all(conn, plaid, box, TODAY) == {FAKE_ITEM_ID: "ITEM_LOGIN_REQUIRED"}
    assert conn.execute("SELECT status FROM items").fetchone()[0] == "login_required"


def test_no_investments_still_syncs(tmp_path):
    conn = connect(tmp_path / "v.db")
    init_db(conn)
    plaid = FakePlaid(TODAY, investments=False)
    link_item(conn, plaid, TokenBox(new_key()), "public-fake-1", TODAY)
    assert _count(conn, "holdings") == 0
    assert _count(conn, "transactions") > 0


def test_networth_snapshot_values(env):
    conn, plaid, box = env
    link_item(conn, plaid, box, "public-fake-1", TODAY)
    row = conn.execute("SELECT date, assets, liabilities FROM networth_snapshots").fetchone()
    assert row["date"] == TODAY.isoformat()
    assert row["assets"] == pytest.approx(6420.12 + 18000.00 + 56302.00)
    assert row["liabilities"] == pytest.approx(1240.55)


def test_failure_on_third_page_saves_nothing(tmp_path):
    conn = connect(tmp_path / "v.db")
    init_db(conn)
    plaid = FakePlaid(TODAY, page_size=100)
    plaid.fail_on_page = 2
    with pytest.raises(PlaidError):
        link_item(conn, plaid, TokenBox(new_key()), "public-fake-1", TODAY)
    assert conn.execute("SELECT txn_cursor FROM items").fetchone()[0] is None
    assert _count(conn, "items") == 1
    assert _count(conn, "transactions") == 0


def _add_item(conn, box, item_id, token):
    conn.execute("INSERT INTO items (item_id, access_token_enc) VALUES (?, ?)",
                 (item_id, box.seal(token)))
    conn.commit()


def test_sync_all_isolates_login_required_item(env):
    conn, plaid, box = env
    link_item(conn, plaid, box, "public-fake-1", TODAY)
    _add_item(conn, box, "item-2", "access-bad")
    plaid.login_required_tokens.add("access-bad")
    result = sync_all(conn, plaid, box, TODAY)
    assert result == {FAKE_ITEM_ID: "ok", "item-2": "ITEM_LOGIN_REQUIRED"}
    assert _count(conn, "transactions") == len(plaid.data["transactions"])
    status = conn.execute("SELECT status FROM items WHERE item_id='item-2'").fetchone()[0]
    assert status == "login_required"
    assert _count(conn, "networth_snapshots") == 1


def test_sync_all_survives_non_plaid_error(env):
    conn, plaid, box = env
    link_item(conn, plaid, box, "public-fake-1", TODAY)
    _add_item(conn, TokenBox(new_key()), "item-2", "access-x")  # sealed with another key
    assert sync_all(conn, plaid, box, TODAY) == {FAKE_ITEM_ID: "ok", "item-2": "ERROR"}
    assert _count(conn, "networth_snapshots") == 1
