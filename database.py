# database.py
import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

DB_PATH = "data/bot.db"

@asynccontextmanager
async def open_db():
    """Async context manager for opening/closing the database connection."""
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute("PRAGMA foreign_keys = ON;")
        yield db
    finally:
        await db.close()

# -------------------------
# User management
# -------------------------
async def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    async with open_db() as db:
        await db.execute(
            """
            INSERT INTO users (id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name
            """,
            (user_id, username, first_name, last_name),
        )
        await db.commit()

async def all_users():
    async with open_db() as db:
        cursor = await db.execute("SELECT id, username, first_name, last_name FROM users")
        rows = await cursor.fetchall()
        return rows

async def get_user(user_id: int):
    async with open_db() as db:
        cursor = await db.execute(
            "SELECT id, username, first_name, last_name FROM users WHERE id=?",
            (user_id,),
        )
        return await cursor.fetchone()

# -------------------------
# Payments
# -------------------------
async def add_payment(user_id: int, amount: float, proof_file: str, months: int = 1):
    async with open_db() as db:
        await db.execute(
            """
            INSERT INTO payments (user_id, amount, proof_file, months)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, amount, proof_file, months),
        )
        await db.commit()

async def get_user_payments(user_id: int):
    async with open_db() as db:
        cursor = await db.execute(
            "SELECT amount, proof_file, months, created_at FROM payments WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        )
        return await cursor.fetchall()

# -------------------------
# Reminders / subscription tracking
# -------------------------
async def set_silence(user_id: int, until: datetime):
    async with open_db() as db:
        await db.execute(
            """
            INSERT INTO silence (user_id, until)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET until=excluded.until
            """,
            (user_id, until.isoformat()),
        )
        await db.commit()

async def get_silence(user_id: int):
    async with open_db() as db:
        cursor = await db.execute(
            "SELECT until FROM silence WHERE user_id=?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row:
            return datetime.fromisoformat(row[0])
        return None

# -------------------------
# Payment history
# -------------------------
async def user_payment_history(user_id: int, limit: int = 10):
    async with open_db() as db:
        cursor = await db.execute(
            "SELECT amount, proof_file, months, created_at FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return await cursor.fetchall()

# -------------------------
# Utility functions
# -------------------------
async def get_due_users(current_date: datetime):
    """Return users whose subscription is due today."""
    async with open_db() as db:
        cursor = await db.execute(
            """
            SELECT u.id, u.username
            FROM users u
            LEFT JOIN silence s ON u.id = s.user_id
            WHERE s.until IS NULL OR s.until < ?
            """,
            (current_date.isoformat(),),
        )
        return await cursor.fetchall()
