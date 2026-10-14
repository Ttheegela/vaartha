"""Deterministic in-memory Plaid for tests and the offline demo seed.

Data shapes follow Plaid's /accounts/get, /transactions/sync and
/investments/holdings/get responses (only the fields Vārtā reads).
"""

import random
from datetime import date, timedelta

from api.plaid_client import PlaidError

FAKE_INSTITUTION = "First Platypus Bank"
FAKE_ITEM_ID = "item-fake-1"
FAKE_ACCESS_TOKEN = "access-fake-1"
HISTORY_DAYS = 400
SEED = 42

ACCOUNTS = [
    ("acc-checking", "Everyday Checking", "depository", "checking", "1234", 6420.12),
    ("acc-savings", "High-Yield Savings", "depository", "savings", "5678", 18000.00),
    ("acc-credit", "Platinum Card", "credit", "credit card", "9012", 1240.55),
    ("acc-brokerage", "Individual Brokerage", "investment", "brokerage", "3456", 56302.00),
]
# merchant, day of month, amount, pfc_primary, pfc_detailed
MONTHLY = [
    ("Rent", 1, 2450.00, "RENT_AND_UTILITIES", "RENT_AND_UTILITIES_RENT"),
    ("Spotify", 3, 11.99, "ENTERTAINMENT", "ENTERTAINMENT_MUSIC_AND_AUDIO"),
    ("Con Edison", 14, 96.43, "RENT_AND_UTILITIES", "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY"),
    ("Netflix", 15, 22.99, "ENTERTAINMENT", "ENTERTAINMENT_TV_AND_MOVIES"),
    ("Verizon", 18, 88.00, "RENT_AND_UTILITIES", "RENT_AND_UTILITIES_TELEPHONE"),
    ("Geico", 21, 142.50, "GENERAL_SERVICES", "GENERAL_SERVICES_INSURANCE"),
]
NETFLIX_OLD_PRICE = 20.99
PAYROLL = ("Acme Corp Payroll", -4120.00, "INCOME", "INCOME_WAGES")
PAYDAYS = (1, 15)
ANNUAL = ("Amazon Prime", 139.00, "GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES")
GROCERY_GAPS = (3, 8, 5, 11, 4, 9, 6, 13)  # irregular on purpose: not a weekly stream
SECURITIES = [
    ("sec-nvda", "NVDA", "NVIDIA Corp", "equity", 86, 143.56),
    ("sec-spy", "SPY", "SPDR S&P 500 ETF", "etf", 19, 578.00),
    ("sec-tsm", "TSM", "Taiwan Semiconductor", "equity", 48, 197.50),
    ("sec-gld", "GLD", "SPDR Gold Shares", "etf", 26, 270.00),
]


def _txn(tid: str, day: date, merchant: str, amount: float, primary: str, detailed: str,
         account: str = "acc-checking") -> dict:
    return {
        "transaction_id": tid, "account_id": account, "date": day.isoformat(),
        "amount": amount, "merchant_name": merchant, "name": merchant, "pending": False,
        "personal_finance_category": {"primary": primary, "detailed": detailed},
    }


def build_fake_dataset(today: date) -> dict:
    """Accounts, ~400 days of transactions, and holdings, deterministic for `today`."""
    rng = random.Random(SEED)
    start = today - timedelta(days=HISTORY_DAYS)
    txns: list[dict] = []
    n = 0

    def add(day, merchant, amount, primary, detailed, account="acc-checking"):
        nonlocal n
        n += 1
        txns.append(_txn(f"txn-{n:05d}", day, merchant, amount, primary, detailed, account))

    d = start.replace(day=1)
    while d <= today:
        for merchant, dom, amount, primary, detailed in MONTHLY:
            day = d.replace(day=min(dom, 28))
            if start <= day <= today:
                old = merchant == "Netflix" and (today - day).days > 60
                price = NETFLIX_OLD_PRICE if old else amount
                add(day, merchant, price, primary, detailed,
                    "acc-credit" if primary == "ENTERTAINMENT" else "acc-checking")
        for dom in PAYDAYS:
            day = d.replace(day=dom)
            if start <= day <= today:
                add(day, PAYROLL[0], PAYROLL[1], PAYROLL[2], PAYROLL[3])
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)

    for back in (10, 375):
        add(today - timedelta(days=back), *ANNUAL, account="acc-credit")

    day, i = start, 0
    while day <= today:
        add(day, "Whole Foods", round(rng.uniform(45, 140), 2),
            "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES", "acc-credit")
        day += timedelta(days=GROCERY_GAPS[i % len(GROCERY_GAPS)])
        i += 1

    add(today - timedelta(days=2), "Whole Foods", 64.20,
        "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES", "acc-credit")  # guarantees spend this month

    for _ in range(60):
        day = today - timedelta(days=rng.randint(0, HISTORY_DAYS))
        add(day, rng.choice(["Sweetgreen", "Blue Bottle", "Uber", "Target"]),
            round(rng.uniform(8, 60), 2), "FOOD_AND_DRINK", "FOOD_AND_DRINK_RESTAURANT",
            "acc-credit")

    accounts = [{
        "account_id": aid, "name": name, "official_name": name, "type": typ, "subtype": sub,
        "mask": mask,
        "balances": {"current": bal, "available": bal if typ == "depository" else None,
                     "iso_currency_code": "USD"},
    } for aid, name, typ, sub, mask, bal in ACCOUNTS]
    securities = [{"security_id": sid, "ticker_symbol": t, "name": nm, "type": ty}
                  for sid, t, nm, ty, _, _ in SECURITIES]
    holdings = [{"account_id": "acc-brokerage", "security_id": sid, "quantity": q,
                 "cost_basis": round(q * px * 0.8, 2), "institution_value": round(q * px, 2),
                 "institution_price": px}
                for sid, _, _, _, q, px in SECURITIES]
    return {"accounts": accounts, "transactions": sorted(txns, key=lambda t: t["date"]),
            "holdings": holdings, "securities": securities}


