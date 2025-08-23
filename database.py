import aiosqlite
from typing import Optional, List, Tuple, Any
from datetime import datetime

DB_PATH = "data/bot.db"

INIT_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    last_name   TEXT,
    muted_until DATE,              -- if set, reminders suppressed until this date (exclusive)
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL NOT NULL,
    months      INTEGER NOT NULL,
    proof_file_id TEXT NOT NULL,
    paid_at     TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS pending_payments (
    user_id     INTEGER PRIMARY KEY,
    amount      REAL NOT NULL,
    months      INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
"""

async def open_db():
    return await aiosqlite.connect(DB_PATH)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(INIT_SQL)
        await db.commit()

# --- Users ---
async def upsert_user(user_id:int, username:str, first:str, last:str):
    now = datetime.utcnow().isoformat()
    async with open_db() as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, created_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              username=excluded.username,
              first_name=excluded.first_name,
              last_name=excluded.last_name
        """,(user_id, username, first, last, now))
        await db.commit()

async def all_users() -> List[aiosqlite.Row]:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY created_at ASC")
        return await cur.fetchall()

async def get_user(user_id:int) -> Optional[aiosqlite.Row]:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await cur.fetchone()

async def get_user_by_username(username:str) -> Optional[aiosqlite.Row]:
    # accept without @
    uname = username.lstrip("@")
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (uname,))
        return await cur.fetchone()

async def remove_user(user_id:int) -> int:
    async with open_db() as db:
        await db.execute("DELETE FROM payments WHERE user_id=?", (user_id,))
        res = await db.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        await db.commit()
        return res.rowcount

# --- Mute ---
async def set_muted_until(user_id:int, until_date:str):
    async with open_db() as db:
        await db.execute("UPDATE users SET muted_until=? WHERE user_id=?", (until_date, user_id))
        await db.commit()

# --- Payments ---
async def add_payment(user_id:int, amount:float, months:int, proof_file_id:str, paid_at_iso:str):
    async with open_db() as db:
        await db.execute("""
            INSERT INTO payments (user_id, amount, months, proof_file_id, paid_at)
            VALUES (?,?,?,?,?)
        """, (user_id, amount, months, proof_file_id, paid_at_iso))
        await db.commit()

async def list_payments(user_id:int, limit:int=20) -> List[aiosqlite.Row]:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM payments WHERE user_id=? ORDER BY paid_at DESC LIMIT ?
        """,(user_id, limit))
        return await cur.fetchall()

async def latest_payment(user_id:int) -> Optional[aiosqlite.Row]:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM payments WHERE user_id=? ORDER BY paid_at DESC LIMIT 1
        """,(user_id,))
        return await cur.fetchone()

async def sum_months_since(user_id:int, iso_cutoff:str) -> int:
    # Not used directly, but available for analytics
    async with open_db() as db:
        cur = await db.execute("""
            SELECT COALESCE(SUM(months),0) FROM payments
            WHERE user_id=? AND paid_at>=?
        """,(user_id, iso_cutoff))
        (total,) = await cur.fetchone()
        return int(total or 0)

# --- Pending flow ---
async def set_pending(user_id:int, amount:float, months:int):
    now = datetime.utcnow().isoformat()
    async with open_db() as db:
        await db.execute("""
            INSERT INTO pending_payments (user_id, amount, months, created_at)
            VALUES (?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount, months=excluded.months, created_at=excluded.created_at
        """,(user_id, amount, months, now))
        await db.commit()

async def get_pending(user_id:int) -> Optional[aiosqlite.Row]:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM pending_payments WHERE user_id=?", (user_id,))
        return await cur.fetchone()

async def clear_pending(user_id:int):
    async with open_db() as db:
        await db.execute("DELETE FROM pending_payments WHERE user_id=?", (user_id,))
        await db.commit()

# --- Reports ---
async def export_all_payments() -> List[Tuple[Any,...]]:
    async with open_db() as db:
        cur = await db.execute("""
            SELECT p.id, p.user_id, u.username, u.first_name, u.last_name, p.amount, p.months, p.proof_file_id, p.paid_at
            FROM payments p
            LEFT JOIN users u ON u.user_id=p.user_id
            ORDER BY p.paid_at DESC
        """)
        return await cur.fetchall()
