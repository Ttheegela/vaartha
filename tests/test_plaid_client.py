"""PlaidClient over a mock transport: paths, auth headers, error mapping."""

import json

import httpx
import pytest

from api.plaid_client import PLAID_HOSTS, PlaidClient, PlaidError

SECRET = "super-secret-value"


def _client(handler):
    return PlaidClient("sandbox", "client-id-1", SECRET, transport=httpx.MockTransport(handler))


def test_auth_in_headers_not_body():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"link_token": "link-sandbox-1"})

    token = _client(handler).link_token_create("owner", ["transactions", "investments"])
    assert token == "link-sandbox-1"
    assert seen["url"] == PLAID_HOSTS["sandbox"] + "/link/token/create"
    assert seen["headers"]["PLAID-CLIENT-ID"] == "client-id-1"
    assert seen["headers"]["PLAID-SECRET"] == SECRET
    assert SECRET not in json.dumps(seen["body"])
    assert seen["body"]["user"] == {"client_user_id": "owner"}
    assert seen["body"]["products"] == ["transactions", "investments"]
    assert seen["body"]["country_codes"] == ["US"]
    assert seen["body"]["transactions"] == {"days_requested": 730}


def test_exchange_returns_token_and_item():
    def handler(request):
        assert json.loads(request.content) == {"public_token": "public-1"}
        return httpx.Response(200, json={"access_token": "access-1", "item_id": "item-1"})

    assert _client(handler).exchange_public_token("public-1") == ("access-1", "item-1")


def test_transactions_sync_omits_null_cursor():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"added": [], "modified": [], "removed": [],
                                         "next_cursor": "c1", "has_more": False})

    c = _client(handler)
    c.transactions_sync("access-1", None)
    c.transactions_sync("access-1", "c1")
    assert "cursor" not in bodies[0]
    assert bodies[1]["cursor"] == "c1"


def test_error_maps_to_plaid_error_without_secret():
    def handler(request):
        return httpx.Response(400, json={"error_code": "ITEM_LOGIN_REQUIRED",
                                         "error_message": "login details changed"})

    with pytest.raises(PlaidError) as exc:
        _client(handler).accounts_get("access-1")
    assert exc.value.code == "ITEM_LOGIN_REQUIRED"
    assert exc.value.status == 400
    assert SECRET not in str(exc.value)


def test_non_json_error_body():
    def handler(request):
        return httpx.Response(502, text="<html>bad gateway</html>")

    with pytest.raises(PlaidError) as exc:
        _client(handler).accounts_get("access-1")
    assert exc.value.code == "HTTP_502"


def test_network_error_becomes_plaid_error():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(PlaidError) as exc:
        _client(handler).accounts_get("access-1")
    assert exc.value.code == "NETWORK_ERROR"
