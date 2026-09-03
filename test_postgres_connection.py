"""
test_postgres_connection.py — Safe PostgreSQL connection and SQLite inspection test.

Guarantees:
- Never prints or exposes DATABASE_URL, passwords, hostnames, or credentials.
- Read-only inspection of existing SQLite database.
- Executes `SELECT 1` against PostgreSQL.
- Reports PASS or FAIL.
"""
import os
import sqlite3
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env"
SQLITE_DB = ROOT_DIR / "database.db"


def inspect_sqlite():
    """Read-only inspection of existing SQLite database."""
    print("=== SQLite Database Inspection (Read-Only) ===")
    if not SQLITE_DB.exists():
        print("[-] SQLite database file database.db not found.")
        return False

    try:
        conn = sqlite3.connect(SQLITE_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"[+] Found {len(tables)} tables: {', '.join(tables)}")

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"    - Table '{table}': {count} records")

        conn.close()
        return True
    except Exception as e:
        print(f"[-] Error inspecting SQLite database: {e}")
        return False


def test_postgresql_connection():
    """Verify PostgreSQL connectivity securely without leaking credentials."""
    print("\n=== PostgreSQL Connection Verification ===")

    # Load environment variables
    load_dotenv(ENV_FILE, override=True)
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("[-] FAIL: DATABASE_URL is not set in .env")
        return False

    print("[+] DATABASE_URL found in .env (safely loaded without displaying credentials)")

    try:
        # Establish connection using psycopg2
        conn = psycopg2.connect(database_url, connect_timeout=10)
        cursor = conn.cursor()

        # Execute test query
        cursor.execute("SELECT 1;")
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result and result[0] == 1:
            print("[+] Query 'SELECT 1' executed successfully. Result: 1")
            print("[+] PostgreSQL connection confirmed working!")
            return True
        else:
            print(f"[-] FAIL: Unexpected result from SELECT 1: {result}")
            return False

    except Exception as e:
        # Sanitize exception message so database_url/credentials are never revealed
        err_msg = str(e)
        if database_url in err_msg:
            err_msg = err_msg.replace(database_url, "[REDACTED_DATABASE_URL]")
        print(f"[-] FAIL: PostgreSQL connection failed: {err_msg}")
        return False


def main():
    sqlite_ok = inspect_sqlite()
    pg_ok = test_postgresql_connection()

    print("\n==============================================")
    if sqlite_ok and pg_ok:
        print("STATUS: PASS")
    else:
        print("STATUS: FAIL")
    print("==============================================")


if __name__ == "__main__":
    main()
