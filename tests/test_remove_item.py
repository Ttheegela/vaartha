"""Unlink a bank: Plaid /item/remove, then delete the item's local rows."""

import json
from contextlib import closing
from datetime import date

import httpx
import pytest

from api.crypto import TokenBox, new_key
from api.db import connect, init_db
from api.plaid_client import PlaidClient, PlaidError
from api.plaid_fake import FAKE_ACCESS_TOKEN, FAKE_ITEM_ID, FakePlaid
from api.settings import Settings
from api.sync import link_item
from scripts.remove_item import list_items, main, remove_item

TODAY = date(2026, 10, 12)
TABLES = ("items", "accounts", "transactions", "holdings", "recurring_streams")


@pytest.fixture
def env(tmp_path):
    key = new_key()
    settings = Settings(db_path=tmp_path / "v.db", instance="owner", token_key=key)
    plaid = FakePlaid(TODAY)
    removed = []
    plaid.item_remove = lambda token: removed.append(token)
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)
        link_item(conn, plaid, TokenBox(key), "public-fake-1", TODAY)
    return settings, plaid, removed


def _counts(settings):
    with closing(connect(settings.db_path)) as conn:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def test_client_item_remove_posts_access_token():
    seen = {}

    def handler(request):
        seen["path"], seen["body"] = request.url.path, json.loads(request.content)
        return httpx.Response(200, json={"request_id": "r1"})

    PlaidClient("sandbox", "c", "s", transport=httpx.MockTransport(handler)).item_remove("tok")
    assert seen == {"path": "/item/remove", "body": {"access_token": "tok"}}


def test_fake_item_remove_signature():
    FakePlaid(TODAY).item_remove("x")


def test_remove_deletes_all_rows_and_calls_plaid_once(env):
    settings, plaid, removed = env
    assert all(n > 0 for n in _counts(settings).values())
    out = remove_item(settings, FAKE_ITEM_ID, plaid)
    assert removed == [FAKE_ACCESS_TOKEN]
    assert out["item_id"] == FAKE_ITEM_ID
    assert all(n == 0 for n in _counts(settings).values())


def test_item_not_found_still_deletes(env):
    settings, plaid, _ = env
    plaid.fail_next["item_remove"] = "ITEM_NOT_FOUND"
    plaid.item_remove = FakePlaid.item_remove.__get__(plaid)
    remove_item(settings, FAKE_ITEM_ID, plaid)
    assert _counts(settings)["items"] == 0


def test_other_plaid_error_deletes_nothing(env):
    settings, plaid, _ = env
    before = _counts(settings)
    plaid.fail_next["item_remove"] = "INTERNAL_SERVER_ERROR"
    plaid.item_remove = FakePlaid.item_remove.__get__(plaid)
    with pytest.raises(PlaidError):
        remove_item(settings, FAKE_ITEM_ID, plaid)
    assert _counts(settings) == before


def test_list_has_no_token(env, capsys):
    settings, _, _ = env
    rows = list_items(settings)
    assert rows[0][0] == FAKE_ITEM_ID and rows[0][2] == 4
    main(["--list"], settings)
    out = capsys.readouterr().out
    assert FAKE_ITEM_ID in out and FAKE_ACCESS_TOKEN not in out and "access_token" not in out
