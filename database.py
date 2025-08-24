import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent / "database.db"


async def init_db():
    """Initialize database with required tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        await db.commit()


async def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    """Insert or update user information."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name
        """, (user_id, username, first_name, last_name))
        await db.commit()


async def all_users():
    """Return all users."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, username, first_name, last_name FROM users")
        rows = await cursor.fetchall()
        return rows


async def list_payments(user_id: int = None):
    """
    Return all payments or payments for a specific user.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id:
            cursor = await db.execute(
                "SELECT id, user_id, amount, created_at FROM payments WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT id, user_id, amount, created_at FROM payments ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return rows


async def add_payment(user_id: int, amount: float):
    """Insert a payment for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (user_id, amount) VALUES (?, ?)",
            (user_id, amount)
        )
        await db.commit()
