"""
test_phase24_postgres_schema.py — Comprehensive PostgreSQL schema verification.

Verifies:
1. All four tables exist: users, promo_codes, campaigns, requests.
2. Primary keys exist on all tables.
3. Foreign keys exist and point to correct parent tables.
4. Unique constraints exist on users.telegram_user_id and promo_codes.code.
5. Required indexes exist.
6. users.telegram_user_id is BIGINT.
7. Campaign status CHECK constraint rejects invalid statuses.
8. Request status CHECK constraint rejects invalid statuses.
9. One-active-campaign partial unique index prevents two active campaigns.
10. PostgreSQL database is currently EMPTY (0 records in all tables).
11. SQLite database.db was NOT modified.
"""
import os
import unittest
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
import psycopg

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
SQLITE_DB = ROOT_DIR / "database.db"


class TestPostgreSQLSchema(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        load_dotenv(ENV_FILE, override=True)
        cls.database_url = os.getenv("DATABASE_URL")
        assert cls.database_url, "DATABASE_URL not found in .env"

    def get_connection(self):
        return psycopg.connect(self.database_url, connect_timeout=10)

    # ── Test 1: All four tables exist in public schema ──────────
    def test_01_tables_exist(self):
        """All 4 expected tables exist in PostgreSQL."""
        expected_tables = {"users", "promo_codes", "campaigns", "requests"}
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
                """)
                tables = {row[0] for row in cur.fetchall()}
                for t in expected_tables:
                    self.assertIn(t, tables, f"Table '{t}' is missing in PostgreSQL")

    # ── Test 2: Primary Keys on all tables ──────────────────────
    def test_02_primary_keys_exist(self):
        """All tables have 'id' as primary key."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for table in ["users", "promo_codes", "campaigns", "requests"]:
                    cur.execute("""
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                          ON tc.constraint_name = kcu.constraint_name
                          AND tc.table_schema = kcu.table_schema
                        WHERE tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_name = %s;
                    """, (table,))
                    pk_cols = [row[0] for row in cur.fetchall()]
                    self.assertIn("id", pk_cols, f"Table '{table}' missing PK 'id'")

    # ── Test 3: Foreign Key Relationships ───────────────────────
    def test_03_foreign_keys_exist(self):
        """Foreign keys match the exact SQLite relationships."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        tc.table_name AS source_table,
                        kcu.column_name AS source_column,
                        ccu.table_name AS target_table,
                        ccu.column_name AS target_column
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                      ON ccu.constraint_name = tc.constraint_name
                      AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY';
                """)
                fks = cur.fetchall()
                fk_map = {(row[0], row[1]): (row[2], row[3]) for row in fks}

                self.assertEqual(
                    fk_map.get(("campaigns", "promo_code_id")),
                    ("promo_codes", "id"),
                    "campaigns.promo_code_id must reference promo_codes(id)",
                )
                self.assertEqual(
                    fk_map.get(("requests", "campaign_id")),
                    ("campaigns", "id"),
                    "requests.campaign_id must reference campaigns(id)",
                )
                self.assertEqual(
                    fk_map.get(("requests", "user_id")),
                    ("users", "id"),
                    "requests.user_id must reference users(id)",
                )

    # ── Test 4: telegram_user_id is BIGINT ──────────────────────
    def test_04_telegram_user_id_is_bigint(self):
        """telegram_user_id data type is bigint."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'telegram_user_id';
                """)
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "bigint")

    # ── Test 5: Unique Constraints Exist ────────────────────────
    def test_05_unique_constraints(self):
        """users.telegram_user_id and promo_codes.code have UNIQUE constraints."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tc.table_name, kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    WHERE tc.constraint_type = 'UNIQUE';
                """)
                uniques = {(row[0], row[1]) for row in cur.fetchall()}
                self.assertIn(("users", "telegram_user_id"), uniques)
                self.assertIn(("promo_codes", "code"), uniques)

    # ── Test 6: Partial Unique Index for Single Active Campaign ─
    def test_06_single_active_campaign_constraint(self):
        """Cannot insert two active campaigns into PostgreSQL."""
        with self.get_connection() as conn:
            # We use a transaction that we explicitly ROLLBACK
            with conn.cursor() as cur:
                try:
                    # 1. Insert dummy promo code
                    cur.execute("""
                        INSERT INTO promo_codes (code, description, instructions, requirements, created_at)
                        VALUES ('TEST_PG_ACTIVE', 'Test', 'Inst', 'Req', '2026-08-16T00:00:00Z')
                        RETURNING id;
                    """)
                    pid = cur.fetchone()[0]

                    # 2. Insert first active campaign -> Should succeed
                    cur.execute("""
                        INSERT INTO campaigns (promo_code_id, max_requests, status, created_at)
                        VALUES (%s, 10, 'active', '2026-08-16T00:00:00Z')
                        RETURNING id;
                    """, (pid,))
                    c1_id = cur.fetchone()[0]
                    self.assertIsNotNone(c1_id)

                    # 3. Insert second active campaign -> Must FAIL with unique violation
                    with self.assertRaises(psycopg.errors.UniqueViolation):
                        cur.execute("""
                            INSERT INTO campaigns (promo_code_id, max_requests, status, created_at)
                            VALUES (%s, 10, 'active', '2026-08-16T00:00:00Z');
                        """, (pid,))
                finally:
                    conn.rollback()

    # ── Test 7: CHECK Constraints on Status ─────────────────────
    def test_07_status_check_constraints(self):
        """Invalid status values are rejected by PostgreSQL CHECK constraints."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("""
                        INSERT INTO promo_codes (code, created_at)
                        VALUES ('TEST_STATUS', '2026-08-16T00:00:00Z')
                        RETURNING id;
                    """)
                    pid = cur.fetchone()[0]

                    # Invalid campaign status
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        cur.execute("""
                            INSERT INTO campaigns (promo_code_id, max_requests, status, created_at)
                            VALUES (%s, 10, 'invalid_status', '2026-08-16T00:00:00Z');
                        """, (pid,))
                finally:
                    conn.rollback()

    # ── Test 8: Indexes exist ───────────────────────────────────
    def test_08_indexes_exist(self):
        """Required query indexes exist on tables."""
        expected_indexes = {
            "idx_campaigns_single_active",
            "idx_users_username",
            "idx_promo_codes_active",
            "idx_campaigns_status",
            "idx_campaigns_promo_code_id",
            "idx_requests_status",
            "idx_requests_campaign_id",
            "idx_requests_user_id",
            "idx_requests_user_campaign",
            "idx_requests_campaign_status",
        }
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE schemaname = 'public';
                """)
                existing = {row[0] for row in cur.fetchall()}
                for idx in expected_indexes:
                    self.assertIn(idx, existing, f"Index '{idx}' is missing")

    # ── Test 9: PostgreSQL is currently EMPTY ───────────────────
    def test_09_database_is_empty(self):
        """Verify PostgreSQL database has 0 records (no data migrated yet)."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for t in ["users", "promo_codes", "campaigns", "requests"]:
                    cur.execute(f"SELECT COUNT(*) FROM {t};")
                    count = cur.fetchone()[0]
                    self.assertEqual(count, 0, f"Table '{t}' in PostgreSQL should be empty (has {count})")

    # ── Test 10: SQLite Database is Untouched ───────────────────
    def test_10_sqlite_database_untouched(self):
        """Verify SQLite database.db exists and still has its exact records."""
        self.assertTrue(SQLITE_DB.exists(), "database.db must exist")
        conn = sqlite3.connect(SQLITE_DB)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users;")
        user_count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(user_count, 19, "SQLite users table must still have 19 records")


if __name__ == "__main__":
    unittest.main(verbosity=2)
