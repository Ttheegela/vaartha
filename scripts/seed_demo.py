"""Seed a demo database: Plaid data plus budgets and goals.

Run: uv run python -m scripts.seed_demo --source fake      (offline, deterministic)
     uv run python -m scripts.seed_demo --source sandbox   (needs PLAID_CLIENT_ID/SECRET, sandbox)
Reads VARTA_DB_PATH and TOKEN_ENCRYPTION_KEY from the environment.
"""

import argparse
import json
from contextlib import closing
from datetime import date

from api.crypto import TokenBox
from api.db import connect, init_db
from api.plaid_client import PlaidAPI, PlaidClient
from api.plaid_fake import FakePlaid
from api.settings import Settings
from api.sync import link_item

SANDBOX_INSTITUTION = "ins_109508"  # verify in Plaid docs/dashboard before relying on it
SANDBOX_PRODUCTS = ["transactions", "investments"]
DEMO_BUDGETS = {"FOOD_AND_DRINK": 600, "GENERAL_MERCHANDISE": 500,
                "TRANSPORTATION": 350, "ENTERTAINMENT": 300}
# name, target amount, target date, account subtypes that fund it
DEMO_GOALS = [
    ("Emergency fund", 25000.0, "2027-06-30", ["savings"]),
    ("Japan trip", 6000.0, "2027-04-01", ["checking"]),
    ("Brokerage to 75k", 75000.0, "2028-12-31", ["brokerage"]),
]


def seed(settings: Settings, source: str, today: date, plaid: PlaidAPI | None = None) -> str:
    """Link one item from `source`, then upsert demo budgets and goals. Returns item_id."""
    if not settings.token_key:
        raise ValueError("TOKEN_ENCRYPTION_KEY is required to store Plaid tokens")
    if plaid is None:
        if source == "fake":
            plaid = FakePlaid(today)
        else:
            if not settings.plaid_configured or settings.plaid_env != "sandbox":
                raise ValueError(
                    "sandbox seed needs PLAID_CLIENT_ID/PLAID_SECRET and PLAID_ENV=sandbox")
            plaid = PlaidClient("sandbox", settings.plaid_client_id, settings.plaid_secret)
    public_token = plaid.sandbox_public_token_create(SANDBOX_INSTITUTION, SANDBOX_PRODUCTS)
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)
        item_id = link_item(conn, plaid, TokenBox(settings.token_key), public_token, today)
        conn.executemany(
            "INSERT OR REPLACE INTO budgets (pfc_primary, monthly_limit) VALUES (?, ?)",
            list(DEMO_BUDGETS.items()))
        by_subtype: dict[str, list[str]] = {}
        for r in conn.execute("SELECT account_id, subtype FROM accounts"):
            by_subtype.setdefault(r["subtype"], []).append(r["account_id"])
        conn.executemany("DELETE FROM goals WHERE name=?", [(g[0],) for g in DEMO_GOALS])
        conn.executemany(
            "INSERT INTO goals (name, target_amount, target_date, account_ids) VALUES (?,?,?,?)",
            [(name, target, when, json.dumps([a for s in subs for a in by_subtype.get(s, [])]))
             for name, target, when, subs in DEMO_GOALS])
        conn.commit()
    return item_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["fake", "sandbox"], default="fake")
    args = parser.parse_args()
    item = seed(Settings.from_env(), args.source, date.today())
    print(f"seeded item {item}")
