"""
database.py — PostgreSQL database layer using psycopg 3.

Connects to Neon PostgreSQL via DATABASE_URL from .env.
Preserves all existing function signatures and row["column"] access patterns.
Uses psycopg_pool.ConnectionPool for connection reuse.

SQLite fallback: if db_path is explicitly passed (not None and not DB_PATH),
functions route to SQLite for test isolation (existing test suite compatibility).
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Union, Generator

from dotenv import load_dotenv
import psycopg
import logging
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger("database")

# ---------------------------------------------------------------------------
# Paths & env
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).resolve().parent / "database.db"
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_FILE, override=True)
DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------------------------------------------------------------------
# Connection pool (PostgreSQL)
# ---------------------------------------------------------------------------
_pool: Optional[ConnectionPool] = None

def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            logger.error("DATABASE_URL is not set in environment")
            raise RuntimeError("DATABASE_URL is not set in environment")
        logger.info("Initializing PostgreSQL connection pool (min_size=1, max_size=10)...")
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        logger.info("PostgreSQL connection pool initialized successfully.")
    return _pool

def check_database_health() -> bool:
    """Bounded lightweight SELECT 1 connectivity check."""
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            return bool(row and (row["ok"] if isinstance(row, dict) else row[0]) == 1)
    except Exception as e:
        logger.error(f"Database health check failed: {e.__class__.__name__}")
        return False


def get_utc_now() -> str:
    """Return current UTC timestamp formatted in ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Connection helpers — dual SQLite/PostgreSQL routing
# ---------------------------------------------------------------------------

def _is_sqlite(db_path: Optional[Path]) -> bool:
    """Return True when the caller explicitly requests SQLite (test isolation)."""
    return db_path is not None and db_path != DB_PATH


@contextmanager
def _sqlite_connection(db_path: Path):
    """SQLite connection (used only during tests that pass db_path explicitly)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _pg_connection():
    """Acquire a psycopg 3 connection from the pool."""
    pool = _get_pool()
    with pool.connection() as conn:
        yield conn


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Generator:
    """
    Unified connection context manager.
    - If db_path is given (test isolation): opens a fresh SQLite connection.
    - Otherwise: acquires a PostgreSQL connection from the pool.
    """
    if db_path is not None:
        with _sqlite_connection(db_path) as conn:
            yield conn
    else:
        with _pg_connection() as conn:
            yield conn


# ---------------------------------------------------------------------------
# initialize_database
# ---------------------------------------------------------------------------

def initialize_database(db_path: Optional[Path] = None) -> None:
    """
    Initialize database tables.
    - SQLite path: creates tables (for test isolation only).
    - PostgreSQL path: no-op — schema already exists on Neon.
    """
    if db_path is not None:
        # Test isolation — create SQLite tables
        with _sqlite_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    created_at TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    description TEXT,
                    instructions TEXT,
                    requirements TEXT,
                    example_image TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    promo_code_id INTEGER NOT NULL,
                    max_requests INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'closed',
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    site_id TEXT,
                    screenshot_file_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
            """)
            conn.commit()
    # PostgreSQL: schema already created by scripts/create_postgres_schema.py — skip silently.


# ---------------------------------------------------------------------------
# Placeholder helper
# ---------------------------------------------------------------------------

def _ph(db_path: Optional[Path]) -> str:
    """Return the correct SQL placeholder character for the active backend."""
    return "?" if db_path is not None else "%s"


# ---------------------------------------------------------------------------
# User Helpers
# ---------------------------------------------------------------------------

def create_or_update_user(
    telegram_user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    """Insert new user or update existing user info. Returns user database id."""
    now = get_utc_now()
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO users (telegram_user_id, username, first_name, created_at)
            VALUES ({p}, {p}, {p}, {p})
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (telegram_user_id, username, first_name, now))
        conn.commit()

        cursor.execute(f"SELECT id FROM users WHERE telegram_user_id = {p}", (telegram_user_id,))
        row = cursor.fetchone()
        if row is None:
            return 0
        return row["id"] if isinstance(row, dict) else row[0]


