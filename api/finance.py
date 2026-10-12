"""Read-only finance endpoints over SQLite. All writes live in api/sync.py."""

from collections.abc import Callable
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.db import connect
from api.sync import LIABILITY_TYPES

WEEKS_PER_MONTH = 52 / 12
MONTHS_PER_YEAR = 12
DEFAULT_NETWORTH_DAYS = 365
MAX_NETWORTH_DAYS = 3650


class ItemOut(BaseModel):
    """A linked institution connection."""

    item_id: str
    institution: str | None
    status: str
    last_synced_at: str | None


class AccountOut(BaseModel):
    """One account with its cached balances."""

    account_id: str
    institution: str | None
    name: str
    type: str
    subtype: str | None
    mask: str | None
    balance_current: float | None
    balance_available: float | None
    is_liability: bool


class AccountsOut(BaseModel):
    """Accounts, items and asset/liability totals."""

    accounts: list[AccountOut]
    items: list[ItemOut]
    assets: float
    liabilities: float


class NetWorthPoint(BaseModel):
    """One daily net-worth snapshot."""

    date: str
    assets: float
    liabilities: float
    net: float


class RecurringOut(BaseModel):
    """A detected recurring stream with its monthly-normalized amount."""

    stream_id: str
    merchant: str
    kind: Literal["subscription", "bill", "income"]
    frequency: Literal["WEEKLY", "MONTHLY", "ANNUALLY"]
    avg_amount: float
    last_amount: float
    last_date: str
    predicted_next_date: str
    is_active: bool
    monthly_amount: float


class RecurringListOut(BaseModel):
    """Subscriptions and bills with active monthly totals."""

    subscriptions: list[RecurringOut]
    bills: list[RecurringOut]
    subscriptions_monthly: float
    bills_monthly: float


def monthly_amount(amount: float, frequency: str) -> float:
    """Average monthly cost of a recurring charge."""
    if frequency == "WEEKLY":
        return amount * WEEKS_PER_MONTH
    if frequency == "ANNUALLY":
        return amount / MONTHS_PER_YEAR
    return amount


def build_finance_router(db_path: Path, today: Callable[[], date]) -> APIRouter:
    """Routes for accounts, net worth and recurring charges."""
    router = APIRouter(prefix="/api")

    @router.get("/accounts", response_model=AccountsOut)
    def accounts() -> AccountsOut:
        """Linked accounts with cached balances, items, and asset/liability totals."""
        with closing(connect(db_path)) as conn:
            items = [ItemOut(**dict(r)) for r in conn.execute(
                "SELECT item_id, institution, status, last_synced_at "
                "FROM items ORDER BY institution")]
            rows = conn.execute(
                "SELECT a.account_id, i.institution, a.name, a.type, a.subtype, a.mask, "
                "a.balance_current, a.balance_available FROM accounts a "
                "JOIN items i USING (item_id) ORDER BY i.institution, a.name").fetchall()
        accts = [AccountOut(**dict(r), is_liability=r["type"] in LIABILITY_TYPES) for r in rows]
        return AccountsOut(
            accounts=accts, items=items,
            assets=sum(a.balance_current or 0 for a in accts if not a.is_liability),
            liabilities=sum(a.balance_current or 0 for a in accts if a.is_liability),
        )

    @router.get("/networth", response_model=list[NetWorthPoint])
    def networth(days: int = Query(DEFAULT_NETWORTH_DAYS, ge=1, le=MAX_NETWORTH_DAYS)):
        """Daily net-worth snapshots for the last `days` days, oldest first."""
        cutoff = (today() - timedelta(days=days)).isoformat()
        with closing(connect(db_path)) as conn:
            rows = conn.execute("SELECT date, assets, liabilities FROM networth_snapshots "
                                "WHERE date >= ? ORDER BY date", (cutoff,)).fetchall()
        return [NetWorthPoint(**dict(r), net=r["assets"] - r["liabilities"]) for r in rows]

    @router.get("/recurring", response_model=RecurringListOut)
    def recurring() -> RecurringListOut:
        """Detected subscriptions and bills with monthly-normalized totals (inactive excluded)."""
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT stream_id, merchant, kind, frequency, avg_amount, last_amount, last_date, "
                "predicted_next_date, is_active FROM recurring_streams "
                "ORDER BY predicted_next_date").fetchall()
        streams = [RecurringOut(**{**dict(r), "is_active": bool(r["is_active"])},
                                monthly_amount=monthly_amount(r["last_amount"], r["frequency"]))
                   for r in rows]
        subs = [s for s in streams if s.kind == "subscription"]
        bills = [s for s in streams if s.kind == "bill"]
        return RecurringListOut(
            subscriptions=subs, bills=bills,
            subscriptions_monthly=sum(s.monthly_amount for s in subs if s.is_active),
            bills_monthly=sum(s.monthly_amount for s in bills if s.is_active),
        )

    return router
