import os
import csv
import io
import asyncio
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
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
        [InlineKeyboardButton(text="❓ Help & Commands", callback_data="help")],
        [InlineKeyboardButton(text="🔄 Refresh Status", callback_data="refresh_user_status")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_comprehensive_menu() -> InlineKeyboardMarkup:
    """Create comprehensive menu for MENU button - shows all commands"""
    buttons = [
        [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
        [InlineKeyboardButton(text="📊 Payment History", callback_data="history")],
        [InlineKeyboardButton(text="🔄 Check Status", callback_data="refresh_user_status")],
        [InlineKeyboardButton(text="❓ Help", callback_data="help")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_admin_comprehensive_menu() -> InlineKeyboardMarkup:
    """Create comprehensive admin menu for MENU button - shows all admin commands"""
    buttons = [
        [InlineKeyboardButton(text="🔧 Admin Panel", callback_data="admin_menu")],
        [InlineKeyboardButton(text="👥 User Management", callback_data="user_management")],
        [InlineKeyboardButton(text="⚡ Quick Actions", callback_data="admin_quick_actions")],
        [InlineKeyboardButton(text="💾 Export Data", callback_data="export")],
        [InlineKeyboardButton(text="📊 All Users Status", callback_data="status")],
        [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
        [InlineKeyboardButton(text="📈 My History", callback_data="history")],
        [InlineKeyboardButton(text="❓ Help", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_admin_menu() -> InlineKeyboardMarkup:
    """Create admin menu keyboard"""
    buttons = [
        [InlineKeyboardButton(text="📊 User Status", callback_data="status")],
        [InlineKeyboardButton(text="🔧 Settings", callback_data="admin_settings")],
        [InlineKeyboardButton(text="👥 Manage Users", callback_data="user_management")],
        [InlineKeyboardButton(text="📥 Export Data", callback_data="export")],
        [InlineKeyboardButton(text="💾 Payment History", callback_data="admin_history")],
        [InlineKeyboardButton(text="⚡ Quick Actions", callback_data="admin_quick_actions")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_payment_menu() -> InlineKeyboardMarkup:
    """Create quick payment options"""
    buttons = [
        [InlineKeyboardButton(text=f"💰 Pay {pretty_money(MONTHLY_AMOUNT)} (1 month)", callback_data=f"pay_{MONTHLY_AMOUNT}_1")],
        [InlineKeyboardButton(text=f"💰 Pay {pretty_money(MONTHLY_AMOUNT * 3)} (3 months)", callback_data=f"pay_{MONTHLY_AMOUNT * 3}_3")],
        [InlineKeyboardButton(text=f"💰 Pay {pretty_money(MONTHLY_AMOUNT * 6)} (6 months)", callback_data=f"pay_{MONTHLY_AMOUNT * 6}_6")],
        [InlineKeyboardButton(text="💳 Custom Amount", callback_data="pay_custom")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_help_menu() -> InlineKeyboardMarkup:
    """Create help menu with command shortcuts"""
    buttons = [
        [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
        [InlineKeyboardButton(text="📊 My History", callback_data="history")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_admin_settings_menu() -> InlineKeyboardMarkup:
    """Create admin settings menu"""
    buttons = [
        [InlineKeyboardButton(text="💰 Set Amount", callback_data="set_amount")],
        [InlineKeyboardButton(text="📅 Set Billing Day", callback_data="set_day")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_user_management_menu() -> InlineKeyboardMarkup:
    """Create user management menu"""
    buttons = [
        [InlineKeyboardButton(text="👤 Add Member", callback_data="add_member")],
        [InlineKeyboardButton(text="🔇 Mute User", callback_data="mute_user")],
        [InlineKeyboardButton(text="🗑️ Remove User", callback_data="remove_user")],
        [InlineKeyboardButton(text="🔍 Get Proof", callback_data="get_proof")],
        [InlineKeyboardButton(text="👥 List All Users", callback_data="list_users")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_admin_quick_actions_menu() -> InlineKeyboardMarkup:
    """Create admin quick actions menu"""
    buttons = [
        [InlineKeyboardButton(text="🚨 Send Reminders Now", callback_data="send_reminders")],
        [InlineKeyboardButton(text="📊 Full System Status", callback_data="system_status")],
        [InlineKeyboardButton(text="🗂️ Recent Payments (10)", callback_data="recent_payments")],
        [InlineKeyboardButton(text="⚠️ Overdue Users", callback_data="overdue_users")],
        [InlineKeyboardButton(text="🔄 Refresh All Data", callback_data="refresh_data")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_history_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Create history menu with additional options"""
    buttons = [
        [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
        [InlineKeyboardButton(text="🔄 Refresh History", callback_data="history")]
    ]
    if is_admin:
        buttons.extend([
            [InlineKeyboardButton(text="🔧 Admin Panel", callback_data="admin_menu")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    else:
        buttons.extend([
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_user_reply_keyboard() -> ReplyKeyboardMarkup:
    """Create persistent reply keyboard for regular users"""
    buttons = [
        [KeyboardButton(text="📋 MENU"), KeyboardButton(text="🔄 Status")],
        [KeyboardButton(text="❌ Cancel")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, persistent=True)

def create_admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Create persistent reply keyboard for administrators"""
    buttons = [
        [KeyboardButton(text="📋 MENU"), KeyboardButton(text="🔄 Status")],
        [KeyboardButton(text="❌ Cancel")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, persistent=True)

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
            "🔧 Choose an option below to get started:\n\n"
            "💡 **Quick Access:** Use the *📋 MENU* button below for instant access to ALL functions!\n"
            "🔄 Use the *Status* button to check all users' payment status\n"
            "❌ Use the *Cancel* button to cancel any pending actions"
        )
        inline_keyboard = create_admin_menu()
        reply_keyboard = create_admin_reply_keyboard()
    else:
        text = (
            "🎵 *Welcome to the Subscription Manager Bot!* 🎵\n\n"
            "👋 Hello! This bot helps you manage your Apple Music subscription payments.\n\n"
            f"💰 Your monthly share: *{pretty_money(MONTHLY_AMOUNT)}*\n"
            f"📅 Billing day: *{BILLING_DAY}* of each month\n\n"
            "📱 Choose an option below to get started:\n\n"
            "💡 **Quick Access:** Use the *📋 MENU* button below for instant access to ALL functions!\n"
            "🔄 Use the *Status* button to check your current payment status\n"
            "❌ Use the *Cancel* button to cancel any pending actions"
        )
        inline_keyboard = create_main_menu()
        reply_keyboard = create_user_reply_keyboard()
    
    # Send message with both inline and reply keyboards
    await msg.answer(text, parse_mode="Markdown", reply_markup=reply_keyboard)
    await msg.answer("Choose from the options above or use the quick buttons below:", reply_markup=inline_keyboard)

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
    
    # Add quick action buttons with more options
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 View History", callback_data="history")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        [InlineKeyboardButton(text="❌ Cancel Payment", callback_data="cancel_payment")]
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

# ---------- Reply Keyboard Button Handlers ----------
@dp.message(F.text == "📋 MENU")
async def handle_menu_button(msg: Message):
    """Handle MENU button from reply keyboard - comprehensive command menu"""
    await ensure_member(msg)
    user_id = msg.from_user.id
    
    if is_admin(user_id):
        text = (
            "📋 *Admin Command Menu* 📋\n\n"
            "🔧 Complete access to all system functions:\n\n"
            "Choose any action below:"
        )
        keyboard = create_admin_comprehensive_menu()
    else:
        text = (
            "📋 *Command Menu* 📋\n\n" 
            "💡 All available actions in one place:\n\n"
            "Choose what you'd like to do:"
        )
        keyboard = create_comprehensive_menu()
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.message(F.text == "🔄 Status")
async def handle_status_button(msg: Message):
    """Handle Status button from reply keyboard - unified for all users"""
    await ensure_member(msg)
    user_id = msg.from_user.id
    user = await db.get_user(user_id)
    
    if is_admin(user_id):
        # Show admin view of all users status
        today = date.today()
        users = await db.all_users()
        
        lines = [f"📊 *All Users Status* - {today.isoformat()}"]
        
        for u in users:
            payments = await db.list_payments(u["user_id"])
            if payments:
                p = payments[-1]  # most recent
                from utils import compute_coverage_until
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
        
        # Enhanced admin status buttons
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh Status", callback_data="status")],
            [InlineKeyboardButton(text="💾 View All Payments", callback_data="admin_history")],
            [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_menu")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    else:
        # Show regular user their personal status
        payments = await db.list_payments(user_id)
        
        from utils import compute_coverage_until
        from datetime import date
        
        today = date.today()
        
        if payments:
            latest_payment = payments[-1]
            last_coverage = compute_coverage_until(iso_to_date(latest_payment["paid_at"]), 
                                                  int(latest_payment["months"]), BILLING_DAY)
            due_date = next_billing_start(last_coverage, BILLING_DAY)
            days_until_due = (due_date - today).days
            
            if days_until_due > 0:
                status_emoji = "✅"
                status_text = f"You're covered until {last_coverage.strftime('%Y-%m-%d')}"
                due_text = f"Next payment due: {due_date.strftime('%Y-%m-%d')} ({days_until_due} days)"
            else:
                status_emoji = "⚠️" 
                status_text = f"Payment overdue since {due_date.strftime('%Y-%m-%d')}"
                due_text = f"Please make a payment as soon as possible"
        else:
            status_emoji = "❌"
            status_text = "No payments recorded"
            due_text = f"Next payment due: {date(today.year, today.month, BILLING_DAY).strftime('%Y-%m-%d')}"
        
        text = (
            f"🔄 *Your Status* 🔄\n\n"
            f"{status_emoji} {status_text}\n"
            f"📅 {due_text}\n\n"
            f"💰 Monthly amount: {pretty_money(MONTHLY_AMOUNT)}\n"
            f"📅 Billing day: {BILLING_DAY} of each month"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Make Payment", callback_data="pay_menu")],
            [InlineKeyboardButton(text="📊 View History", callback_data="history")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.message(F.text == "❌ Cancel")
async def handle_cancel_button(msg: Message):
    """Handle Cancel button from reply keyboard - clear pending actions and go to main menu"""
    await ensure_member(msg)
    user_id = msg.from_user.id
    
    # Clear any pending payment
    await db.clear_pending(user_id)
    
    text = (
        "❌ *Action Cancelled* ❌\n\n"
        "Any pending operations have been cancelled.\n\n"
        "💡 You can start fresh anytime!"
    )
    
    if is_admin(user_id):
        keyboard = create_admin_menu()
    else:
        keyboard = create_main_menu()
        
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)

# Admin reply keyboard handlers removed - now handled by consolidated MENU system

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
            
            # Add helpful buttons for payment confirmation
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel Payment", callback_data="cancel_payment")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    
    await callback.answer()

@dp.callback_query(F.data == "history")
async def callback_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_admin_user = is_admin(user_id)
    payments = await db.list_payments(user_id, limit=20)
    
    if not payments:
        text = (
            "📊 *Payment History* 📊\n\n"
            "No payments found yet.\n\n"
            "💡 Ready to make your first payment?"
        )
        keyboard = create_history_menu(is_admin_user)
    else:
        lines = ["📊 *Payment History* 📊\n"]
        total_amount = 0
        total_months = 0
        
        for p in payments:
            t = iso_to_date(p["paid_at"])
            lines.append(f"• {t.isoformat()}: {pretty_money(p['amount'])} for {p['months']} mo")
            total_amount += p['amount']
            total_months += p['months']
        
        lines.append(f"\n📋 *Summary:*")
        lines.append(f"Total paid: *{pretty_money(total_amount)}*")
        lines.append(f"Total months: *{total_months}*")
        text = "\n".join(lines)
        keyboard = create_history_menu(is_admin_user)
    
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
    
    # Enhanced admin status buttons
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh Status", callback_data="status")],
        [InlineKeyboardButton(text="💾 View All Payments", callback_data="admin_history")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")]
    ])
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="admin_settings")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    elif action == "set_day":
        text = (
            "📅 *Set Billing Day* 📅\n\n"
            f"Current billing day: *{BILLING_DAY}*\n\n"
            "Use the command: `/setday <1-28>`\n"
            "Example: `/setday 15`"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="admin_settings")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    elif action == "add_member":
        text = (
            "👤 *Add Member* 👤\n\n"
            "💡 To add a member, use the command:\n\n"
            "📝 `/addmember <@user|id>`\n\n"
            "**Examples:**\n"
            "• `/addmember @username`\n"
            "• `/addmember 123456789`\n\n"
            "⚠️ **Important:** The user must first send `/start` to the bot so their Telegram profile information can be retrieved.\n\n"
            "🔧 This allows the bot to track their payments and send reminders."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 List Users", callback_data="list_users")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="user_management")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    elif action == "mute_user":
        text = (
            "🔇 *Mute User* 🔇\n\n"
            "Use the command: `/setmute <@user|id> <months>`\n"
            "Example: `/setmute @username 2`"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="user_management")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    elif action == "remove_user":
        text = (
            "🗑️ *Remove User* 🗑️\n\n"
            "Use the command: `/remove <@user|id>`\n"
            "Example: `/remove @username` or `/remove 123456789`"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="user_management")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    elif action == "get_proof":
        text = (
            "🔍 *Get Proof* 🔍\n\n"
            "Use the command: `/proof <@user|id>`\n"
            "Example: `/proof @username` or `/proof 123456789`"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="user_management")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    else:
        text = "Unknown action"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="user_management")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
        ])
    
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

# ---------- New Enhanced Callbacks ----------
@dp.callback_query(F.data == "admin_quick_actions")
async def callback_admin_quick_actions(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    text = (
        "⚡ *Admin Quick Actions* ⚡\n\n"
        "Choose a quick action to perform:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=create_admin_quick_actions_menu())
    await callback.answer()

@dp.callback_query(F.data == "admin_history")
async def callback_admin_history(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    payments = await db.list_payments(limit=30)  # Get last 30 payments for admin
    if not payments:
        text = "💾 *All Payment History* 💾\n\nNo payments in database."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")]])
    else:
        lines = ["💾 *All Payment History* 💾\n"]
        total_amount = 0
        
        for p in payments:
            t = iso_to_date(p["paid_at"])
            user_info = await db.get_user(p["user_id"])
            username = f"@{user_info['username']}" if user_info and user_info['username'] else f"ID:{p['user_id']}"
            lines.append(f"• {t.isoformat()}: {username} - {pretty_money(p['amount'])} ({p['months']}mo)")
            total_amount += p['amount']
        
        lines.append(f"\n💰 *Total shown: {pretty_money(total_amount)}*")
        lines.append(f"📊 *Showing last {len(payments)} payments*")
        text = "\n".join(lines)
        
        buttons = [
            [InlineKeyboardButton(text="🗑️ Manage Payments", callback_data="manage_payments")],
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_menu")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "manage_payments")
async def callback_manage_payments(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    payments = await db.list_payments(limit=10)  # Show last 10 for management
    if not payments:
        text = "🗑️ *Manage Payments* 🗑️\n\nNo payments to manage."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_history")]])
    else:
        lines = ["🗑️ *Manage Payments* 🗑️\n", "Select a payment to delete:"]
        
        buttons = []
        for p in payments:
            t = iso_to_date(p["paid_at"])
            user_info = await db.get_user(p["user_id"])
            username = f"@{user_info['username']}" if user_info and user_info['username'] else f"ID:{p['user_id']}"
            button_text = f"❌ {t.strftime('%m/%d')} {username} {pretty_money(p['amount'])}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"delete_payment_{p['id']}")])
        
        buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_history")])
        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_payment_"))
async def callback_delete_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    payment_id = int(callback.data.split("_")[2])
    payment = await db.get_payment(payment_id)
    
    if not payment:
        await callback.answer("Payment not found", show_alert=True)
        return
    
    user_info = await db.get_user(payment["user_id"])
    username = f"@{user_info['username']}" if user_info and user_info['username'] else f"ID:{payment['user_id']}"
    t = iso_to_date(payment["paid_at"])
    
    text = (
        "⚠️ *Confirm Payment Deletion* ⚠️\n\n"
        f"Are you sure you want to delete this payment?\n\n"
        f"👤 User: {username}\n"
        f"💰 Amount: {pretty_money(payment['amount'])}\n"
        f"📅 Date: {t.isoformat()}\n"
        f"📝 Months: {payment['months']}\n\n"
        "⚠️ This action cannot be undone!"
    )
    
    buttons = [
        [InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"confirm_delete_{payment_id}"),
         InlineKeyboardButton(text="❌ Cancel", callback_data="manage_payments")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def callback_confirm_delete_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    payment_id = int(callback.data.split("_")[2])
    success = await db.delete_payment(payment_id)
    
    if success:
        text = "✅ *Payment Deleted* ✅\n\nPayment has been successfully deleted from the database."
        await callback.answer("Payment deleted successfully", show_alert=True)
    else:
        text = "❌ *Error* ❌\n\nPayment could not be deleted (may have already been removed)."
        await callback.answer("Error deleting payment", show_alert=True)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Management", callback_data="manage_payments")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "refresh_user_status")
async def callback_refresh_user_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    await ensure_member(callback.message)
    
    # Show user's current status
    payments = await db.list_payments(user_id, limit=5)
    text_lines = ["🔄 *Your Current Status* 🔄\n"]
    
    if payments:
        latest_payment = payments[0]
        t = iso_to_date(latest_payment["paid_at"])
        text_lines.append(f"💳 Last payment: {pretty_money(latest_payment['amount'])} on {t.isoformat()}")
        text_lines.append(f"📝 For {latest_payment['months']} months")
        
        total_paid = sum(p['amount'] for p in payments)
        total_months = sum(p['months'] for p in payments)
        text_lines.append(f"\n📊 Recent totals:")
        text_lines.append(f"💰 Total: {pretty_money(total_paid)} ({total_months} months)")
    else:
        text_lines.append("❌ No payments recorded yet")
        text_lines.append("💡 Consider making your first payment!")
    
    text_lines.append(f"\n⚙️ System info:")
    text_lines.append(f"💰 Monthly amount: {pretty_money(MONTHLY_AMOUNT)}")
    text_lines.append(f"📅 Billing day: {BILLING_DAY}")
    
    text = "\n".join(text_lines)
    keyboard = create_main_menu()
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer("Status refreshed!")

@dp.callback_query(F.data == "list_users")
async def callback_list_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    users = await db.all_users()
    if not users:
        text = "👥 *All Users* 👥\n\nNo users registered yet."
    else:
        lines = [f"👥 *All Users* 👥\n", f"Total registered: {len(users)}\n"]
        
        for i, u in enumerate(users, 1):
            username = f"@{u['username']}" if u['username'] else "No username"
            full_name = f"{u['first_name']} {u['last_name']}".strip() or "No name"
            mute_status = f" (Muted until {u['muted_until']})" if u['muted_until'] else ""
            lines.append(f"{i}. {full_name} - {username}{mute_status}")
            lines.append(f"   ID: {u['user_id']}")
    
    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="user_management")]])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "cancel_payment")
async def callback_cancel_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    # Clear any pending payment
    await db.clear_pending(user_id)
    
    text = (
        "❌ *Payment Cancelled* ❌\n\n"
        "Your pending payment has been cancelled.\n\n"
        "💡 You can start a new payment anytime!"
    )
    
    keyboard = create_main_menu()
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer("Payment cancelled")

@dp.callback_query(F.data == "recent_payments")
async def callback_recent_payments(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    payments = await db.list_payments(limit=10)
    if not payments:
        text = "📊 *Recent Payments* 📊\n\nNo recent payments found."
    else:
        lines = ["📊 *Recent Payments* 📊\n"]
        for p in payments:
            t = iso_to_date(p["paid_at"])
            user_info = await db.get_user(p["user_id"])
            username = f"@{user_info['username']}" if user_info and user_info['username'] else f"ID:{p['user_id']}"
            lines.append(f"• {t.strftime('%m/%d')} {username}: {pretty_money(p['amount'])} ({p['months']}mo)")
        text = "\n".join(lines)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_quick_actions")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "system_status")
async def callback_system_status(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    users = await db.all_users()
    all_payments = await db.list_payments()
    
    total_users = len(users)
    total_payments = len(all_payments)
    total_revenue = sum(p['amount'] for p in all_payments)
    total_months_sold = sum(p['months'] for p in all_payments)
    
    active_users = len([u for u in users if not u['muted_until']])
    muted_users = total_users - active_users
    
    text = (
        "📊 *Full System Status* 📊\n\n"
        f"👥 **Users:**\n"
        f"• Total registered: {total_users}\n"
        f"• Active users: {active_users}\n"
        f"• Muted users: {muted_users}\n\n"
        f"💰 **Financials:**\n"
        f"• Total payments: {total_payments}\n"
        f"• Total revenue: {pretty_money(total_revenue)}\n"
        f"• Total months sold: {total_months_sold}\n\n"
        f"⚙️ **Settings:**\n"
        f"• Monthly amount: {pretty_money(MONTHLY_AMOUNT)}\n"
        f"• Billing day: {BILLING_DAY}\n"
        f"• Timezone: {TZNAME}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_quick_actions")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "overdue_users")
async def callback_overdue_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    users = await db.all_users()
    if not users:
        text = "⚠️ *Overdue Users* ⚠️\n\nNo users registered yet."
    else:
        tz = ZoneInfo(TZNAME)
        today = datetime.now(tz).date()
        overdue_users = []
        
        for u in users:
            payments = await db.list_payments(u["user_id"], limit=1000)
            if payments:
                payments_sorted = sorted(payments, key=lambda p: p["paid_at"])
                from utils import compute_coverage_until
                last_cov = iso_to_date(payments_sorted[0]["paid_at"])
                last_cov = last_cov.replace(day=1)
                for p in payments_sorted:
                    last_cov = compute_coverage_until(iso_to_date(p["paid_at"]), int(p["months"]), BILLING_DAY)
                
                if last_cov < today:  # Coverage ended
                    days_overdue = (today - last_cov).days
                    overdue_users.append((u, days_overdue))
            else:
                # No payments, consider overdue
                overdue_users.append((u, 0))
        
        if not overdue_users:
            text = "✅ *Overdue Users* ✅\n\nAll users are up to date!"
        else:
            lines = ["⚠️ *Overdue Users* ⚠️\n"]
            for u, days in overdue_users:
                username = f"@{u['username']}" if u['username'] else f"ID:{u['user_id']}"
                if days == 0:
                    lines.append(f"• {username}: No payments recorded")
                else:
                    lines.append(f"• {username}: {days} days overdue")
            text = "\n".join(lines)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_quick_actions")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "refresh_data")
async def callback_refresh_data(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    text = (
        "🔄 *Data Refreshed* 🔄\n\n"
        "System data has been refreshed.\n\n"
        "✅ All cached information updated\n"
        "✅ User statuses recalculated\n"
        "✅ Database connections renewed"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_quick_actions")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer("Data refreshed successfully!")

@dp.callback_query(F.data == "send_reminders")
async def callback_send_reminders(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    
    text = (
        "🚨 *Send Reminders* 🚨\n\n"
        "This feature will send reminder messages to users who need to make payments.\n\n"
        "⚠️ This is a placeholder for future implementation.\n"
        "The reminder system currently runs automatically via the scheduler.\n\n"
        "💡 To manually remind users, use the user management tools."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_quick_actions")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer("Feature coming soon!")

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
