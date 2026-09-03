"""
test_phase24_migration_verification.py — Verifies SQLite-to-PostgreSQL data migration.

Checks:
1. Row counts match between SQLite and PostgreSQL.
2. IDs are preserved exactly.
3. Data equality via checksums.
4. Foreign-key integrity.
5. Identity sequences are synchronized.
6. SQLite database.db is unchanged.
7. Application still uses SQLite (database.py imports sqlite3).
"""
import os
import sys
import sqlite3
import hashlib
import unittest
from pathlib import Path
from dotenv import load_dotenv
import psycopg

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
SQLITE_DB = ROOT_DIR / "database.db"

TABLES = ["users", "promo_codes", "campaigns", "requests"]
COLUMNS = {
    "users": ["id", "telegram_user_id", "username", "first_name", "created_at"],
    "promo_codes": ["id", "code", "description", "instructions", "requirements",
                     "example_image", "active", "created_at"],
    "campaigns": ["id", "promo_code_id", "max_requests", "status", "created_at", "closed_at"],
    "requests": ["id", "campaign_id", "user_id", "site_id", "screenshot_file_id",
                  "status", "created_at", "reviewed_at"],
}


def checksum_rows(rows):
    h = hashlib.sha256()
    for row in rows:
        h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


class TestMigrationVerification(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        load_dotenv(ENV_FILE, override=True)
        cls.database_url = os.getenv("DATABASE_URL")
        assert cls.database_url, "DATABASE_URL not found"

    def get_pg(self):
        return psycopg.connect(self.database_url, connect_timeout=10)

    def get_sqlite(self):
        conn = sqlite3.connect(f"file:{SQLITE_DB}?mode=ro", uri=True)
        return conn

    # Test 1: Row counts match
    def test_01_row_counts_match(self):
        pg = self.get_pg()
        sq = self.get_sqlite()
        for table in TABLES:
            sq_cur = sq.cursor()
            sq_cur.execute(f"SELECT COUNT(*) FROM {table}")
            sq_count = sq_cur.fetchone()[0]

            pg_cur = pg.cursor()
            pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
            pg_count = pg_cur.fetchone()[0]

            self.assertEqual(sq_count, pg_count, f"{table}: SQLite={sq_count}, PG={pg_count}")
        pg.close()
        sq.close()

    # Test 2: IDs preserved exactly
    def test_02_ids_preserved(self):
        pg = self.get_pg()
        sq = self.get_sqlite()
        for table in TABLES:
            sq_cur = sq.cursor()
            sq_cur.execute(f"SELECT id FROM {table} ORDER BY id")
            sq_ids = [r[0] for r in sq_cur.fetchall()]

            pg_cur = pg.cursor()
            pg_cur.execute(f"SELECT id FROM {table} ORDER BY id")
            pg_ids = [r[0] for r in pg_cur.fetchall()]

            self.assertEqual(sq_ids, pg_ids, f"{table}: ID lists differ")
        pg.close()
        sq.close()

    # Test 3: Data checksums match
    def test_03_data_checksums(self):
        pg = self.get_pg()
        sq = self.get_sqlite()
        for table in TABLES:
            cols = ", ".join(COLUMNS[table])

            sq_cur = sq.cursor()
            sq_cur.execute(f"SELECT {cols} FROM {table} ORDER BY id")
            sq_rows = [tuple(r) for r in sq_cur.fetchall()]

            pg_cur = pg.cursor()
            pg_cur.execute(f"SELECT {cols} FROM {table} ORDER BY id")
            pg_rows = pg_cur.fetchall()

            self.assertEqual(
                checksum_rows(sq_rows),
                checksum_rows(pg_rows),
                f"{table}: checksum mismatch",
            )
        pg.close()
        sq.close()

    # Test 4: No foreign-key orphans in PostgreSQL
    def test_04_no_fk_orphans(self):
        fk_checks = [
            ("campaigns", "promo_code_id", "promo_codes", "id"),
            ("requests", "campaign_id", "campaigns", "id"),
            ("requests", "user_id", "users", "id"),
        ]
        pg = self.get_pg()
        pg_cur = pg.cursor()
        for child, child_col, parent, parent_col in fk_checks:
            pg_cur.execute(f"""
                SELECT COUNT(*) FROM {child} c
                LEFT JOIN {parent} p ON c.{child_col} = p.{parent_col}
                WHERE p.{parent_col} IS NULL
            """)
            orphans = pg_cur.fetchone()[0]
            self.assertEqual(orphans, 0, f"{child}.{child_col} has {orphans} orphans")
        pg.close()

    # Test 5: Identity sequences synchronized
    def test_05_sequences_synchronized(self):
        pg = self.get_pg()
        pg_cur = pg.cursor()
        for table in TABLES:
            seq_name = f"{table}_id_seq"
            pg_cur.execute(f"SELECT MAX(id) FROM {table}")
            max_id = pg_cur.fetchone()[0]
            if max_id is not None:
                pg_cur.execute(f"SELECT last_value FROM {seq_name}")
                last_val = pg_cur.fetchone()[0]
                self.assertGreaterEqual(last_val, max_id,
                    f"{seq_name}: last_value={last_val} < MAX(id)={max_id}")
        pg.close()

    # Test 6: SQLite database.db still has 19 users
    def test_06_sqlite_unchanged(self):
        self.assertTrue(SQLITE_DB.exists())
        sq = self.get_sqlite()
        cur = sq.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        self.assertEqual(cur.fetchone()[0], 19)
        sq.close()

    # Test 7: Application still uses SQLite
    def test_07_app_uses_sqlite(self):
        db_py = ROOT_DIR / "database.py"
        content = db_py.read_text(encoding="utf-8")
        self.assertIn("import sqlite3", content)
        self.assertNotIn("import psycopg", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
