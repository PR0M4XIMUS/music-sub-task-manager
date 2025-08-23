from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional, Tuple
import math

def next_billing_start(last_covered_until: date, billing_day:int) -> date:
    """
    Given that coverage is valid THROUGH last_covered_until (inclusive),
    return the next due date (billing cycle anchor) based on billing_day.
    """
    # Next cycle anchor on billing_day after last_covered_until
    candidate = date(last_covered_until.year, last_covered_until.month, 1)
    # Move to next month if we're past or on billing day in this month
    # Determine current month's billing anchor
    curr_anchor = candidate.replace(day=min(billing_day, days_in_month(candidate.year, candidate.month)))
    if last_covered_until < curr_anchor:
        return curr_anchor
    # else move forwards month-by-month until after last_covered_until
    d = curr_anchor
    while d <= last_covered_until:
        d = add_months_anchor(d, 1, billing_day)
    return d

def add_months_anchor(anchor_date: date, months:int, billing_day:int) -> date:
    target = anchor_date + relativedelta(months=+months)
    # clamp day to last day of month if billing_day > month length
    return target.replace(day=min(billing_day, days_in_month(target.year, target.month)))

def days_in_month(y:int, m:int) -> int:
    if m==12:
        nxt = date(y+1,1,1)
    else:
        nxt = date(y,m+1,1)
    return (nxt - date(y,m,1)).days

def apply_advance_months(start_anchor: date, months:int, billing_day:int) -> date:
    """Return coverage-through date after adding months to start_anchor (each month covers until the day before next anchor)."""
    end_anchor = add_months_anchor(start_anchor, months, billing_day)
    # Coverage lasts until the day BEFORE the end anchor
    return end_anchor - timedelta(days=1)

def compute_coverage_until(last_payment_date: date, months:int, billing_day:int) -> date:
    """Coverage from payment applies starting at the next billing anchor on/after payment date."""
    first_anchor = date(last_payment_date.year, last_payment_date.month, 1)
    first_anchor = first_anchor.replace(day=min(billing_day, days_in_month(first_anchor.year, first_anchor.month)))
    if last_payment_date < first_anchor:
        start = first_anchor
    else:
        # start at next anchor if paying after billing day
        start = add_months_anchor(first_anchor, 1, billing_day)
    return apply_advance_months(start, months, billing_day)

def pretty_money(amount: float) -> str:
    # Keep 2 decimals max without trailing zeros excess
    return f"{amount:.2f}".rstrip("0").rstrip(".")

def parse_username_or_id(s: str) -> Optional[int]:
    # Admin might pass a numeric user id
    try:
        return int(s)
    except:
        return None

def iso_to_date(iso_str: str) -> date:
    return datetime.fromisoformat(iso_str).date()
