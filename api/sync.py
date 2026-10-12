"""All Plaid-driven writes: link, sync, net-worth snapshot, recurring refresh.

Plaid amount sign is preserved: positive = money out.
"""

import logging
import sqlite3
from datetime import UTC, date, datetime

import polars as pl

from api.crypto import TokenBox
from api.plaid_client import PlaidAPI, PlaidError
from core.recurring import STREAM_COLUMNS, detect_recurring

log = logging.getLogger("varta.sync")

ASSET_TYPES = ("depository", "investment")
LIABILITY_TYPES = ("credit", "loan")
RESTART_CODE = "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"
LOGIN_REQUIRED = "ITEM_LOGIN_REQUIRED"
NO_INVESTMENTS = {"PRODUCTS_NOT_SUPPORTED", "NO_INVESTMENT_ACCOUNTS", "PRODUCT_NOT_ENABLED"}
MAX_SYNC_RESTARTS = 3


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def link_item(conn: sqlite3.Connection, plaid: PlaidAPI, box: TokenBox,
              public_token: str, today: date) -> str:
    """Exchange a public token, store the encrypted access token, then sync everything."""
    access_token, item_id = plaid.exchange_public_token(public_token)
    conn.execute(
        "INSERT INTO items (item_id, access_token_enc, status) VALUES (?, ?, 'active') "
        "ON CONFLICT(item_id) DO UPDATE SET access_token_enc=excluded.access_token_enc, "
        "status='active'",
        (item_id, box.seal(access_token)),
    )
    conn.commit()
    sync_item(conn, plaid, box, item_id)
    refresh_recurring(conn, today)
    snapshot_networth(conn, today)
    return item_id


def _pull_transactions(plaid: PlaidAPI, token: str, cursor: str | None):
    for _ in range(MAX_SYNC_RESTARTS + 1):
        added, modified, removed, next_cursor = [], [], [], cursor
        try:
            while True:
                page = plaid.transactions_sync(token, next_cursor)
                added += page["added"]
                modified += page["modified"]
                removed += page["removed"]
                next_cursor = page["next_cursor"]
                if not page["has_more"]:
                    return added, modified, removed, next_cursor
        except PlaidError as exc:
            if exc.code != RESTART_CODE:
                raise
            log.info("transactions changed during pagination; restarting")
    raise PlaidError(RESTART_CODE, "gave up after restarts", 0)


def _txn_row(t: dict) -> tuple:
    pfc = t.get("personal_finance_category") or {}
    return (t["transaction_id"], t["account_id"], t["date"], t["amount"],
            t.get("merchant_name") or t.get("name"), pfc.get("primary"), pfc.get("detailed"),
            int(bool(t.get("pending"))))


def sync_item(conn: sqlite3.Connection, plaid: PlaidAPI, box: TokenBox,
              item_id: str) -> dict[str, int]:
    """Sync one item; commit only after Plaid data is fully fetched. Returns change counts."""
    row = conn.execute("SELECT access_token_enc, txn_cursor FROM items WHERE item_id=?",
                       (item_id,)).fetchone()
    token = box.open(row["access_token_enc"])
    try:
        acc = plaid.accounts_get(token)
        added, modified, removed, cursor = _pull_transactions(plaid, token, row["txn_cursor"])
        try:
            inv = plaid.investments_holdings_get(token)
        except PlaidError as exc:
            if exc.code not in NO_INVESTMENTS:
                raise
            inv = {"holdings": [], "securities": []}
    except PlaidError as exc:
        if exc.code == LOGIN_REQUIRED:
            conn.execute("UPDATE items SET status='login_required' WHERE item_id=?", (item_id,))
            conn.commit()
        raise

    with conn:
        conn.execute("UPDATE items SET institution=?, txn_cursor=?, status='active', "
                     "last_synced_at=? WHERE item_id=?",
                     (acc["item"].get("institution_name"), cursor, _now(), item_id))
        conn.executemany(
            "INSERT INTO accounts (account_id, item_id, name, type, subtype, mask, "
            "balance_current, balance_available, currency) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(account_id) DO UPDATE SET item_id=excluded.item_id, "
            "name=excluded.name, type=excluded.type, subtype=excluded.subtype, "
            "mask=excluded.mask, balance_current=excluded.balance_current, "
            "balance_available=excluded.balance_available, currency=excluded.currency",
            [(a["account_id"], item_id, a["name"], a["type"], a["subtype"], a.get("mask"),
              a["balances"].get("current"), a["balances"].get("available"),
              a["balances"].get("iso_currency_code")) for a in acc["accounts"]])
        conn.executemany(
            "INSERT OR REPLACE INTO transactions (txn_id, account_id, date, amount, merchant, "
            "pfc_primary, pfc_detailed, pending) VALUES (?,?,?,?,?,?,?,?)",
            [_txn_row(t) for t in added + modified])
        conn.executemany("DELETE FROM transactions WHERE txn_id=?",
                         [(r["transaction_id"],) for r in removed])
        conn.executemany(
            "INSERT OR REPLACE INTO securities (security_id, ticker, name, type) VALUES (?,?,?,?)",
            [(s["security_id"], s.get("ticker_symbol"), s.get("name"), s.get("type"))
             for s in inv["securities"]])
        conn.execute("DELETE FROM holdings WHERE account_id IN "
                     "(SELECT account_id FROM accounts WHERE item_id=?)", (item_id,))
        conn.executemany(
            "INSERT INTO holdings (account_id, security_id, quantity, cost_basis, value, as_of) "
            "VALUES (?,?,?,?,?,?)",
            [(h["account_id"], h["security_id"], h.get("quantity"), h.get("cost_basis"),
              h.get("institution_value"), _now()) for h in inv["holdings"]])
    return {"added": len(added), "modified": len(modified), "removed": len(removed)}


