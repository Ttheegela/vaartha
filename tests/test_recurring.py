"""Recurring detection: cadence, kind, next date, inactivity, edge dates."""

from datetime import date, timedelta

import polars as pl

from core.recurring import STREAM_COLUMNS, detect_recurring

TODAY = date(2026, 10, 12)


def _df(rows):
    return pl.DataFrame(
        rows,
        schema={"account_id": pl.Utf8, "date": pl.Date, "amount": pl.Float64, "merchant": pl.Utf8,
                "pfc_primary": pl.Utf8, "pfc_detailed": pl.Utf8},
        orient="row",
    )


def _monthly(merchant, days, amount=10.0, primary="ENTERTAINMENT", detailed="ENTERTAINMENT_X"):
    return [("a1", d, amount, merchant, primary, detailed) for d in days]


def _one(out, merchant):
    rows = out.filter(pl.col("merchant") == merchant).to_dicts()
    assert len(rows) == 1, out
    return rows[0]


def test_monthly_subscription_detected():
    days = [date(2026, m, 15) for m in (6, 7, 8, 9)]
    s = _one(detect_recurring(_df(_monthly("Netflix", days)), TODAY), "Netflix")
    assert s["frequency"] == "MONTHLY"
    assert s["kind"] == "subscription"
    assert s["predicted_next_date"] == date(2026, 10, 15)
    assert s["is_active"] is True
    assert list(detect_recurring(_df(_monthly("Netflix", days)), TODAY).columns) == STREAM_COLUMNS


def test_rent_utilities_insurance_are_bills():
    days = [date(2026, m, 1) for m in (7, 8, 9, 10)]
    rows = (_monthly("Rent", days, 2450, "RENT_AND_UTILITIES", "RENT_AND_UTILITIES_RENT")
            + _monthly("Geico", days, 142.5, "GENERAL_SERVICES", "GENERAL_SERVICES_INSURANCE"))
    out = detect_recurring(_df(rows), TODAY)
    assert _one(out, "Rent")["kind"] == "bill"
    assert _one(out, "Geico")["kind"] == "bill"


def test_irregular_purchases_not_recurring():
    d, rows = date(2026, 5, 1), []
    for gap in (3, 8, 5, 11, 4, 9, 6, 13, 2, 10):
        d += timedelta(days=gap)
        rows.append(("a1", d, 50.0, "Whole Foods", "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES"))
    assert detect_recurring(_df(rows), TODAY).height == 0


def test_two_monthly_charges_not_enough():
    days = [date(2026, 8, 15), date(2026, 9, 15)]
    assert detect_recurring(_df(_monthly("New", days)), TODAY).height == 0


def test_annual_needs_two():
    rows = _monthly("Amazon Prime", [date(2025, 10, 2), date(2026, 10, 2)], 139.0)
    s = _one(detect_recurring(_df(rows), TODAY), "Amazon Prime")
    assert s["frequency"] == "ANNUALLY"
    assert s["predicted_next_date"] == date(2027, 10, 2)


def test_weekly_detected():
    days = [TODAY - timedelta(days=7 * k) for k in range(4, 0, -1)]
    s = _one(detect_recurring(_df(_monthly("Dog walker", days, 30.0)), TODAY), "Dog walker")
    assert s["frequency"] == "WEEKLY"


def test_stopped_subscription_inactive():
    days = [date(2026, m, 5) for m in (3, 4, 5, 6)]
    s = _one(detect_recurring(_df(_monthly("The Atlantic", days, 7.99)), TODAY), "The Atlantic")
    assert s["is_active"] is False


def test_month_end_clamps():
    days = [date(2026, 5, 31), date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31)]
    s = _one(detect_recurring(_df(_monthly("Gym", days)), date(2026, 9, 10)), "Gym")
    assert s["frequency"] == "MONTHLY"
    assert s["predicted_next_date"] == date(2026, 9, 30)


def test_leap_day_annual():
    rows = _monthly("Domain", [date(2023, 2, 28), date(2024, 2, 29)], 12.0)
    s = _one(detect_recurring(_df(rows), date(2024, 6, 1)), "Domain")
    assert s["predicted_next_date"] == date(2025, 2, 28)


def test_price_change_tracked_and_inflows_ignored():
    days = [date(2026, m, 15) for m in (6, 7, 8, 9)]
    prices = (20.99, 20.99, 20.99, 22.99)
    rows = [("a1", d, a, "Netflix", "ENTERTAINMENT", "X")
            for d, a in zip(days, prices, strict=True)]
    rows += [("a1", date(2026, m, 1), -4120.0, "Payroll", "INCOME", "INCOME_WAGES")
             for m in (6, 7, 8, 9)]
    out = detect_recurring(_df(rows), TODAY)
    s = _one(out, "Netflix")
    assert s["last_amount"] == 22.99
    assert s["avg_amount"] == round((20.99 * 3 + 22.99) / 4, 2)
    assert out.filter(pl.col("merchant") == "Payroll").height == 0


def test_empty_input():
    out = detect_recurring(_df([]), TODAY)
    assert out.height == 0 and list(out.columns) == STREAM_COLUMNS


def test_same_day_duplicate_does_not_hide_monthly():
    days = [date(2026, m, 15) for m in (6, 7, 8, 9)] + [date(2026, 9, 15)]
    s = _one(detect_recurring(_df(_monthly("Netflix", days)), TODAY), "Netflix")
    assert s["frequency"] == "MONTHLY"


def test_old_irregular_gap_ignored_when_recent_charges_regular():
    days = [date(2025, 1, 3), date(2025, 2, 20)] + [date(2026, m, 15) for m in range(4, 10)]
    s = _one(detect_recurring(_df(_monthly("Hulu", days)), TODAY), "Hulu")
    assert s["frequency"] == "MONTHLY"


MONTHLY_DAYS = [date(2026, m, 15) for m in (6, 7, 8, 9)]


def test_own_account_transfer_not_recurring():
    rows = _monthly("ACH Electronic CreditGUSTO PAY", MONTHLY_DAYS, 500.0,
                    "TRANSFER_OUT", "TRANSFER_OUT_ACCOUNT_TRANSFER")
    assert detect_recurring(_df(rows), TODAY).height == 0


def test_credit_card_payment_not_recurring():
    rows = _monthly("CREDIT CARD 3333 PAYMENT", MONTHLY_DAYS, 800.0,
                    "LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
    assert detect_recurring(_df(rows), TODAY).height == 0


def test_auto_loan_payment_is_bill():
    rows = _monthly("Auto Loan", MONTHLY_DAYS, 350.0, "LOAN_PAYMENTS",
                    "LOAN_PAYMENTS_OTHER_PAYMENT")
    assert _one(detect_recurring(_df(rows), TODAY), "Auto Loan")["kind"] == "bill"


def test_null_categories_still_detected():
    rows = _monthly("Mystery Sub", MONTHLY_DAYS, 9.99, None, None)
    s = _one(detect_recurring(_df(rows), TODAY), "Mystery Sub")
    assert s["frequency"] == "MONTHLY"
    assert s["kind"] == "subscription"
