import os
import csv
import io
import asyncio
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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

def create_main_menu() -> InlineKeyboardMarkup:
    """Create main menu keyboard for regular users"""
    buttons = [
        [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
        [InlineKeyboardButton(text="📊 Payment History", callback_data="history")],
        [InlineKeyboardButton(text="❓ Help & Commands", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_admin_menu() -> InlineKeyboardMarkup:
    """Create admin menu keyboard"""
    buttons = [
        [InlineKeyboardButton(text="📊 User Status", callback_data="status")],
        [InlineKeyboardButton(text="🔧 Settings", callback_data="admin_settings")],
        [InlineKeyboardButton(text="👥 Manage Users", callback_data="user_management")],
        [InlineKeyboardButton(text="📥 Export Data", callback_data="export")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_payment_menu() -> InlineKeyboardMarkup:
    """Create quick payment options"""
    buttons = [
        [InlineKeyboardButton(text=f"💰 Pay {pretty_money(MONTHLY_AMOUNT)} (1 month)", callback_data=f"pay_{MONTHLY_AMOUNT}_1")],
        [InlineKeyboardButton(text=f"💰 Pay {pretty_money(MONTHLY_AMOUNT * 3)} (3 months)", callback_data=f"pay_{MONTHLY_AMOUNT * 3}_3")],
        [InlineKeyboardButton(text=f"💰 Pay {pretty_money(MONTHLY_AMOUNT * 6)} (6 months)", callback_data=f"pay_{MONTHLY_AMOUNT * 6}_6")],
        [InlineKeyboardButton(text="💳 Custom Amount", callback_data="pay_custom")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_help_menu() -> InlineKeyboardMarkup:
    """Create help menu with command shortcuts"""
    buttons = [
        [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
        [InlineKeyboardButton(text="📊 My History", callback_data="history")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_admin_settings_menu() -> InlineKeyboardMarkup:
    """Create admin settings menu"""
    buttons = [
        [InlineKeyboardButton(text="💰 Set Amount", callback_data="set_amount")],
        [InlineKeyboardButton(text="📅 Set Billing Day", callback_data="set_day")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_user_management_menu() -> InlineKeyboardMarkup:
    """Create user management menu"""
    buttons = [
        [InlineKeyboardButton(text="👤 Add Member", callback_data="add_member")],
        [InlineKeyboardButton(text="🔇 Mute User", callback_data="mute_user")],
        [InlineKeyboardButton(text="🗑️ Remove User", callback_data="remove_user")],
        [InlineKeyboardButton(text="🔍 Get Proof", callback_data="get_proof")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Commands ----------
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    await ensure_member(msg)
    
    # Check if user is admin for different menu
    if is_admin(msg.from_user.id):
        text = (
            "🎵 *Welcome to the Subscription Manager Bot!* 🎵\n\n"
            "👋 Hello Admin! You have full access to manage the subscription system.\n\n"
            f"💰 Current monthly share: *{pretty_money(MONTHLY_AMOUNT)}*\n"
            f"📅 Billing day: *{BILLING_DAY}* of each month\n\n"
            "🔧 Choose an option below to get started:"
        )
        keyboard = create_admin_menu()
    else:
        text = (
            "🎵 *Welcome to the Subscription Manager Bot!* 🎵\n\n"
            "👋 Hello! This bot helps you manage your Apple Music subscription payments.\n\n"
            f"💰 Your monthly share: *{pretty_money(MONTHLY_AMOUNT)}*\n"
            f"📅 Billing day: *{BILLING_DAY}* of each month\n\n"
            "📱 Choose an option below to get started:"
        )
        keyboard = create_main_menu()
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.message(Command("help"))
async def cmd_help(msg: Message):
    admin_commands = ""
    if is_admin(msg.from_user.id):
        admin_commands = (
            "\n*🔧 Admin Commands:*\n"
            "• /status — 📊 View who's paid & next due dates\n"
            "• /setmute <@user|id> <months> — 🔇 Mute reminders\n"
            "• /setamount <value> — 💰 Set monthly amount\n"
            "• /setday <1-28> — 📅 Set billing day\n"
            "• /proof <@user|id> — 🔍 Fetch latest proof\n"
            "• /addmember <@user|id> — 👤 Add/track a member\n"
            "• /remove <@user|id> — 🗑️ Remove member & data\n"
            "• /export — 📥 CSV export of all payments\n"
        )
    
    text = (
        "❓ *Help & Available Commands* ❓\n\n"
        "*📱 User Commands:*\n"
        "• /start — 🏠 Register & show main menu\n"
        "• /pay <amount> <months> — 💳 Begin payment process\n"
        "• /history — 📊 View your last 20 payments\n"
        "• /help — ❓ Show this help message\n"
        + admin_commands +
        "\n💡 *Tips:*\n"
        "• Use the buttons below for quick actions\n"
        "• After /pay, upload your payment proof immediately\n"
        "• Contact admin if you have any issues\n"
    )
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=create_help_menu())

@dp.message(Command("pay"))
async def cmd_pay(msg: Message, command: CommandObject):
    await ensure_member(msg)

    if not command.args:
        text = (
            "💳 *Make a Payment* 💳\n\n"
            "Usage: `/pay <amount> <months>`\n"
            f"Example: `/pay {pretty_money(MONTHLY_AMOUNT)} 1`\n\n"
            "Or use quick payment buttons:"
        )
        return await msg.reply(text, parse_mode="Markdown", reply_markup=create_payment_menu())

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
    
    # Create a success message with helpful buttons
    text = (
        "✅ *Payment Started* ✅\n\n"
        f"Amount: *{pretty_money(amount)}*\n"
        f"Months: *{months}*\n\n"
        "📎 Now please upload your payment proof (photo or document) in your next message."
    )
    
    # Add quick action buttons
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 View History", callback_data="history")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ])
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)

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

    # Notify user with enhanced message and buttons
    text = (
        "🎉 *Payment Recorded Successfully!* 🎉\n\n"
        f"Amount: *{pretty_money(float(pending['amount']))}*\n"
        f"Months: *{pending['months']}*\n"
        f"Date: *{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC*\n\n"
        "Thank you for your payment! 💚"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 View History", callback_data="history")],
        [InlineKeyboardButton(text="💳 Make Another Payment", callback_data="pay_menu")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ])
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)
    
    # Notify admin with emoji
    try:
        admin_text = f"💰 *New Payment Received*\n\n👤 User: {user['username'] or msg.from_user.full_name}\n💵 Amount: {pretty_money(float(pending['amount']))}\n📅 Months: {pending['months']}"
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
    except:
        pass

@dp.message(Command("history"))
async def cmd_history(msg: Message):
    await ensure_member(msg)
    payments = await db.list_payments(msg.from_user.id, limit=20)
    if not payments:
        text = (
            "📊 *Payment History* 📊\n\n"
            "No payments found yet.\n\n"
            "💡 Ready to make your first payment?"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
        ])
        return await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)
    
    lines = ["📊 *Payment History* 📊\n"]
    total_amount = 0
    total_months = 0
    
    for p in payments:
        t = iso_to_date(p["paid_at"])
        lines.append(f"• {t.isoformat()}: {pretty_money(p['amount'])} for {p['months']} mo")
        total_amount += p['amount']
        total_months += p['months']
    
    # Add summary
    lines.append(f"\n📈 *Summary:*")
    lines.append(f"Total paid: *{pretty_money(total_amount)}*")
    lines.append(f"Total months: *{total_months}*")
    
    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ])
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)

# ---------- Callback Handlers ----------
@dp.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    if is_admin(user_id):
        text = (
            "🎵 *Welcome to the Subscription Manager Bot!* 🎵\n\n"
            "👋 Hello Admin! You have full access to manage the subscription system.\n\n"
            f"💰 Current monthly share: *{pretty_money(MONTHLY_AMOUNT)}*\n"
            f"📅 Billing day: *{BILLING_DAY}* of each month\n\n"
            "🔧 Choose an option below to get started:"
        )
        keyboard = create_admin_menu()
    else:
        text = (
            "🎵 *Welcome to the Subscription Manager Bot!* 🎵\n\n"
            "👋 Hello! This bot helps you manage your Apple Music subscription payments.\n\n"
            f"💰 Your monthly share: *{pretty_money(MONTHLY_AMOUNT)}*\n"
            f"📅 Billing day: *{BILLING_DAY}* of each month\n\n"
            "📱 Choose an option below to get started:"
        )
        keyboard = create_main_menu()
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "pay_menu")
async def callback_pay_menu(callback: CallbackQuery):
    text = (
        "💳 *Payment Options* 💳\n\n"
        "Choose how much you want to pay:\n\n"
        f"Monthly amount: *{pretty_money(MONTHLY_AMOUNT)}*\n"
        "Select a quick option or use custom amount:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=create_payment_menu())
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_"))
async def callback_pay_amount(callback: CallbackQuery):
    data = callback.data
    if data == "pay_custom":
        text = (
            "💳 *Custom Payment* 💳\n\n"
            "Please use the command format:\n"
            "`/pay <amount> <months>`\n\n"
            "Examples:\n"
            f"• `/pay {pretty_money(MONTHLY_AMOUNT)} 1` - one month\n"
            f"• `/pay {pretty_money(MONTHLY_AMOUNT * 2)} 2` - two months\n"
            "• `/pay 10.50 4` - custom amount for 4 months"
        )
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=create_payment_menu())
    else:
        # Extract amount and months from callback data like "pay_2.50_1"
        parts = data.split("_")
        if len(parts) == 3:
            amount = float(parts[1])
            months = int(parts[2])
            user_id = callback.from_user.id
            
            # Set pending payment
            await db.set_pending(user_id, amount, months)
            
            text = (
                "✅ *Payment Started* ✅\n\n"
                f"Amount: *{pretty_money(amount)}*\n"
                f"Months: *{months}*\n\n"
                "📎 Now please upload your payment proof (photo or document) in your next message."
            )
            await callback.message.edit_text(text, parse_mode="Markdown")
    
    await callback.answer()

@dp.callback_query(F.data == "history")
async def callback_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    payments = await db.list_payments(user_id, limit=20)
    if not payments:
        text = "📊 *Payment History* 📊\n\nNo payments found yet."
    else:
        lines = ["📊 *Payment History* 📊\n"]
        for p in payments:
            t = iso_to_date(p["paid_at"])
            lines.append(f"• {t.isoformat()}: {pretty_money(p['amount'])} for {p['months']} mo")
        text = "\n".join(lines)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    admin_commands = ""
    if is_admin(callback.from_user.id):
        admin_commands = (
            "\n*🔧 Admin Commands:*\n"
            "• /status — 📊 View who's paid & next due dates\n"
            "• /setmute <@user|id> <months> — 🔇 Mute reminders\n"
            "• /setamount <value> — 💰 Set monthly amount\n"
            "• /setday <1-28> — 📅 Set billing day\n"
            "• /proof <@user|id> — 🔍 Fetch latest proof\n"
            "• /addmember <@user|id> — 👤 Add/track a member\n"
            "• /remove <@user|id> — 🗑️ Remove member & data\n"
            "• /export — 📥 CSV export of all payments\n"
        )
    
    text = (
        "❓ *Help & Available Commands* ❓\n\n"
        "*📱 User Commands:*\n"
        "• /start — 🏠 Register & show main menu\n"
        "• /pay <amount> <months> — 💳 Begin payment process\n"
        "• /history — 📊 View your last 20 payments\n"
        "• /help — ❓ Show this help message\n"
        + admin_commands +
        "\n💡 *Tips:*\n"
        "• Use the buttons below for quick actions\n"
        "• After /pay, upload your payment proof immediately\n"
        "• Contact admin if you have any issues\n"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=create_help_menu())
    await callback.answer()

# Admin callback handlers
@dp.callback_query(F.data == "admin_menu")
async def callback_admin_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    text = (
        "🔧 *Admin Panel* 🔧\n\n"
        "Welcome admin! Choose an option below:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=create_admin_menu())
    await callback.answer()

@dp.callback_query(F.data == "status")
async def callback_status(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    users = await db.all_users()
    if not users:
        text = "📊 *User Status* 📊\n\nNo users registered yet."
    else:
        # Build status similar to cmd_status
        tz = ZoneInfo(TZNAME)
        today = datetime.now(tz).date()
        lines = ["📊 *User Status* 📊\n"]
        
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
                anchor = date(today.year, today.month, 1).replace(day=min(BILLING_DAY, 28))
                status = f"no payments yet, next due {anchor.isoformat()}"

            mute = f", muted until {u['muted_until']}" if u["muted_until"] else ""
            uname = f"@{u['username']}" if u["username"] else str(u["user_id"])
            lines.append(f"• {uname}: {status}{mute}")
        
        text = "\n".join(lines)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_settings")
async def callback_admin_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    text = (
        "⚙️ *Settings* ⚙️\n\n"
        f"Current monthly amount: *{pretty_money(MONTHLY_AMOUNT)}*\n"
        f"Current billing day: *{BILLING_DAY}*\n\n"
        "Choose what to modify:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=create_admin_settings_menu())
    await callback.answer()

@dp.callback_query(F.data == "user_management")
async def callback_user_management(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    text = (
        "👥 *User Management* 👥\n\n"
        "Manage users and their data:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=create_user_management_menu())
    await callback.answer()

@dp.callback_query(F.data.startswith("set_") or F.data.startswith("add_") or F.data.startswith("mute_") or F.data.startswith("remove_") or F.data.startswith("get_"))
async def callback_admin_actions(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    action = callback.data
    if action == "set_amount":
        text = (
            "💰 *Set Monthly Amount* 💰\n\n"
            f"Current amount: *{pretty_money(MONTHLY_AMOUNT)}*\n\n"
            "Use the command: `/setamount <value>`\n"
            "Example: `/setamount 3.50`"
        )
    elif action == "set_day":
        text = (
            "📅 *Set Billing Day* 📅\n\n"
            f"Current billing day: *{BILLING_DAY}*\n\n"
            "Use the command: `/setday <1-28>`\n"
            "Example: `/setday 15`"
        )
    elif action == "add_member":
        text = (
            "👤 *Add Member* 👤\n\n"
            "Use the command: `/addmember <@user|id>`\n"
            "Example: `/addmember @username` or `/addmember 123456789`"
        )
    elif action == "mute_user":
        text = (
            "🔇 *Mute User* 🔇\n\n"
            "Use the command: `/setmute <@user|id> <months>`\n"
            "Example: `/setmute @username 2`"
        )
    elif action == "remove_user":
        text = (
            "🗑️ *Remove User* 🗑️\n\n"
            "Use the command: `/remove <@user|id>`\n"
            "Example: `/remove @username` or `/remove 123456789`"
        )
    elif action == "get_proof":
        text = (
            "🔍 *Get Proof* 🔍\n\n"
            "Use the command: `/proof <@user|id>`\n"
            "Example: `/proof @username` or `/proof 123456789`"
        )
    else:
        text = "Unknown action"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="user_management" if action.startswith(("add_", "mute_", "remove_", "get_")) else "admin_settings")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "export")
async def callback_export(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    rows = await db.export_all_payments()
    if not rows:
        text = "📥 *Export Data* 📥\n\nNo payments to export."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")]])
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id","user_id","username","first_name","last_name","amount","months","proof_file_id","paid_at"])
        writer.writerows(rows)
        output.seek(0)
        data = io.BytesIO(output.getvalue().encode("utf-8"))
        data.name = "payments.csv"
        await bot.send_document(chat_id=callback.message.chat.id, document=data, caption="📥 All payments export")
    
    await callback.answer()

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
        text = (
            "⏰ *Payment Reminder* ⏰\n\n"
            f"Hi! It's time to pay your Apple Music share of *{pretty_money(MONTHLY_AMOUNT)}*.\n\n"
            "💡 Quick options:"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💰 Pay {pretty_money(MONTHLY_AMOUNT)} (1 month)", callback_data=f"pay_{MONTHLY_AMOUNT}_1")],
            [InlineKeyboardButton(text="💳 Custom Amount", callback_data="pay_custom")],
            [InlineKeyboardButton(text="📊 View History", callback_data="history")]
        ])
        
        await bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=keyboard)
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
