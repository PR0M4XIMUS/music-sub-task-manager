import aiosqlite
from pathlib import Path
from typing import Optional, Dict, Any, List

DB_PATH = Path(__file__).parent / "database.db"


async def init_db():
    """Initialize database with required tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                muted_until TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                months INTEGER,
                proof_file_id TEXT,
                paid_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_payments (
                user_id INTEGER PRIMARY KEY,
                amount REAL,
                months INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


async def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    """Insert or update user information."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name
        """, (user_id, username, first_name, last_name))
        await db.commit()


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by user_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, username, first_name, last_name, muted_until FROM users WHERE user_id = ?", 
            (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user by username."""
    username = username.lstrip('@')  # Remove @ if present
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, username, first_name, last_name, muted_until FROM users WHERE username = ?", 
            (username,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def all_users() -> List[Dict[str, Any]]:
    """Return all users."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT user_id, username, first_name, last_name, muted_until FROM users")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def list_payments(user_id: int = None, limit: int = None) -> List[Dict[str, Any]]:
    """
    Return all payments or payments for a specific user.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            if limit:
                cursor = await db.execute(
                    "SELECT id, user_id, amount, months, proof_file_id, paid_at, created_at FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit)
                )
            else:
                cursor = await db.execute(
                    "SELECT id, user_id, amount, months, proof_file_id, paid_at, created_at FROM payments WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,)
                )
        else:
            if limit:
                cursor = await db.execute(
                    "SELECT id, user_id, amount, months, proof_file_id, paid_at, created_at FROM payments ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            else:
                cursor = await db.execute(
                    "SELECT id, user_id, amount, months, proof_file_id, paid_at, created_at FROM payments ORDER BY created_at DESC"
                )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def add_payment(user_id: int, amount: float, months: int, proof_file_id: str, paid_at_iso: str):
    """Insert a payment for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO payments (user_id, amount, months, proof_file_id, paid_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, months, proof_file_id, paid_at_iso)
        )
        await db.commit()


async def latest_payment(user_id: int) -> Optional[Dict[str, Any]]:
    """Get the latest payment for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, user_id, amount, months, proof_file_id, paid_at, created_at FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_pending(user_id: int, amount: float, months: int):
    """Set pending payment for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR REPLACE INTO pending_payments (user_id, amount, months) VALUES (?, ?, ?)",
            (user_id, amount, months)
        )
        await db.commit()


async def get_pending(user_id: int) -> Optional[Dict[str, Any]]:
    """Get pending payment for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, amount, months FROM pending_payments WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def clear_pending(user_id: int):
    """Clear pending payment for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pending_payments WHERE user_id = ?", (user_id,))
        await db.commit()


async def set_muted_until(user_id: int, muted_until: str):
    """Set muted_until date for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET muted_until = ? WHERE user_id = ?",
            (muted_until, user_id)
        )
        await db.commit()


async def remove_user(user_id: int) -> int:
    """Remove a user and all their data. Returns number of rows affected."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pending_payments WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.commit()
        return 1  # Simple return for now


async def export_all_payments() -> List[tuple]:
    """Export all payment data with user information."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT p.id, p.user_id, u.username, u.first_name, u.last_name, 
                   p.amount, p.months, p.proof_file_id, p.paid_at
            FROM payments p
            JOIN users u ON p.user_id = u.user_id
            ORDER BY p.created_at DESC
        """)
        rows = await cursor.fetchall()
        return [tuple(row) for row in rows]
