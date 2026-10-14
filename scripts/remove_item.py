"""Unlink a bank at Plaid and delete its data locally.

Run: uv run python -m scripts.remove_item --list
     uv run python -m scripts.remove_item <item_id> [--yes]
"""

import argparse
from contextlib import closing

from api.crypto import TokenBox
from api.db import connect
from api.plaid_client import PlaidAPI, PlaidClient, PlaidError
from api.settings import Settings

ALREADY_REMOVED = "ITEM_NOT_FOUND"


def list_items(settings: Settings) -> list[tuple[str, str | None, int]]:
    """(item_id, institution, account count) per item; never the token."""
    with closing(connect(settings.db_path)) as conn:
        return conn.execute(
            "SELECT i.item_id, i.institution, COUNT(a.account_id) FROM items i "
            "LEFT JOIN accounts a ON a.item_id = i.item_id GROUP BY i.item_id").fetchall()


def remove_item(settings: Settings, item_id: str, plaid: PlaidAPI | None = None) -> dict:
    """Revoke the item at Plaid, then delete its rows in one transaction.

    ITEM_NOT_FOUND counts as already removed; any other Plaid error raises and deletes nothing.
    Accounts, transactions, holdings and recurring streams go via ON DELETE CASCADE.
    """
    plaid = plaid or PlaidClient(settings.plaid_env, settings.plaid_client_id,
                                 settings.plaid_secret)
    box = TokenBox(settings.token_key)
    with closing(connect(settings.db_path)) as conn:
        row = conn.execute("SELECT access_token_enc FROM items WHERE item_id=?",
                           (item_id,)).fetchone()
        if row is None:
            raise KeyError(f"no such item: {item_id}")
        try:
            plaid.item_remove(box.open(row[0]))
        except PlaidError as exc:
            if exc.code != ALREADY_REMOVED:
                raise
        with conn:
            conn.execute("DELETE FROM items WHERE item_id=?", (item_id,))
    return {"item_id": item_id}


def main(argv: list[str] | None = None, settings: Settings | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("item_id", nargs="?")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)
    settings = settings or Settings.from_env()
    items = list_items(settings)
    if args.list or not args.item_id:
        for item_id, institution, n in items:
            print(f"{item_id}  {institution}  {n} accounts")
        return
    institution = next((i for k, i, _ in items if k == args.item_id), None)
    if institution is None and not any(k == args.item_id for k, _, _ in items):
        raise SystemExit(f"no such item: {args.item_id}")
    if institution is None and not args.yes:
        raise SystemExit("institution name unknown; re-run with --yes to confirm")
    prompt = f"Type the institution name to confirm ({institution}): "
    if not args.yes and input(prompt) != institution:
        raise SystemExit("not confirmed; nothing removed")
    remove_item(settings, args.item_id)
    print(f"removed {args.item_id}")


if __name__ == "__main__":
    main()
