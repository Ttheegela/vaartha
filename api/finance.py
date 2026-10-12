"""Read-only finance endpoints over SQLite. All writes live in api/sync.py."""

import json
import re
from collections.abc import Callable
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.db import connect
from api.sync import LIABILITY_TYPES

WEEKS_PER_MONTH = 52 / 12
MONTHS_PER_YEAR = 12
DEFAULT_NETWORTH_DAYS = 365
MAX_NETWORTH_DAYS = 3650
EXCLUDED_PRIMARY = ("TRANSFER_IN", "TRANSFER_OUT")
EXCLUDED_DETAILED = ("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",)
CASH_FLOW_MONTHS = 6
TOP_MERCHANTS = 10
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# Shared WHERE fragment; parameters: EXCLUDED_PRIMARY + EXCLUDED_DETAILED
_COUNTED = (
    f"pending=0 AND COALESCE(pfc_primary,'') NOT IN ({','.join('?' * len(EXCLUDED_PRIMARY))}) "
    f"AND COALESCE(pfc_detailed,'') NOT IN ({','.join('?' * len(EXCLUDED_DETAILED))})"
)
_COUNTED_ARGS = EXCLUDED_PRIMARY + EXCLUDED_DETAILED


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


class CategorySpend(BaseModel):
    """Total spend for one category."""

    category: str
    amount: float


class MerchantSpendOut(BaseModel):
    """Total spend and transaction count for one merchant."""

    merchant: str
    category: str | None
    amount: float
    count: int


class CashFlowMonth(BaseModel):
    """Income and spend for one month (YYYY-MM)."""

    month: str
    income: float
    spend: float


class SpendingOut(BaseModel):
    """Month spending breakdown plus six months of cash flow."""

    month: str
    by_category: list[CategorySpend]
    by_merchant: list[MerchantSpendOut]
    cash_flow: list[CashFlowMonth]


class BudgetOut(BaseModel):
    """A monthly category budget with this month's spend."""

    category: str
    limit: float
    spent: float


class GoalOut(BaseModel):
    """A savings goal with progress toward its target."""

    id: int
    name: str
    target_amount: float
    target_date: str | None
    current: float
    progress: float
    months_left: int | None