class FakePlaid:
    """Implements PlaidAPI over build_fake_dataset; paginates /transactions/sync."""

    def __init__(self, today: date, page_size: int = 100, investments: bool = True) -> None:
        self.data = build_fake_dataset(today)
        self.page_size = page_size
        self.investments = investments
        self.fail_next: dict[str, str] = {}
        self.mutate_once = False
        self.fail_on_page: int | None = None  # 0-based sync page to fail once
        self.login_required_tokens: set[str] = set()
        self.link_calls: list[dict] = []
        self._pending: dict = {"modified": [], "removed": []}

    def _maybe_fail(self, method: str) -> None:
        code = self.fail_next.pop(method, None)
        if code:
            raise PlaidError(code, "simulated", 400)

    def link_token_create(self, user_id, products, additional_consented=None,
                          days_requested=730, redirect_uri=None, access_token=None):
        """Record the call and return a fixed link token."""
        self._maybe_fail("link_token_create")
        self.link_calls.append({"products": products, "additional_consented": additional_consented,
                                "redirect_uri": redirect_uri, "access_token": access_token})
        return "link-fake-1"

    def exchange_public_token(self, public_token):
        self._maybe_fail("exchange_public_token")
        return FAKE_ACCESS_TOKEN, FAKE_ITEM_ID

    def accounts_get(self, access_token):
        self._maybe_fail("accounts_get")
        if access_token in self.login_required_tokens:
            raise PlaidError("ITEM_LOGIN_REQUIRED", "simulated", 400)
        return {"accounts": self.data["accounts"],
                "item": {"item_id": FAKE_ITEM_ID, "institution_name": FAKE_INSTITUTION}}

    def transactions_sync(self, access_token, cursor):
        self._maybe_fail("transactions_sync")
        txns = self.data["transactions"]
        if cursor == "done":
            out = {"added": [], **self._pending, "next_cursor": "done", "has_more": False}
            self._pending = {"modified": [], "removed": []}
            return out
        page = int(cursor[1:]) if cursor else 0
        if page == 1 and self.mutate_once:
            self.mutate_once = False
            raise PlaidError("TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION", "simulated", 400)
        if page == self.fail_on_page:
            self.fail_on_page = None
            raise PlaidError("INTERNAL_SERVER_ERROR", "simulated", 500)
        chunk = txns[page * self.page_size:(page + 1) * self.page_size]
        has_more = (page + 1) * self.page_size < len(txns)
        return {"added": chunk, "modified": [], "removed": [],
                "next_cursor": f"p{page + 1}" if has_more else "done", "has_more": has_more}

    def investments_holdings_get(self, access_token):
        self._maybe_fail("investments_holdings_get")
        if not self.investments:
            raise PlaidError("PRODUCTS_NOT_SUPPORTED", "no investments", 400)
        return {"holdings": self.data["holdings"], "securities": self.data["securities"]}

    def sandbox_public_token_create(self, institution_id, products):
        return "public-fake-1"

    def item_remove(self, access_token):
        """Pretend to unlink the item."""
        self._maybe_fail("item_remove")

    def modify_and_remove(self, modified_id: str, new_amount: float, removed_id: str) -> None:
        """Queue a modified and a removed transaction for the next incremental sync."""
        txn = next(t for t in self.data["transactions"] if t["transaction_id"] == modified_id)
        self._pending = {"modified": [{**txn, "amount": new_amount}],
                         "removed": [{"transaction_id": removed_id}]}
