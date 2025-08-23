import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

API_TOKEN = "8435725472:AAETxBADH9XKiz3XKQZF1CTUtb9Wk3N3sLk"
ADMIN_ID = 864342269  # your Telegram user ID

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

DB = "data/payments.db"

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        months INTEGER,
        proof TEXT,
        paid_at TEXT
    )
    """)
    conn.commit()
    conn.close()

# --- Commands ---
@dp.message(Command("start"))
async def start(msg: types.Message):
    await msg.answer("👋 Welcome! This bot helps track Apple Music family payments.\n"
                     "Send /pay to submit proof, or wait for reminders.")

@dp.message(Command("pay"))
async def pay(msg: types.Message):
    await msg.answer("📸 Please send a screenshot or document as payment proof.")

@dp.message(lambda m: m.photo or m.document)
async def handle_proof(msg: types.Message):
    proof_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO payments (user_id, amount, months, proof, paid_at) VALUES (?,?,?,?,?)",
                (msg.from_user.id, 2.5, 1, proof_id, datetime.now().isoformat()))  # TODO: dynamic amount
    conn.commit()
    conn.close()
    await msg.answer("✅ Payment proof saved!")
    await bot.send_message(ADMIN_ID, f"💰 {msg.from_user.full_name} submitted payment proof.")

# --- Scheduler ---
async def send_reminders():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # TODO: filter only users who are due
    for user_id, in cur.execute("SELECT DISTINCT user_id FROM payments"):
        try:
            await bot.send_message(user_id, "⏰ Reminder: Please pay your Apple Music share!")
        except Exception as e:
            logging.error(f"Could not send reminder: {e}")
    conn.close()

async def main():
    init_db()
    scheduler.add_job(send_reminders, "interval", weeks=4)  # every 4 weeks
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
