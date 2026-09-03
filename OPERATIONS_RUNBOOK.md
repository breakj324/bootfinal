# OPERATIONAL & DISASTER RECOVERY RUNBOOK

## 1. System Overview
- **Production Database**: Neon PostgreSQL (Serverless PostgreSQL 16) via `DATABASE_URL`
- **Application Services**:
  - Telegram Customer Bot (`bot.py`)
  - Telegram Admin Bot (`admin_bot.py`)
  - FastAPI Admin API Backend (`backend/main.py`)
  - React/Vite Admin Dashboard (`dashboard/dist`)
- **Historical Backup**: `database.db` (SQLite source of truth from Phase 23, preserved with 19 users).

---

## 2. Environment Configuration
The following environment variables must be configured in `.env` (kept strictly confidential):
- `DATABASE_URL`: Connection string for Neon PostgreSQL (psycopg3 compatible).
- `BOT_TOKEN`: Telegram bot token from @BotFather.
- `ADMIN_TELEGRAM_ID`: Numeric Telegram ID of primary administrator.
- `ADMIN_USERNAME`: Admin dashboard login username (default: `admin`).
- `ADMIN_PASSWORD`: Admin dashboard login password.
- `JWT_SECRET`: Secret key for signing JWT tokens.
- `DASHBOARD_ORIGIN`: Allowed CORS origin (e.g. `http://localhost:5173`).
- `VITE_API_BASE_URL`: Frontend environment variable pointing to FastAPI backend URL.

---

## 3. Service Operations

### Starting FastAPI Backend
```bash
.\venv\Scripts\uvicorn.exe backend.main:app --host 0.0.0.0 --port 8000
```
- Health Check: `GET /api/health` -> `{"status": "ok"}`

### Starting Telegram Bot
```bash
.\venv\Scripts\python.exe bot.py
```

### Building Dashboard for Production
```bash
cd dashboard
npm run build
```

---

## 4. Disaster Recovery & Rollback Procedures

### A. Application Rollback
- Revert code using Git tags or releases.
- No database downgrades are required unless schema changes were introduced.

### B. Database Protection Policy
- **Authoritative Source**: Neon PostgreSQL is the sole active production database.
- **Historical Backup**: `database.db` must NEVER be deleted or modified automatically.
- Never downgrade PostgreSQL runtime back to SQLite in production.

### C. Neon Cloud Recovery (Point-in-Time Recovery)
1. Log in to [Neon Console](https://console.neon.tech).
2. Navigate to the production project and branch.
3. If point-in-time recovery is required due to data corruption or accidental deletion, use Neon's branching / PITR feature to restore the state from a prior timestamp.
4. Update `DATABASE_URL` in `.env` if restoring to a new branch.
5. Restart services.

### D. Emergency Incident Protocol
1. **Stop Writes**: If an active defect is corrupting data, terminate `bot.py` and `backend.main:app`.
2. **Preserve Logs**: Capture terminal and application logs before restarting.
3. **Audit State**: Execute read-only diagnostics to assess affected tables.
4. **Restore**: Recover PostgreSQL using Neon PITR or designated branch backup.
5. **Verify**: Run `PRAGMA integrity_check` on local backups and verify PostgreSQL table counts.
6. **Resume**: Restart services cleanly and verify `/api/health`.

---

## 5. Monitoring & Observability Guide

### A. Health & Connectivity Verification
- **API Health Check**: `GET /api/health`
  - Returns `{"status": "ok"}` (HTTP 200) when application and PostgreSQL are operational.
  - Returns `{"status": "degraded", "database": "unavailable"}` (HTTP 503) if PostgreSQL connectivity is lost.
- **PostgreSQL Direct Check**:
  - Run `check_database_health()` from `database.py` for a bounded `SELECT 1` ping.

### B. Application Logging & Request Timing
- Standard logging formats timestamp, module name, log level, and message.
- HTTP requests are monitored via timing middleware emitting method, path, status, and duration (e.g. `GET /api/dashboard/stats -> 200 (12.40ms)`).
- `X-Response-Time` header is returned on all API responses.

### C. Operational Troubleshooting Runbook
1. **If PostgreSQL is unavailable**:
   - Check Neon Console for compute endpoint state / branch status.
   - Verify connection string and firewall/network access.
   - Health check will surface HTTP 503 automatically.
2. **If Telegram Bot stops polling**:
   - Check `bot.log` / process console for unhandled exceptions.
   - Global error handler catches handler exceptions without terminating polling loop.
   - If network timeout occurs, bot auto-retries via `telegram.ext`.
3. **If API latency increases**:
   - Check `X-Response-Time` header on responses.
   - Check Neon compute active state and pool size in `database.py`.
   - Inspect PostgreSQL query execution plans.
4. **Neon PITR Reminder**:
   - Automated cloud point-in-time recovery and branch backups must be monitored via the Neon Console.
