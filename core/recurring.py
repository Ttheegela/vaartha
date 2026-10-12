"""Detect recurring outflows (subscriptions and bills) from transactions.

Our own detector, because Plaid's recurring add-on is not on the Trial plan.
A stream = same account + normalized merchant, charged on a regular cadence.
"""

import calendar
import hashlib
import statistics
from datetime import date, timedelta

import polars as pl

STREAM_SCHEMA = {
    "stream_id": pl.Utf8, "account_id": pl.Utf8, "direction": pl.Utf8, "kind": pl.Utf8,
    "merchant": pl.Utf8, "avg_amount": pl.Float64, "last_amount": pl.Float64,
    "frequency": pl.Utf8, "last_date": pl.Date, "predicted_next_date": pl.Date,
    "status": pl.Utf8, "is_active": pl.Boolean,
}
STREAM_COLUMNS = list(STREAM_SCHEMA)
WEEK_DAYS = 7
WEEKLY_TOLERANCE_DAYS = 3
MONTHLY_TOLERANCE_DAYS = 3
ANNUAL_DAYS = 365
ANNUAL_TOLERANCE_DAYS = 10
MIN_WEEKLY = MIN_MONTHLY = 3
MIN_ANNUAL = 2
TOLERANCE = {"WEEKLY": WEEKLY_TOLERANCE_DAYS, "MONTHLY": MONTHLY_TOLERANCE_DAYS,
             "ANNUALLY": ANNUAL_TOLERANCE_DAYS}
CADENCE_WINDOW = 6  # cadence and avg_amount use only the most recent distinct-day charges
ANCHOR_WINDOW = 3  # day-of-month anchor = max day among the last 3 charges (month-end safe)
BILL_PRIMARY = {"RENT_AND_UTILITIES", "LOAN_PAYMENTS"}
BILL_DETAILED_PREFIX = "GENERAL_SERVICES_INSURANCE"
STREAM_ID_LENGTH = 16
AMOUNT_DECIMALS = 2


def _add_months(first_of_month: date, months: int) -> date:
    y, m = divmod(first_of_month.month - 1 + months, 12)
    return date(first_of_month.year + y, m + 1, 1)


def _next_date(last: date, frequency: str, anchor_day: int) -> date:
    """Next expected charge: +7 days, or +1/+12 months on anchor_day clamped to month length."""
    if frequency == "WEEKLY":
        return last + timedelta(days=WEEK_DAYS)
    target = _add_months(last.replace(day=1), 1 if frequency == "MONTHLY" else 12)
    return target.replace(day=min(anchor_day, calendar.monthrange(target.year, target.month)[1]))


def _cadence(dates: list[date]) -> str | None:
    pairs = list(zip(dates, dates[1:], strict=False))
    if not pairs:
        return None
    gaps = [(b - a).days for a, b in pairs]
    if len(dates) >= MIN_WEEKLY and all(abs(g - WEEK_DAYS) <= WEEKLY_TOLERANCE_DAYS for g in gaps):
        return "WEEKLY"
    anchor = max(d.day for d in dates)
    if len(dates) >= MIN_MONTHLY and all(
        (b.year - a.year) * 12 + b.month - a.month == 1
        and abs((b - _next_date(a, "MONTHLY", anchor)).days) <= MONTHLY_TOLERANCE_DAYS
        for a, b in pairs
    ):
        return "MONTHLY"
    if len(dates) >= MIN_ANNUAL and all(
        abs(g - ANNUAL_DAYS) <= ANNUAL_TOLERANCE_DAYS for g in gaps
    ):
        return "ANNUALLY"
    return None


def _kind(primary: str | None, detailed: str | None) -> str:
    if primary in BILL_PRIMARY or (detailed or "").startswith(BILL_DETAILED_PREFIX):
        return "bill"
    return "subscription"


def detect_recurring(txns: pl.DataFrame, today: date) -> pl.DataFrame:
    """Return one row per detected outflow stream (columns: STREAM_COLUMNS)."""
    rows = []
    outflows = txns.filter((pl.col("amount") > 0) & pl.col("merchant").is_not_null())
    if outflows.height:
        grouped = (
            outflows.with_columns(pl.col("merchant").str.strip_chars().str.to_lowercase().alias("key"))
            .sort("date")
            .group_by("account_id", "key", maintain_order=True)
            .agg(pl.col("date"), pl.col("amount"), pl.col("merchant").last(),
                 pl.col("pfc_primary").last(), pl.col("pfc_detailed").last())
        )
        for g in grouped.iter_rows(named=True):
            # one charge per day (last wins); input is date-sorted
            per_day = dict(zip(g["date"], g["amount"], strict=True))
            dates = list(per_day)[-CADENCE_WINDOW:]
            amounts = [per_day[d] for d in dates]
            frequency = _cadence(dates)
            if frequency is None:
                continue
            anchor = (dates[-1].day if frequency == "ANNUALLY"
                      else max(d.day for d in dates[-ANCHOR_WINDOW:]))
            nxt = _next_date(dates[-1], frequency, anchor)
            digest = hashlib.sha1(f"{g['account_id']}|{g['key']}".encode()).hexdigest()
            sid = digest[:STREAM_ID_LENGTH]
            rows.append({
                "stream_id": sid, "account_id": g["account_id"], "direction": "outflow",
                "kind": _kind(g["pfc_primary"], g["pfc_detailed"]), "merchant": g["merchant"],
                "avg_amount": round(statistics.fmean(amounts), AMOUNT_DECIMALS),
                "last_amount": amounts[-1], "frequency": frequency, "last_date": dates[-1],
                "predicted_next_date": nxt, "status": "MATURE",
                "is_active": today <= nxt + timedelta(days=TOLERANCE[frequency]),
            })
    return pl.DataFrame(rows, schema=STREAM_SCHEMA)
