import os
from pathlib import Path
from dotenv import load_dotenv

# Explicitly resolve path to .env in project directory
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing from .env")

admin_id_raw = os.getenv("ADMIN_TELEGRAM_ID")
ADMIN_TELEGRAM_ID = int(admin_id_raw.strip()) if admin_id_raw and admin_id_raw.strip().isdigit() else None

# Dashboard / Backend API settings
DASHBOARD_ORIGIN = os.getenv("DASHBOARD_ORIGIN", "http://localhost:5173")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-rewards-admin-token-phase20")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