def get_user_by_telegram_id(
    telegram_user_id: int,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve user record by Telegram user ID."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE telegram_user_id = {p}", (telegram_user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_user_by_telegram_id(
    telegram_user_id: int,
    db_path: Optional[Path] = None,
) -> bool:
    """Delete user by Telegram user ID (used for test cleanup)."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM users WHERE telegram_user_id = {p}", (telegram_user_id,))
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Promo Code Helpers
# ---------------------------------------------------------------------------

def create_promo_code(
    code: str,
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    requirements: Optional[str] = None,
    example_image: Optional[str] = None,
    active: int = 1,
    db_path: Optional[Path] = None,
) -> int:
    """Create a new promo code. Returns created promo code id."""
    now = get_utc_now()
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if db_path is not None:
            # SQLite: use lastrowid
            cursor.execute(f"""
                INSERT INTO promo_codes (code, description, instructions, requirements, example_image, active, created_at)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
            """, (code, description, instructions, requirements, example_image, active, now))
            conn.commit()
            return cursor.lastrowid or 0
        else:
            # PostgreSQL: use RETURNING id
            cursor.execute("""
                INSERT INTO promo_codes (code, description, instructions, requirements, example_image, active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (code, description, instructions, requirements, example_image, active, now))
            row = cursor.fetchone()
            conn.commit()
            return row["id"] if row else 0


def get_promo_code_by_code(
    code: str,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve promo code record by its actual promo code string."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM promo_codes WHERE code = {p}", (code,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_promo_code_by_id(
    promo_code_id: int,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve promo code record by its internal database ID."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM promo_codes WHERE id = {p}", (promo_code_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_promo_code(
    code_or_id: Union[int, str],
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Get promo code record by ID or code string."""
    if isinstance(code_or_id, int):
        return get_promo_code_by_id(code_or_id, db_path=db_path)
    return get_promo_code_by_code(str(code_or_id), db_path=db_path)


def get_active_promo_codes(
    db_path: Optional[Path] = None,
) -> list[Dict[str, Any]]:
    """Retrieve all currently active promo codes."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promo_codes WHERE active = 1 ORDER BY id ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def update_promo_code(
    code: str,
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    requirements: Optional[str] = None,
    example_image: Optional[str] = None,
    active: Optional[int] = None,
    new_code: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update promo code fields using the actual promo code string."""
    p = _ph(db_path)
    fields = []
    params = []

    if description is not None:
        fields.append(f"description = {p}")
        params.append(description)
    if instructions is not None:
        fields.append(f"instructions = {p}")
        params.append(instructions)
    if requirements is not None:
        fields.append(f"requirements = {p}")
        params.append(requirements)
    if example_image is not None:
        fields.append(f"example_image = {p}")
        params.append(example_image)
    if active is not None:
        fields.append(f"active = {p}")
        params.append(active)
    if new_code is not None:
        fields.append(f"code = {p}")
        params.append(new_code)

    if not fields:
        return False

    params.append(code)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE promo_codes SET {', '.join(fields)} WHERE code = {p}", params)
        conn.commit()
        return cursor.rowcount > 0


def disable_promo_code(code: str, db_path: Optional[Path] = None) -> bool:
    """Disable a promo code by setting active = 0."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE promo_codes SET active = 0 WHERE code = {p}", (code,))
        conn.commit()
        return cursor.rowcount > 0


def enable_promo_code(code: str, db_path: Optional[Path] = None) -> bool:
    """Enable a promo code by setting active = 1."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE promo_codes SET active = 1 WHERE code = {p}", (code,))
        conn.commit()
        return cursor.rowcount > 0


def disable_promo_code_by_id(promo_code_id: int, db_path: Optional[Path] = None) -> bool:
    """Disable a promo code by database ID."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE promo_codes SET active = 0 WHERE id = {p}", (promo_code_id,))
        conn.commit()
        return cursor.rowcount > 0


def enable_promo_code_by_id(promo_code_id: int, db_path: Optional[Path] = None) -> bool:
    """Enable a promo code by database ID."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE promo_codes SET active = 1 WHERE id = {p}", (promo_code_id,))
        conn.commit()
        return cursor.rowcount > 0


def update_promo_code_by_id(
    promo_code_id: int,
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    requirements: Optional[str] = None,
    example_image: Optional[str] = None,
    active: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update promo code fields using internal database ID (code remains immutable)."""
    p = _ph(db_path)
    fields = []
    params = []

    if description is not None:
        fields.append(f"description = {p}")
        params.append(description)
    if instructions is not None:
        fields.append(f"instructions = {p}")
        params.append(instructions)
    if requirements is not None:
        fields.append(f"requirements = {p}")
        params.append(requirements)
    if example_image is not None:
        fields.append(f"example_image = {p}")
        params.append(example_image)
    if active is not None:
        fields.append(f"active = {p}")
        params.append(active)

    if not fields:
        return False

    params.append(promo_code_id)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE promo_codes SET {', '.join(fields)} WHERE id = {p}", params)
        conn.commit()
        return cursor.rowcount > 0


def is_promo_code_used_in_active_campaign(
    promo_code_id: int,
    db_path: Optional[Path] = None,
) -> bool:
    """Check if a promo code is currently in use by an active or full campaign."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT 1 FROM campaigns
            WHERE promo_code_id = {p} AND status IN ('active', 'full')
            LIMIT 1
        """, (promo_code_id,))
        return cursor.fetchone() is not None


def delete_promo_code(code: str, db_path: Optional[Path] = None) -> bool:
    """Delete a promo code by actual code (used for test cleanup)."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM promo_codes WHERE code = {p}", (code,))
        conn.commit()
        return cursor.rowcount > 0


def resolve_promo_code_id(
    promo_code: Union[int, str],
    db_path: Optional[Path] = None,
) -> Optional[int]:
    """Helper to resolve promo code ID from int ID or string code."""
    if isinstance(promo_code, int):
        promo = get_promo_code_by_id(promo_code, db_path=db_path)
        return promo["id"] if promo else None
    else:
        promo = get_promo_code_by_code(str(promo_code), db_path=db_path)
        return promo["id"] if promo else None


# ---------------------------------------------------------------------------
# Campaign Helpers
# ---------------------------------------------------------------------------

def create_campaign(
    promo_code: Union[int, str],
    max_requests: int,
    status: str = "closed",
    db_path: Optional[Path] = None,
) -> int:
    """Create a new campaign for a promo code. Returns created campaign id."""
    if not isinstance(max_requests, int) or max_requests <= 0:
        raise ValueError("max_requests must be a positive integer greater than 0")

    valid_statuses = {"closed", "active", "full", "completed"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    if isinstance(promo_code, int):
        promo = get_promo_code_by_id(promo_code, db_path=db_path)
    else:
        promo = get_promo_code_by_code(str(promo_code), db_path=db_path)

    if not promo:
        raise ValueError("Referenced promo code does not exist")

    if promo["active"] != 1:
        raise ValueError("Cannot create a campaign for a disabled promo code")

    now = get_utc_now()
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if db_path is not None:
            cursor.execute(f"""
                INSERT INTO campaigns (promo_code_id, max_requests, status, created_at)
                VALUES ({p}, {p}, {p}, {p})
            """, (promo["id"], max_requests, status, now))
            conn.commit()
            return cursor.lastrowid or 0
        else:
            cursor.execute("""
                INSERT INTO campaigns (promo_code_id, max_requests, status, created_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (promo["id"], max_requests, status, now))
            row = cursor.fetchone()
            conn.commit()
            return row["id"] if row else 0


def get_campaign_by_id(
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve campaign record by ID including associated promo code details."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT c.*, p.code AS promo_code, p.active AS promo_code_active,
                   p.description AS promo_description, p.instructions AS promo_instructions,
                   p.requirements AS promo_requirements, p.example_image AS promo_example_image
            FROM campaigns c
            JOIN promo_codes p ON c.promo_code_id = p.id
            WHERE c.id = {p}
        """, (campaign_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_active_campaign(
    promo_code: Optional[Union[int, str]] = None,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve the active campaign, optionally filtered by promo code ID or code string."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if promo_code is not None:
            promo_id = resolve_promo_code_id(promo_code, db_path=db_path)
            if not promo_id:
                return None
            cursor.execute(f"""
                SELECT c.*, p.code AS promo_code, p.active AS promo_code_active,
                       p.description AS promo_description, p.instructions AS promo_instructions,
                       p.requirements AS promo_requirements, p.example_image AS promo_example_image
                FROM campaigns c
                JOIN promo_codes p ON c.promo_code_id = p.id
                WHERE c.status = 'active' AND c.promo_code_id = {p}
                ORDER BY c.id DESC
                LIMIT 1
            """, (promo_id,))
        else:
            cursor.execute("""
                SELECT c.*, p.code AS promo_code, p.active AS promo_code_active,
                       p.description AS promo_description, p.instructions AS promo_instructions,
                       p.requirements AS promo_requirements, p.example_image AS promo_example_image
                FROM campaigns c
                JOIN promo_codes p ON c.promo_code_id = p.id
                WHERE c.status = 'active'
                ORDER BY c.id DESC
                LIMIT 1
            """)
        row = cursor.fetchone()
        return dict(row) if row else None


def get_campaigns(
    promo_code: Optional[Union[int, str]] = None,
    status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[Dict[str, Any]]:
    """Retrieve campaigns list filtered optionally by promo code and/or status."""
    p = _ph(db_path)
    query = """
        SELECT c.*, p.code AS promo_code, p.active AS promo_code_active,
               p.description AS promo_description, p.instructions AS promo_instructions,
               p.requirements AS promo_requirements, p.example_image AS promo_example_image
        FROM campaigns c
        JOIN promo_codes p ON c.promo_code_id = p.id
    """
    conditions = []
    params = []

    if promo_code is not None:
        promo_id = resolve_promo_code_id(promo_code, db_path=db_path)
        if not promo_id:
            return []
        conditions.append(f"c.promo_code_id = {p}")
        params.append(promo_id)

    if status is not None:
        conditions.append(f"c.status = {p}")
        params.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY c.id DESC"

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_campaign_pending_count(
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> int:
    """Count pending requests for a specific campaign."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) AS total FROM requests WHERE campaign_id = {p} AND status = 'pending'",
            (campaign_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return 0
        return row["total"] if isinstance(row, dict) else row[0]


count_pending_requests = get_campaign_pending_count


def get_campaign_remaining_slots(
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> int:
    """Calculate remaining available slots for pending requests in a campaign."""
    campaign = get_campaign_by_id(campaign_id, db_path=db_path)
    if not campaign:
        return 0
    pending_count = get_campaign_pending_count(campaign_id, db_path=db_path)
    return max(0, campaign["max_requests"] - pending_count)


def can_accept_request(
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> bool:
    """Check whether a campaign can currently accept new customer requests."""
    campaign = get_campaign_by_id(campaign_id, db_path=db_path)
    if not campaign:
        return False
    if campaign["status"] != "active":
        return False
    if campaign.get("promo_code_active") != 1:
        return False
    pending_count = get_campaign_pending_count(campaign_id, db_path=db_path)
    return pending_count < campaign["max_requests"]


def activate_campaign(
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> bool:
    """
    Activate a campaign with row-level locking (concurrency-safe).
    Verifies promo code is active and no other campaign is already active.
    """
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Lock the campaign row to prevent concurrent activation races
        if db_path is None:
            cursor.execute(f"""
                SELECT c.id, c.promo_code_id, c.max_requests, c.status,
                       p.active AS promo_code_active
                FROM campaigns c
                JOIN promo_codes p ON c.promo_code_id = p.id
                WHERE c.id = {p}
                FOR UPDATE
            """, (campaign_id,))
        else:
            cursor.execute(f"""
                SELECT c.id, c.promo_code_id, c.max_requests, c.status,
                       p.active AS promo_code_active
                FROM campaigns c
                JOIN promo_codes p ON c.promo_code_id = p.id
                WHERE c.id = {p}
            """, (campaign_id,))

        campaign = cursor.fetchone()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        if campaign["promo_code_active"] != 1:
            raise ValueError("Cannot activate a campaign with a disabled promo code")

        # Count pending requests within same transaction
        cursor.execute(
            f"SELECT COUNT(*) AS total FROM requests WHERE campaign_id = {p} AND status = 'pending'",
            (campaign_id,)
        )
        cnt_row = cursor.fetchone()
        pending_count = cnt_row["total"] if isinstance(cnt_row, dict) else cnt_row[0]
        new_status = "full" if pending_count >= campaign["max_requests"] else "active"

        cursor.execute(f"""
            UPDATE campaigns
            SET status = {p}, closed_at = NULL
            WHERE id = {p}
        """, (new_status, campaign_id))
        conn.commit()
        return cursor.rowcount > 0


def close_campaign(
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> bool:
    """Close an active or full campaign."""
    now = get_utc_now()
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE campaigns
            SET status = 'closed', closed_at = {p}
            WHERE id = {p}
        """, (now, campaign_id))
        conn.commit()
        return cursor.rowcount > 0


def complete_campaign(
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> bool:
    """Mark a campaign as completed."""
    now = get_utc_now()
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE campaigns
            SET status = 'completed', closed_at = {p}
            WHERE id = {p}
        """, (now, campaign_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_campaign(
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> bool:
    """Delete campaign and associated requests (for test cleanup only)."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM requests WHERE campaign_id = {p}", (campaign_id,))
        cursor.execute(f"DELETE FROM campaigns WHERE id = {p}", (campaign_id,))
        conn.commit()
        return cursor.rowcount > 0


def has_user_benefited(
    user_id: int,
    promo_code: Union[int, str],
    db_path: Optional[Path] = None,
) -> bool:
    """Check if a user has already benefited from a specific promo code."""
    promo_id = resolve_promo_code_id(promo_code, db_path=db_path)
    if not promo_id:
        return False
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT 1 FROM requests r
            JOIN campaigns c ON r.campaign_id = c.id
            WHERE r.user_id = {p} AND c.promo_code_id = {p} AND r.status IN ('approved', 'accepted')
            LIMIT 1
        """, (user_id, promo_id))
        return cursor.fetchone() is not None


def has_user_pending_request(
    user_id: int,
    campaign_id: int,
    db_path: Optional[Path] = None,
) -> bool:
    """Check if a user already has an active pending request in a specific campaign."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT 1 FROM requests
            WHERE user_id = {p} AND campaign_id = {p} AND status = 'pending'
            LIMIT 1
        """, (user_id, campaign_id))
        return cursor.fetchone() is not None


def get_user_benefited_promo_codes(
    user_id: int,
    db_path: Optional[Path] = None,
) -> list[str]:
    """Retrieve distinct promo codes that the user has already benefited from (accepted/approved)."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT DISTINCT p.code
            FROM requests r
            JOIN campaigns c ON r.campaign_id = c.id
            JOIN promo_codes p ON c.promo_code_id = p.id
            WHERE r.user_id = {p} AND r.status IN ('approved', 'accepted')
            ORDER BY p.code ASC
        """, (user_id,))
        rows = cursor.fetchall()
        codes = []
        for r in rows:
            codes.append(r["code"] if isinstance(r, dict) else r[0])
        return codes


# ---------------------------------------------------------------------------
# Request Helpers
# ---------------------------------------------------------------------------

def create_request(
    campaign_id: int,
    user_id: int,
    site_id: Optional[str] = None,
    screenshot_file_id: Optional[str] = None,
    status: str = "pending",
    db_path: Optional[Path] = None,
) -> int:
    """
    Create a new submission request.
    Concurrency-safe: locks campaign row with FOR UPDATE (PostgreSQL) before
    checking capacity, then inserts atomically.
    """
    now = get_utc_now()
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Lock campaign row for update (PostgreSQL) — prevents concurrent over-capacity inserts
        if db_path is None:
            cursor.execute(f"""
                SELECT c.id, c.promo_code_id, c.max_requests, c.status, p.active AS promo_active
                FROM campaigns c
                JOIN promo_codes p ON c.promo_code_id = p.id
                WHERE c.id = {p}
                FOR UPDATE
            """, (campaign_id,))
        else:
            cursor.execute(f"""
                SELECT c.id, c.promo_code_id, c.max_requests, c.status, p.active AS promo_active
                FROM campaigns c
                JOIN promo_codes p ON c.promo_code_id = p.id
                WHERE c.id = {p}
            """, (campaign_id,))

        campaign = cursor.fetchone()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        if status == "pending":
            if campaign["status"] != "active":
                raise ValueError(f"Campaign {campaign_id} is '{campaign['status']}' and cannot accept requests")
            if campaign["promo_active"] != 1:
                raise ValueError("Referenced promo code is disabled")

            # Check if user has already benefited from this promo code
            cursor.execute(f"""
                SELECT 1 FROM requests r
                JOIN campaigns c ON r.campaign_id = c.id
                WHERE r.user_id = {p} AND c.promo_code_id = {p} AND r.status IN ('approved', 'accepted')
                LIMIT 1
            """, (user_id, campaign["promo_code_id"]))
            if cursor.fetchone() is not None:
                raise ValueError("User has already benefited from this promo code")

            # Check if user already has a pending request in this campaign
            cursor.execute(f"""
                SELECT 1 FROM requests
                WHERE user_id = {p} AND campaign_id = {p} AND status = 'pending'
                LIMIT 1
            """, (user_id, campaign_id))
            if cursor.fetchone() is not None:
                raise ValueError("User already has a pending request for this campaign")

            cursor.execute(
                f"SELECT COUNT(*) AS total FROM requests WHERE campaign_id = {p} AND status = 'pending'",
                (campaign_id,)
            )
            cnt_row = cursor.fetchone()
            pending_count = cnt_row["total"] if isinstance(cnt_row, dict) else cnt_row[0]

            if pending_count >= campaign["max_requests"]:
                cursor.execute(f"UPDATE campaigns SET status = 'full' WHERE id = {p}", (campaign_id,))
                conn.commit()
                raise ValueError("Campaign is full; maximum pending requests reached")

            if db_path is not None:
                cursor.execute(f"""
                    INSERT INTO requests (campaign_id, user_id, site_id, screenshot_file_id, status, created_at)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p})
                """, (campaign_id, user_id, site_id, screenshot_file_id, status, now))
                request_id = cursor.lastrowid or 0
            else:
                cursor.execute("""
                    INSERT INTO requests (campaign_id, user_id, site_id, screenshot_file_id, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (campaign_id, user_id, site_id, screenshot_file_id, status, now))
                row = cursor.fetchone()
                request_id = row["id"] if row else 0

            # Automatically transition to 'full' if capacity is met
            if pending_count + 1 >= campaign["max_requests"]:
                cursor.execute(f"UPDATE campaigns SET status = 'full' WHERE id = {p}", (campaign_id,))

            conn.commit()
            return request_id
        else:
            if db_path is not None:
                cursor.execute(f"""
                    INSERT INTO requests (campaign_id, user_id, site_id, screenshot_file_id, status, created_at)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p})
                """, (campaign_id, user_id, site_id, screenshot_file_id, status, now))
                conn.commit()
                return cursor.lastrowid or 0
            else:
                cursor.execute("""
                    INSERT INTO requests (campaign_id, user_id, site_id, screenshot_file_id, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (campaign_id, user_id, site_id, screenshot_file_id, status, now))
                row = cursor.fetchone()
                conn.commit()
                return row["id"] if row else 0


def get_request_by_id(
    request_id: int,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve a submission request by ID with joined user, campaign, and promo details."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT r.*,
                   u.telegram_user_id, u.username, u.first_name,
                   c.promo_code_id, c.max_requests, c.status AS campaign_status,
                   p.code AS promo_code, p.description AS promo_description
            FROM requests r
            JOIN users u ON r.user_id = u.id
            JOIN campaigns c ON r.campaign_id = c.id
            JOIN promo_codes p ON c.promo_code_id = p.id
            WHERE r.id = {p}
        """, (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def review_request(
    request_id: int,
    new_status: str,
    db_path: Optional[Path] = None,
) -> tuple[bool, str]:
    """
    Atomically review a request (accept or reject).
    PostgreSQL: uses UPDATE ... WHERE status='pending' RETURNING id for atomic check-and-update.
    Returns (success, message/reason).
    """
    valid_statuses = {"accepted", "rejected", "approved"}
    if new_status not in valid_statuses:
        return False, f"Invalid status: {new_status}"

    now = get_utc_now()
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Fetch request + campaign info (with row lock on PostgreSQL)
        if db_path is None:
            cursor.execute(f"""
                SELECT r.*, c.promo_code_id, c.max_requests, c.status AS campaign_status
                FROM requests r
                JOIN campaigns c ON r.campaign_id = c.id
                WHERE r.id = {p}
                FOR UPDATE
            """, (request_id,))
        else:
            cursor.execute(f"""
                SELECT r.*, c.promo_code_id, c.max_requests, c.status AS campaign_status
                FROM requests r
                JOIN campaigns c ON r.campaign_id = c.id
                WHERE r.id = {p}
            """, (request_id,))

        req = cursor.fetchone()
        if not req:
            return False, "Request not found"

        if req["status"] != "pending":
            return False, f"Request already processed (current status: {req['status']})"

        if new_status in ("accepted", "approved"):
            # Check if user has already benefited from this promo code in another request
            cursor.execute(f"""
                SELECT 1 FROM requests r
                JOIN campaigns c ON r.campaign_id = c.id
                WHERE r.user_id = {p} AND c.promo_code_id = {p}
                  AND r.status IN ('approved', 'accepted') AND r.id != {p}
                LIMIT 1
            """, (req["user_id"], req["promo_code_id"], request_id))
            if cursor.fetchone() is not None:
                return False, "Customer has already benefited from this promo code"

        # Atomically update the request status
        cursor.execute(f"""
            UPDATE requests
            SET status = {p}, reviewed_at = {p}
            WHERE id = {p} AND status = 'pending'
        """, (new_status, now, request_id))

        if cursor.rowcount == 0:
            conn.rollback()
            return False, "Request was already processed by another reviewer"

        # Check if campaign was 'full' and now has available pending slots
        cursor.execute(
            f"SELECT COUNT(*) AS total FROM requests WHERE campaign_id = {p} AND status = 'pending'",
            (req["campaign_id"],)
        )
        cnt_row = cursor.fetchone()
        new_pending_count = cnt_row["total"] if isinstance(cnt_row, dict) else cnt_row[0]
        if req["campaign_status"] == "full" and new_pending_count < req["max_requests"]:
            cursor.execute(f"UPDATE campaigns SET status = 'active' WHERE id = {p}", (req["campaign_id"],))

        conn.commit()
        return True, "Request reviewed successfully"


def update_request_status(
    request_id: int,
    status: str,
    reviewed_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update request status and review timestamp."""
    review_time = reviewed_at or get_utc_now()
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE requests
            SET status = {p}, reviewed_at = {p}
            WHERE id = {p}
        """, (status, review_time, request_id))
        conn.commit()
        return cursor.rowcount > 0


def get_pending_requests_count(db_path: Optional[Path] = None) -> int:
    """Return the total count of all currently pending requests."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM requests WHERE status = 'pending'")
        row = cursor.fetchone()
        if row is None:
            return 0
        return row["total"] if isinstance(row, dict) else row[0]


def get_pending_requests(
    limit: int = 10,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> list[Dict[str, Any]]:
    """
    Retrieve pending requests with user and promo details, newest first.
    Supports pagination via limit/offset.
    """
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT r.*,
                   u.telegram_user_id, u.username, u.first_name,
                   p.code AS promo_code
            FROM requests r
            JOIN users u ON r.user_id = u.id
            JOIN campaigns c ON r.campaign_id = c.id
            JOIN promo_codes p ON c.promo_code_id = p.id
            WHERE r.status = 'pending'
            ORDER BY r.id DESC
            LIMIT {p} OFFSET {p}
        """, (limit, offset))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_all_promo_codes(db_path: Optional[Path] = None) -> list[Dict[str, Any]]:
    """Retrieve all promo codes (both active and inactive) ordered by id DESC."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promo_codes ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_dashboard_stats(db_path: Optional[Path] = None) -> Dict[str, int]:
    """Calculate aggregated stats from the database."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS total FROM users")
        total_users = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM promo_codes")
        total_promo_codes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM promo_codes WHERE active = 1")
        active_promo_codes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM requests WHERE status = 'pending'")
        pending_requests = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM requests WHERE status IN ('accepted', 'approved')")
        accepted_requests = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM requests WHERE status = 'rejected'")
        rejected_requests = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM campaigns WHERE status = 'active'")
        active_campaigns = cursor.fetchone()["total"]

        return {
            "total_users": total_users,
            "total_promo_codes": total_promo_codes,
            "active_promo_codes": active_promo_codes,
            "pending_requests": pending_requests,
            "accepted_requests": accepted_requests,
            "rejected_requests": rejected_requests,
            "active_campaigns": active_campaigns,
        }


def get_customers(
    limit: int = 20,
    offset: int = 0,
    search: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[Dict[str, Any]]:
    """Retrieve registered users with optional username/first_name search."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if search:
            pattern = f"%{search.strip()}%"
            cursor.execute(f"""
                SELECT id, telegram_user_id, username, first_name, created_at
                FROM users
                WHERE username LIKE {p} OR first_name LIKE {p}
                ORDER BY id DESC
                LIMIT {p} OFFSET {p}
            """, (pattern, pattern, limit, offset))
        else:
            cursor.execute(f"""
                SELECT id, telegram_user_id, username, first_name, created_at
                FROM users
                ORDER BY id DESC
                LIMIT {p} OFFSET {p}
            """, (limit, offset))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_customers_count(search: Optional[str] = None, db_path: Optional[Path] = None) -> int:
    """Return total count of customers matching optional search query."""
    p = _ph(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if search:
            pattern = f"%{search.strip()}%"
            cursor.execute(f"""
                SELECT COUNT(*) AS total FROM users
                WHERE username LIKE {p} OR first_name LIKE {p}
            """, (pattern, pattern))
        else:
            cursor.execute("SELECT COUNT(*) AS total FROM users")
        row = cursor.fetchone()
        if row is None:
            return 0
        return row["total"] if isinstance(row, dict) else row[0]


# ---------------------------------------------------------------------------
# Safe Self-Test (SQLite only — do not run against production PostgreSQL)
# ---------------------------------------------------------------------------

def run_database_test(db_path: Optional[Path] = None) -> bool:
    """Run a safe self-test. Must be called with an explicit db_path for SQLite isolation."""
    if db_path is None:
        raise RuntimeError("run_database_test() must be called with an explicit db_path for test isolation.")
    initialize_database(db_path)

    test_telegram_id = 999000111
    delete_user_by_telegram_id(test_telegram_id, db_path=db_path)
    user_db_id = create_or_update_user(
        telegram_user_id=test_telegram_id,
        username="test_user_phase11",
        first_name="Test",
        db_path=db_path,
    )
    assert user_db_id > 0, "Failed to create test user"

    user_record = get_user_by_telegram_id(test_telegram_id, db_path=db_path)
    assert user_record is not None
    assert user_record["telegram_user_id"] == test_telegram_id

    test_code = "MRC456"
    delete_promo_code(test_code, db_path=db_path)
    promo_id = create_promo_code(
        code=test_code,
        description="Test promo code for 50% discount",
        instructions="Enter code at checkout",
        requirements="New users only",
        db_path=db_path,
    )
    assert promo_id > 0

    camp_id = create_campaign(promo_code=test_code, max_requests=2, db_path=db_path)
    assert camp_id > 0
    camp = get_campaign_by_id(camp_id, db_path=db_path)
    assert camp["status"] == "closed"
    assert not can_accept_request(camp_id, db_path=db_path)

    activate_campaign(camp_id, db_path=db_path)
    assert can_accept_request(camp_id, db_path=db_path)
    assert get_campaign_remaining_slots(camp_id, db_path=db_path) == 2

    req1 = create_request(campaign_id=camp_id, user_id=user_db_id, db_path=db_path)
    assert req1 > 0
    assert get_campaign_remaining_slots(camp_id, db_path=db_path) == 1

    req2 = create_request(campaign_id=camp_id, user_id=user_db_id, db_path=db_path)
    assert req2 > 0
    camp_full = get_campaign_by_id(camp_id, db_path=db_path)
    assert camp_full["status"] == "full"
    assert not can_accept_request(camp_id, db_path=db_path)

    overflow_rejected = False
    try:
        create_request(campaign_id=camp_id, user_id=user_db_id, db_path=db_path)
    except ValueError:
        overflow_rejected = True
    assert overflow_rejected

    delete_campaign(camp_id, db_path=db_path)
    delete_promo_code(test_code, db_path=db_path)
    delete_user_by_telegram_id(test_telegram_id, db_path=db_path)
    return True


if __name__ == "__main__":
    print("database.py PostgreSQL layer loaded successfully.")
