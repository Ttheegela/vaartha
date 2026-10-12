"""Minimal Plaid REST client (httpx). Credentials travel only in headers."""

from typing import Protocol

import httpx

PLAID_HOSTS = {"sandbox": "https://sandbox.plaid.com", "production": "https://production.plaid.com"}
TIMEOUT_SECONDS = 30.0
CLIENT_NAME = "Vārtā"
COUNTRY_CODES = ["US"]
LANGUAGE = "en"
MAX_HISTORY_DAYS = 730
SYNC_PAGE_SIZE = 500
ERROR_TEXT_LIMIT = 200


class PlaidError(Exception):
    """A Plaid API error (or transport failure) with Plaid's error_code."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


class PlaidAPI(Protocol):
    """The Plaid calls Vārtā uses; implemented by PlaidClient and FakePlaid."""

    def link_token_create(self, user_id: str, products: list[str],
                          days_requested: int = MAX_HISTORY_DAYS) -> str: ...
    def exchange_public_token(self, public_token: str) -> tuple[str, str]: ...
    def accounts_get(self, access_token: str) -> dict: ...
    def transactions_sync(self, access_token: str, cursor: str | None) -> dict: ...
    def investments_holdings_get(self, access_token: str) -> dict: ...
    def sandbox_public_token_create(self, institution_id: str, products: list[str]) -> str: ...


class PlaidClient:
    """Thin JSON-over-HTTPS client for the endpoints in PlaidAPI."""

    def __init__(self, env: str, client_id: str, secret: str,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(
            base_url=PLAID_HOSTS[env],
            timeout=TIMEOUT_SECONDS,
            transport=transport,
            headers={"PLAID-CLIENT-ID": client_id, "PLAID-SECRET": secret},
        )

    def _post(self, path: str, body: dict) -> dict:
        """POST JSON to a Plaid path; map every failure to PlaidError."""
        try:
            resp = self._http.post(path, json=body)
        except httpx.HTTPError as exc:
            raise PlaidError("NETWORK_ERROR", type(exc).__name__, 0) from exc
        try:
            data = resp.json()
        except ValueError:
            data = None
        if resp.status_code >= 400 or data is None:
            if isinstance(data, dict) and "error_code" in data:
                raise PlaidError(data["error_code"], data.get("error_message", ""),
                                 resp.status_code)
            raise PlaidError(f"HTTP_{resp.status_code}", resp.text[:ERROR_TEXT_LIMIT],
                             resp.status_code)
        return data

    def link_token_create(self, user_id: str, products: list[str],
                          days_requested: int = MAX_HISTORY_DAYS) -> str:
        """Create a Link token for the single user of this instance."""
        data = self._post("/link/token/create", {
            "client_name": CLIENT_NAME,
            "language": LANGUAGE,
            "country_codes": COUNTRY_CODES,
            "user": {"client_user_id": user_id},
            "products": products,
            "transactions": {"days_requested": days_requested},
        })
        return data["link_token"]

    def exchange_public_token(self, public_token: str) -> tuple[str, str]:
        """Exchange Link's public token for (access_token, item_id)."""
        data = self._post("/item/public_token/exchange", {"public_token": public_token})
        return data["access_token"], data["item_id"]

    def accounts_get(self, access_token: str) -> dict:
        """Cached account balances (free endpoint) plus the item."""
        return self._post("/accounts/get", {"access_token": access_token})

    def transactions_sync(self, access_token: str, cursor: str | None) -> dict:
        """One page of /transactions/sync; omit cursor for full history."""
        body: dict = {"access_token": access_token, "count": SYNC_PAGE_SIZE}
        if cursor:
            body["cursor"] = cursor
        return self._post("/transactions/sync", body)

    def investments_holdings_get(self, access_token: str) -> dict:
        """Holdings and securities for the item's investment accounts."""
        return self._post("/investments/holdings/get", {"access_token": access_token})

    def sandbox_public_token_create(self, institution_id: str, products: list[str]) -> str:
        """Sandbox only: create an item without Link."""
        data = self._post("/sandbox/public_token/create", {
            "institution_id": institution_id,
            "initial_products": products,
            "options": {"transactions": {"days_requested": MAX_HISTORY_DAYS}},
        })
        return data["public_token"]
