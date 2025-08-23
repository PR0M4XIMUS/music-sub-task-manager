import os
import csv
import io
import asyncio
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, FSInputFile
from aiogram.utils.markdown import hbold, hcode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from utils import pretty_money, parse_username_or_id, iso_to_date, next_billing_start, add_months_anchor, apply_advance_months
from scheduler import run_daily

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MONTHLY_AMOUNT = float(os.getenv("MONTHLY_AMOUNT", "2.50"))
BILLING_DAY = int(os.getenv("BILLING_DAY", "1"))            # 1..28 recommended
TZNAME = os.getenv("TIMEZONE", "Europe/Chisinau")
REMINDER_HOUR = int(os.getenv("REMINDER_HOUR", "10"))

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("BOT_TOKEN and ADMIN_ID must be set via environment variables.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ---------- Helpers ----------
def is_admin(user_id:int) -> bool:
    return user_id == ADMIN_ID

def user_label(u: types.User) -> str:
    tag = f"@{u.username}" if u.username else str(u.id)
    return f"{u.full_name} ({tag})"

async def ensure_member(msg: Message):
    u = msg.from_user
    await db.upsert_user(u.id, u.username or "", u.first_name or "", u.last_name or "")
    return await db.get_user(u.id)

# ---------- Commands ----------
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    await ensure_member(msg)
    text = (
        "👋 Welcome to the *Subscription Manager* bot!\n\n"
        f"Your monthly share is *{pretty_money(MONTHLY_AMOUNT)}*.\n"
        f"Billing day: *{BILLING_DAY}* of each month.\n\n"
        "Use:\n"
        "• /pay <amount> <months> — start a payment and then upload proof\n"
        "• Send a photo/document immediately after /pay to attach proof\n"
        "• /history — see your recent payments\n"
        "• /help — all commands\n"
    )
    await msg.answer(text, parse_mode="Markdown")

@dp.message(Command("help"))
async def cmd_help(msg: Message):
    admin_bits = ""
    if is_admin(msg.from_user.id):
        admin_bits = (
            "\n*Admin:*\n"
            "• /status — who’s paid & next due dates\n"
            "• /setmute <@user|id> <months> — mute reminders for advance payments\n"
            "• /setamount <value> — set monthly amount\n"
            "• /setday <1-28> — set billing day\n"
            "• /proof <@user|id> — fetch latest proof\n"
            "• /addmember <@user|id> — add/track a member explicitly\n"
            "• /remove <@user|id> — remove a member & their data\n"
            "• /export — CSV export of all payments\n"
        )
    await msg.answer(
        "*Commands:*\n"
        "• /start — register / info\n"
        "• /pay <amount> <months> — begin payment (then upload proof)\n"
        "• /history — your last 20 payments\n"
        + admin_bits, parse_mode="Markdown"
    )

@dp.message(Command("pay"))
async def cmd_pay(msg: Message, command: CommandObject):
    await ensure_member(msg)

    if not command.args:
        return await msg.reply("Usage: `/pay <amount> <months>`\nExample: `/pay 2.50 1`",
                               parse_mode="Markdown")

    parts = command.args.split()
    if len(parts) != 2:
        return await msg.reply("Please provide exactly two values: amount and months. Example: `/pay 2.50 1`",
                               parse_mode="Markdown")

    try:
        amount = float(parts[0])
        months = int(parts[1])
    except:
        return await msg.reply("Could not parse values. Example: `/pay 2.50 1`", parse_mode="Markdown")

    if months <= 0 or amount <= 0:
        return await msg.reply("Amount and months must be positive numbers.")

    await db.set_pending(msg.from_user.id, amount, months)
    await msg.answer(
        f"Got it! Expected: *{pretty_money(amount)}* for *{months}* month(s).\n"
        "Now please upload your payment proof (photo or document) in your next message.",
        parse_mode="Markdown"
    )

@dp.message(F.photo | F.document)
async def handle_proof(msg: Message):
    user = await ensure_member(msg)
    pending = await db.get_pending(msg.from_user.id)
    if not pending:
        return await msg.reply("Please start with `/pay <amount> <months>` before sending proof.", parse_mode="Markdown")

    proof_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    paid_at_iso = datetime.utcnow().isoformat()
    await db.add_payment(user_id=msg.from_user.id,
                         amount=float(pending["amount"]),
                         months=int(pending["months"]),
                         proof_file_id=proof_id,
                         paid_at_iso=paid_at_iso)
    await db.clear_pending(msg.from_user.id)

    # Notify user & admin
    await msg.answer("✅ Payment recorded. Thank you!")
    try:
        await bot.send_message(ADMIN_ID, f"💰 Payment: {user['username'] or msg.from_user.full_name} — {pretty_money(float(pending['amount']))} for {pending['months']} month(s).")
    except:
        pass

@dp.message(Command("history"))
async def cmd_history(msg: Message):
    await ensure_member(msg)
    payments = await db.list_payments(msg.from_user.id, limit=20)
    if not payments:
        return await msg.answer("No payments yet.")
    lines = []
    for p in payments:
        t = iso_to_date(p["paid_at"])
        lines.append(f"• {t.isoformat()}: {pretty_money(p['amount'])} for {p['months']} mo")
    await msg.answer("\n".join(lines))

# ---------- Admin ----------
@dp.message(Command("status"))
async def cmd_status(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    users = await db.all_users()
    if not users:
        return await msg.answer("No users registered yet.")

    # build a concise status
    tz = ZoneInfo(TZNAME)
    today = datetime.now(tz).date()

    lines = ["*Status:*"]
    for u in users:
        payments = await db.list_payments(u["user_id"], limit=1000)
        if payments:
            payments_sorted = sorted(payments, key=lambda p: p["paid_at"])
            from utils import compute_coverage_until
            last_cov = iso_to_date(payments_sorted[0]["paid_at"])
            last_cov = last_cov.replace(day=1)
            for p in payments_sorted:
                last_cov = compute_coverage_until(iso_to_date(p["paid_at"]), int(p["months"]), BILLING_DAY)
            due = next_billing_start(last_cov, BILLING_DAY)
            status = f"covered through {last_cov.isoformat()}, next due {due.isoformat()}"
        else:
            # due on nearest anchor
            anchor = date(today.year, today.month, 1).replace(day=min(BILLING_DAY, 28))
            status = f"no payments yet, next due {anchor.isoformat()}"

        mute = f", muted until {u['muted_until']}" if u["muted_until"] else ""
        uname = f"@{u['username']}" if u["username"] else str(u["user_id"])
        lines.append(f"• {uname}: {status}{mute}")

    await msg.answer("\n".join(lines), parse_mode="Markdown")

@dp.message(Command("setmute"))
async def cmd_setmute(msg: Message, command: CommandObject):
    if not is_admin(msg.from_user.id):
        return
    if not command.args:
        return await msg.reply("Usage: `/setmute <@user|id> <months>`", parse_mode="Markdown")
    parts = command.args.split()
    if len(parts) != 2:
        return await msg.reply("Usage: `/setmute <@user|id> <months>`", parse_mode="Markdown")

    target, months_str = parts
    months = int(months_str)
    if months <= 0:
        return await msg.reply("Months must be positive.")
    # resolve user
    uid = parse_username_or_id(target)
    row = None
    if uid:
        row = await db.get_user(uid)
    else:
        row = await db.get_user_by_username(target)
    if not row:
        return await msg.reply("User not found in database. Ask them to /start the bot once.")

    tz = ZoneInfo(TZNAME)
    today = datetime.now(tz).date()
    until = today + relativedelta(months=+months)  # type: ignore
    # Reminders are muted until 'until' (exclusive)
    await db.set_muted_until(row["user_id"], until.isoformat())
    await msg.answer(f"🔕 Muted {target} until {until.isoformat()}.")

@dp.message(Command("setamount"))
async def cmd_setamount(msg: Message, command: CommandObject):
    if not is_admin(msg.from_user.id):
        return
    if not command.args:
        return await msg.reply("Usage: `/setamount <value>`", parse_mode="Markdown")
    try:
        value = float(command.args.strip())
    except:
        return await msg.reply("Please provide a valid number.")
    global MONTHLY_AMOUNT
    MONTHLY_AMOUNT = value
    await msg.answer(f"Monthly amount set to {pretty_money(MONTHLY_AMOUNT)}.")

@dp.message(Command("setday"))
async def cmd_setday(msg: Message, command: CommandObject):
    if not is_admin(msg.from_user.id):
        return
    if not command.args:
        return await msg.reply("Usage: `/setday <1-28>`", parse_mode="Markdown")
    try:
        day = int(command.args.strip())
        if not (1 <= day <= 28):
            raise ValueError()
    except:
        return await msg.reply("Day must be an integer between 1 and 28.")
    global BILLING_DAY
    BILLING_DAY = day
    await msg.answer(f"Billing day set to {BILLING_DAY}.")

@dp.message(Command("proof"))
async def cmd_proof(msg: Message, command: CommandObject):
    if not is_admin(msg.from_user.id):
        return
    if not command.args:
        return await msg.reply("Usage: `/proof <@user|id>`", parse_mode="Markdown")
    target = command.args.strip()
    uid = parse_username_or_id(target)
    row = None
    if uid:
        row = await db.get_user(uid)
    else:
        row = await db.get_user_by_username(target)
    if not row:
        return await msg.reply("User not found.")

    p = await db.latest_payment(row["user_id"])
    if not p:
        return await msg.reply("No payments found for that user.")
    # try sending as photo first; fall back to document
    try:
        await bot.send_photo(chat_id=msg.chat.id, photo=p["proof_file_id"], caption=f"{target} — {pretty_money(p['amount'])} for {p['months']} mo on {iso_to_date(p['paid_at']).isoformat()}")
    except:
        await bot.send_document(chat_id=msg.chat.id, document=p["proof_file_id"], caption=f"{target} — {pretty_money(p['amount'])} for {p['months']} mo on {iso_to_date(p['paid_at']).isoformat()}")

@dp.message(Command("addmember"))
async def cmd_addmember(msg: Message, command: CommandObject):
    if not is_admin(msg.from_user.id):
        return
    if not command.args:
        return await msg.reply("Usage: `/addmember <@user|id>`", parse_mode="Markdown")
    target = command.args.strip()
    uid = parse_username_or_id(target)
    if uid:
        await db.upsert_user(uid, "", "", "")
        return await msg.answer(f"Added user id {uid}. They should /start the bot to complete profile.")
    # username
    row = await db.get_user_by_username(target)
    if row:
        return await msg.answer("User already exists.")
    await msg.answer("I can only add by numeric id unless the user has already messaged the bot. Ask them to send /start once.")

@dp.message(Command("remove"))
async def cmd_remove(msg: Message, command: CommandObject):
    if not is_admin(msg.from_user.id):
        return
    if not command.args:
        return await msg.reply("Usage: `/remove <@user|id>`", parse_mode="Markdown")
    target = command.args.strip()
    uid = parse_username_or_id(target)
    if not uid:
        row = await db.get_user_by_username(target)
        if not row:
            return await msg.reply("User not found.")
        uid = row["user_id"]
    count = await db.remove_user(uid)
    await msg.answer(f"Removed user {target} and their payments.")

@dp.message(Command("export"))
async def cmd_export(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    rows = await db.export_all_payments()
    if not rows:
        return await msg.answer("No payments to export.")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","user_id","username","first_name","last_name","amount","months","proof_file_id","paid_at"])
    writer.writerows(rows)
    output.seek(0)
    data = io.BytesIO(output.getvalue().encode("utf-8"))
    data.name = "payments.csv"
    await bot.send_document(chat_id=msg.chat.id, document=data, caption="All payments export")

# ---------- Reminders ----------
async def send_reminder_to_user(user_id:int):
    try:
        await bot.send_message(user_id, f"⏰ Reminder: please pay your Apple Music share of {pretty_money(MONTHLY_AMOUNT)}. Use /pay {pretty_money(MONTHLY_AMOUNT)} 1 and upload your proof.")
    except Exception as e:
        print(f"[reminder] failed to message {user_id}: {e}")

async def schedule_jobs():
    tz = ZoneInfo(TZNAME)
    # Daily at REMINDER_HOUR local time
    scheduler.add_job(
        lambda: asyncio.create_task(run_daily(send_reminder_to_user, BILLING_DAY, TZNAME)),
        CronTrigger(hour=REMINDER_HOUR, minute=0, timezone=tz),
        name="daily-reminders"
    )
    scheduler.start()
    print(f"[scheduler] Reminders scheduled at {REMINDER_HOUR}:00 {TZNAME} daily.")

# ---------- Startup ----------
async def main():
    await db.init_db()
    await schedule_jobs()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