def _months_back(month: str, n: int) -> list[str]:
    """The n months ending at `month` (YYYY-MM), oldest first."""
    y, m = map(int, month.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def build_finance_router(db_path: Path, today: Callable[[], date]) -> APIRouter:
    """Routes for accounts, net worth and recurring charges."""
    router = APIRouter(prefix="/api")

    @router.get("/accounts", response_model=AccountsOut)
    def accounts() -> AccountsOut:
        """Linked accounts with cached balances, items, and asset/liability totals."""
        with closing(connect(db_path)) as conn:
            items = [
                ItemOut(**dict(r))
                for r in conn.execute(
                    "SELECT item_id, institution, status, last_synced_at "
                    "FROM items ORDER BY institution"
                )
            ]
            rows = conn.execute(
                "SELECT a.account_id, i.institution, a.name, a.type, a.subtype, a.mask, "
                "a.balance_current, a.balance_available FROM accounts a "
                "JOIN items i USING (item_id) ORDER BY i.institution, a.name"
            ).fetchall()
        accts = [AccountOut(**dict(r), is_liability=r["type"] in LIABILITY_TYPES) for r in rows]
        return AccountsOut(
            accounts=accts,
            items=items,
            assets=sum(a.balance_current or 0 for a in accts if not a.is_liability),
            liabilities=sum(a.balance_current or 0 for a in accts if a.is_liability),
        )

    @router.get("/networth", response_model=list[NetWorthPoint])
    def networth(days: int = Query(DEFAULT_NETWORTH_DAYS, ge=1, le=MAX_NETWORTH_DAYS)):
        """Daily net-worth snapshots for the last `days` days, oldest first."""
        cutoff = (today() - timedelta(days=days)).isoformat()
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT date, assets, liabilities FROM networth_snapshots "
                "WHERE date >= ? ORDER BY date",
                (cutoff,),
            ).fetchall()
        return [NetWorthPoint(**dict(r), net=r["assets"] - r["liabilities"]) for r in rows]

    @router.get("/recurring", response_model=RecurringListOut)
    def recurring() -> RecurringListOut:
        """Detected subscriptions and bills with monthly-normalized totals (inactive excluded)."""
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT stream_id, merchant, kind, frequency, avg_amount, last_amount, last_date, "
                "predicted_next_date, is_active FROM recurring_streams "
                "ORDER BY predicted_next_date"
            ).fetchall()
        streams = [
            RecurringOut(
                **{**dict(r), "is_active": bool(r["is_active"])},
                monthly_amount=monthly_amount(r["last_amount"], r["frequency"]),
            )
            for r in rows
        ]
        subs = [s for s in streams if s.kind == "subscription"]
        bills = [s for s in streams if s.kind == "bill"]
        return RecurringListOut(
            subscriptions=subs,
            bills=bills,
            subscriptions_monthly=sum(s.monthly_amount for s in subs if s.is_active),
            bills_monthly=sum(s.monthly_amount for s in bills if s.is_active),
        )

    @router.get("/spending", response_model=SpendingOut)
    def spending(month: str | None = None) -> SpendingOut:
        """Spend by category and top merchants for a month, plus 6 months of cash flow."""
        month = month or today().strftime("%Y-%m")
        if not MONTH_RE.match(month):
            raise HTTPException(status_code=422, detail="month must be YYYY-MM")
        months = _months_back(month, CASH_FLOW_MONTHS)
        with closing(connect(db_path)) as conn:
            cats = conn.execute(
                f"SELECT pfc_primary AS category, SUM(amount) AS amount FROM transactions "
                f"WHERE {_COUNTED} AND amount > 0 AND substr(date,1,7)=? "
                f"AND pfc_primary IS NOT NULL "
                f"GROUP BY pfc_primary ORDER BY amount DESC",
                (*_COUNTED_ARGS, month),
            ).fetchall()
            merchants = conn.execute(
                f"SELECT merchant, MAX(pfc_primary) AS category, SUM(amount) AS amount, "
                f"COUNT(*) AS count FROM transactions WHERE {_COUNTED} AND amount > 0 "
                f"AND substr(date,1,7)=? AND merchant IS NOT NULL GROUP BY merchant "
                f"ORDER BY amount DESC LIMIT ?",
                (*_COUNTED_ARGS, month, TOP_MERCHANTS),
            ).fetchall()
            flows = {
                r["month"]: r
                for r in conn.execute(
                    f"SELECT substr(date,1,7) AS month, "
                    f"SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS income, "
                    f"SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS spend FROM transactions "
                    f"WHERE {_COUNTED} AND substr(date,1,7) BETWEEN ? AND ? GROUP BY month",
                    (*_COUNTED_ARGS, months[0], months[-1]),
                ).fetchall()
            }
        return SpendingOut(
            month=month,
            by_category=[CategorySpend(**dict(r)) for r in cats],
            by_merchant=[MerchantSpendOut(**dict(r)) for r in merchants],
            cash_flow=[
                CashFlowMonth(
                    month=m,
                    income=flows[m]["income"] if m in flows else 0,
                    spend=flows[m]["spend"] if m in flows else 0,
                )
                for m in months
            ],
        )

    @router.get("/budgets", response_model=list[BudgetOut])
    def budgets() -> list[BudgetOut]:
        """Monthly budgets with this month's spend per category."""
        month = today().strftime("%Y-%m")
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                f"SELECT b.pfc_primary AS category, b.monthly_limit AS 'limit', "
                f"COALESCE((SELECT SUM(amount) FROM transactions t "
                f"WHERE t.pfc_primary=b.pfc_primary AND t.amount > 0 "
                f"AND substr(t.date,1,7)=? AND {_COUNTED}), 0) AS spent "
                f"FROM budgets b ORDER BY b.pfc_primary",
                (month, *_COUNTED_ARGS),
            ).fetchall()
        return [BudgetOut(**dict(r)) for r in rows]

    @router.get("/goals", response_model=list[GoalOut])
    def goals() -> list[GoalOut]:
        """Goals with current balance of linked accounts and months remaining."""
        now = today()
        with closing(connect(db_path)) as conn:
            balances = {
                r["account_id"]: r["balance_current"] or 0
                for r in conn.execute("SELECT account_id, balance_current FROM accounts")
            }
            rows = conn.execute(
                "SELECT id, name, target_amount, target_date, account_ids FROM goals ORDER BY id"
            ).fetchall()
        out = []
        for r in rows:
            current = sum(balances.get(a, 0) for a in json.loads(r["account_ids"]))
            months_left = None
            if r["target_date"]:
                t = date.fromisoformat(r["target_date"])
                months_left = max(0, (t.year - now.year) * 12 + t.month - now.month)
            progress = min(1.0, current / r["target_amount"]) if r["target_amount"] else 0.0
            out.append(
                GoalOut(
                    id=r["id"],
                    name=r["name"],
                    target_amount=r["target_amount"],
                    target_date=r["target_date"],
                    current=current,
                    progress=progress,
                    months_left=months_left,
                )
            )
        return out

    return router
