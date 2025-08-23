import asyncio
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Callable, Awaitable, List
from database import all_users, list_payments
from utils import next_billing_start, iso_to_date

async def users_due(billing_day:int, tz:ZoneInfo) -> List[int]:
    """Return list of user_ids who should get a reminder today."""
    today_local = datetime.now(tz).date()
    result = []
    users = await all_users()
    for u in users:
        muted_until = None
        if u["muted_until"]:
            muted_until = iso_to_date(u["muted_until"])
            if today_local < muted_until:
                continue  # still muted

        # Determine last covered date from payments
        payments = await list_payments(u["user_id"], limit=1000)
        if not payments:
            # New user: first due is the nearest billing anchor >= today
            due = date(today_local.year, today_local.month, 1)
            day = min(billing_day, (date(due.year, (due.month % 12)+1, 1) - date(due.year, due.month, 1)).days)
            due = due.replace(day=day)
            if today_local >= due:
                result.append(u["user_id"])
            continue

        # Compute coverage: sort by paid_at ascending and roll forward
        payments_sorted = sorted(payments, key=lambda p: p["paid_at"])
        # Start with the date they first paid
        last_covered = iso_to_date(payments_sorted[0]["paid_at"])
        last_covered = last_covered.replace(day=1)  # baseline; will be advanced by months
        # Fold payments in chronological order
        from utils import compute_coverage_until  # late import to avoid cycle
        for p in payments_sorted:
            paid_on = iso_to_date(p["paid_at"])
            last_covered = compute_coverage_until(paid_on, int(p["months"]), billing_day)
        # Next due is next billing anchor AFTER coverage-through
        due = next_billing_start(last_covered, billing_day)
        if today_local >= due:
            result.append(u["user_id"])
    return result

async def run_daily(remind_fn: Callable[[int], Awaitable[None]], billing_day:int, tzname:str):
    tz = ZoneInfo(tzname)
    due_ids = await users_due(billing_day, tz)
    for uid in due_ids:
        try:
            await remind_fn(uid)
        except Exception as e:
            # log to stdout; container will capture logs
            print(f"[reminder] failed to send to {uid}: {e}")
