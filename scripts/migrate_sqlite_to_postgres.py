"""
migrate_sqlite_to_postgres.py — Safe one-time data migration from SQLite to PostgreSQL.

Reads SQLite database.db (read-only) and inserts all rows into PostgreSQL
preserving original primary-key IDs. Synchronizes identity sequences afterward.

Safety:
- Single PostgreSQL transaction; rolls back on any error.
- Verifies PostgreSQL tables are empty before inserting.
- Never modifies SQLite.
- Never prints DATABASE_URL or credentials.
"""
import os
import sys
import sqlite3
import hashlib
from pathlib import Path
from dotenv import load_dotenv
import psycopg

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
SQLITE_DB = ROOT_DIR / "database.db"

TABLES_IN_ORDER = ["users", "promo_codes", "campaigns", "requests"]

COLUMNS = {
    "users": ["id", "telegram_user_id", "username", "first_name", "created_at"],
    "promo_codes": ["id", "code", "description", "instructions", "requirements",
                     "example_image", "active", "created_at"],
    "campaigns": ["id", "promo_code_id", "max_requests", "status", "created_at", "closed_at"],
    "requests": ["id", "campaign_id", "user_id", "site_id", "screenshot_file_id",
                  "status", "created_at", "reviewed_at"],
}


def get_sqlite_data():
    """Read all rows from SQLite (read-only)."""
    conn = sqlite3.connect(f"file:{SQLITE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    data = {}
    for table in TABLES_IN_ORDER:
        cols = ", ".join(COLUMNS[table])
        cur = conn.cursor()
        cur.execute(f"SELECT {cols} FROM {table} ORDER BY id")
        rows = [tuple(row) for row in cur.fetchall()]
        data[table] = rows
    conn.close()
    return data


def checksum_rows(rows):
    """Compute a deterministic checksum for a list of row tuples."""
    h = hashlib.sha256()
    for row in rows:
        h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


def main():
    print("=== SQLite -> PostgreSQL Migration ===")

    # Load env
    load_dotenv(ENV_FILE, override=True)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[-] FAIL: DATABASE_URL not set in .env")
        return False

    print("[+] DATABASE_URL loaded (credentials hidden).")

    # Step 1: Read SQLite
    if not SQLITE_DB.exists():
        print("[-] FAIL: database.db not found.")
        return False

    sqlite_data = get_sqlite_data()
    for table in TABLES_IN_ORDER:
        print(f"[+] SQLite {table}: {len(sqlite_data[table])} rows")

    # Step 2-5: Connect to PG, verify empty, insert, sync sequences
    try:
        with psycopg.connect(database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                # Step 2: Verify PostgreSQL tables are empty
                print("\n--- Pre-migration emptiness check ---")
                for table in TABLES_IN_ORDER:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    if count != 0:
                        print(f"[-] FAIL: PostgreSQL '{table}' is NOT empty ({count} rows). STOPPING.")
                        conn.rollback()
                        return False
                    print(f"[+] PostgreSQL {table}: 0 rows (OK)")

                # Step 3: Insert rows preserving IDs
                print("\n--- Inserting rows ---")
                for table in TABLES_IN_ORDER:
                    rows = sqlite_data[table]
                    if not rows:
                        print(f"[+] {table}: 0 rows (nothing to insert)")
                        continue

                    cols = COLUMNS[table]
                    col_list = ", ".join(cols)
                    placeholders = ", ".join(["%s"] * len(cols))
                    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

                    for row in rows:
                        cur.execute(sql, row)

                    print(f"[+] {table}: {len(rows)} rows inserted")

                # Step 4: Verify counts match
                print("\n--- Post-insertion count verification ---")
                for table in TABLES_IN_ORDER:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    pg_count = cur.fetchone()[0]
                    sq_count = len(sqlite_data[table])
                    status = "OK" if pg_count == sq_count else "MISMATCH"
                    print(f"[+] {table}: SQLite={sq_count}, PostgreSQL={pg_count} [{status}]")
                    if pg_count != sq_count:
                        print(f"[-] FAIL: Count mismatch on {table}. Rolling back.")
                        conn.rollback()
                        return False

                # Step 4b: Verify data checksums
                print("\n--- Checksum verification ---")
                for table in TABLES_IN_ORDER:
                    cols = ", ".join(COLUMNS[table])
                    cur.execute(f"SELECT {cols} FROM {table} ORDER BY id")
                    pg_rows = cur.fetchall()
                    sq_checksum = checksum_rows(sqlite_data[table])
                    pg_checksum = checksum_rows(pg_rows)
                    status = "MATCH" if sq_checksum == pg_checksum else "MISMATCH"
                    print(f"[+] {table}: {status}")
                    if sq_checksum != pg_checksum:
                        print(f"[-] FAIL: Checksum mismatch on {table}. Rolling back.")
                        conn.rollback()
                        return False

                # Step 4c: Verify no foreign-key orphans
                print("\n--- Foreign-key orphan check ---")
                fk_checks = [
                    ("campaigns", "promo_code_id", "promo_codes", "id"),
                    ("requests", "campaign_id", "campaigns", "id"),
                    ("requests", "user_id", "users", "id"),
                ]
                for child, child_col, parent, parent_col in fk_checks:
                    cur.execute(f"""
                        SELECT COUNT(*) FROM {child} c
                        LEFT JOIN {parent} p ON c.{child_col} = p.{parent_col}
                        WHERE p.{parent_col} IS NULL
                    """)
                    orphans = cur.fetchone()[0]
                    status = "OK" if orphans == 0 else f"ORPHANS={orphans}"
                    print(f"[+] {child}.{child_col} -> {parent}.{parent_col}: {status}")
                    if orphans > 0:
                        print(f"[-] FAIL: Foreign-key orphans found. Rolling back.")
                        conn.rollback()
                        return False

                # Step 5: Synchronize identity sequences
                print("\n--- Sequence synchronization ---")
                for table in TABLES_IN_ORDER:
                    seq_name = f"{table}_id_seq"
                    cur.execute(f"SELECT MAX(id) FROM {table}")
                    max_id = cur.fetchone()[0]
                    if max_id is not None:
                        cur.execute(f"SELECT setval('{seq_name}', %s)", (max_id,))
                        new_val = cur.fetchone()[0]
                        print(f"[+] {seq_name} set to {new_val}")
                    else:
                        print(f"[+] {seq_name}: no rows, sequence unchanged")

            # Commit the entire transaction
            conn.commit()
            print("\n[+] Transaction COMMITTED successfully.")
            return True

    except Exception as e:
        err_msg = str(e)
        if database_url in err_msg:
            err_msg = err_msg.replace(database_url, "[REDACTED]")
        print(f"[-] FAIL: {err_msg}")
        return False


if __name__ == "__main__":
    success = main()
    print(f"\n{'='*50}")
    print(f"STATUS: {'PASS' if success else 'FAIL'}")
    print(f"{'='*50}")
    sys.exit(0 if success else 1)