def snapshot_networth(conn: sqlite3.Connection, today: date) -> None:
    """Write today's assets/liabilities from cached balances (one row per day)."""
    a_ph = ",".join("?" * len(ASSET_TYPES))
    l_ph = ",".join("?" * len(LIABILITY_TYPES))
    assets = conn.execute(f"SELECT COALESCE(SUM(balance_current),0) FROM accounts "
                          f"WHERE type IN ({a_ph})", ASSET_TYPES).fetchone()[0]
    liabilities = conn.execute(f"SELECT COALESCE(SUM(balance_current),0) FROM accounts "
                               f"WHERE type IN ({l_ph})", LIABILITY_TYPES).fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO networth_snapshots (date, assets, liabilities) "
                 "VALUES (?,?,?)", (today.isoformat(), assets, liabilities))
    conn.commit()


def refresh_recurring(conn: sqlite3.Connection, today: date) -> int:
    """Rebuild recurring_streams from non-pending transactions; returns stream count."""
    rows = conn.execute("SELECT account_id, date, amount, merchant, pfc_primary, pfc_detailed "
                        "FROM transactions WHERE pending=0").fetchall()
    txns = pl.DataFrame(
        [dict(r) for r in rows],
        schema={"account_id": pl.Utf8, "date": pl.Utf8, "amount": pl.Float64, "merchant": pl.Utf8,
                "pfc_primary": pl.Utf8, "pfc_detailed": pl.Utf8},
    ).with_columns(pl.col("date").str.to_date())
    streams = detect_recurring(txns, today)
    with conn:
        conn.execute("DELETE FROM recurring_streams")
        conn.executemany(
            f"INSERT INTO recurring_streams ({', '.join(STREAM_COLUMNS)}) "
            f"VALUES ({', '.join('?' * len(STREAM_COLUMNS))})",
            [tuple(v.isoformat() if isinstance(v, date) else v for v in r)
             for r in streams.select(STREAM_COLUMNS).iter_rows()])
    return streams.height


def sync_all(conn: sqlite3.Connection, plaid: PlaidAPI, box: TokenBox,
             today: date) -> dict[str, str]:
    """Sync every item; one failing item never blocks the others."""
    results: dict[str, str] = {}
    for (item_id,) in conn.execute("SELECT item_id FROM items").fetchall():
        try:
            sync_item(conn, plaid, box, item_id)
            results[item_id] = "ok"
        except PlaidError as exc:
            log.warning("sync failed for %s: %s", item_id, exc.code)
            results[item_id] = exc.code
        except Exception as exc:  # noqa: BLE001 - isolate items; never log the token
            log.warning("sync failed for %s: %s", item_id, type(exc).__name__)
            results[item_id] = "ERROR"
    refresh_recurring(conn, today)
    snapshot_networth(conn, today)
    return results
