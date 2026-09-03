"""
test_phase21.py — Complete test suite for Phase 21: Connecting Dashboard to Real API.

Verifies end-to-end API communication, UI service layer, data integrity,
and prevents regressions across all previous phases.
"""
import os
import unittest
from pathlib import Path
from starlette.testclient import TestClient

import config
from database import (
    initialize_database,
    create_or_update_user,
    delete_user_by_telegram_id,
    create_promo_code,
    delete_promo_code,
    create_campaign,
    activate_campaign,
    close_campaign,
    create_request,
    delete_campaign,
    get_request_by_id,
    get_connection,
)
from backend.main import app

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
SRC_DIR = DASHBOARD_DIR / "src"


class TestPhase21DashboardAPIIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        initialize_database()
        cls.client = TestClient(app)

        # Login to obtain real JWT
        res = cls.client.post(
            "/api/auth/login",
            json={"username": config.ADMIN_USERNAME, "password": config.ADMIN_PASSWORD},
        )
        assert res.status_code == 200, "Setup login failed"
        cls.token = res.json()["token"]
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

    def setUp(self):
        self.test_code = "MRC456P21"
        self.cleanup_camps = []
        self.cleanup_tg_ids = []

        delete_promo_code(self.test_code)
        self.promo_id = create_promo_code(
            code=self.test_code,
            description="Phase 21 integration test",
            instructions="Test",
            requirements="Test",
        )

        self.camp_id = create_campaign(promo_code=self.promo_id, max_requests=10)
        activate_campaign(self.camp_id)
        self.cleanup_camps.append(self.camp_id)

        self.cust_tg_id = 99210001
        self.cleanup_tg_ids.append(self.cust_tg_id)
        self.cust_db_id = create_or_update_user(
            telegram_user_id=self.cust_tg_id,
            username="p21_user",
            first_name="P21FirstName",
        )

    def tearDown(self):
        for cid in self.cleanup_camps:
            try:
                with get_connection() as conn:
                    conn.execute("DELETE FROM requests WHERE campaign_id = ?", (cid,))
                    conn.commit()
                delete_campaign(cid)
            except Exception:
                pass

        for tid in self.cleanup_tg_ids:
            try:
                delete_user_by_telegram_id(tid)
            except Exception:
                pass

        delete_promo_code(self.test_code)

    # ── Test 1, 2, 3: Real Login & Invalid Credentials ─────────
    def test_01_02_03_auth_flow(self):
        """Verify real login, rejection of invalid creds, and JWT reception."""
        # 1. Invalid login
        bad_res = self.client.post(
            "/api/auth/login",
            json={"username": "wrong_user", "password": "wrong_password"},
        )
        self.assertEqual(bad_res.status_code, 401)

        # 2. Valid login
        good_res = self.client.post(
            "/api/auth/login",
            json={"username": config.ADMIN_USERNAME, "password": config.ADMIN_PASSWORD},
        )
        self.assertEqual(good_res.status_code, 200)
        data = good_res.json()
        self.assertIn("token", data)
        self.assertEqual(data["username"], config.ADMIN_USERNAME)

    # ── Test 4 & 5: Overview Stats & Active Campaign ────────────
    def test_04_05_overview_real_data(self):
        """Overview endpoints return real database stats and active campaign."""
        # Stats
        stats_res = self.client.get("/api/dashboard/stats", headers=self.auth_headers)
        self.assertEqual(stats_res.status_code, 200)
        stats = stats_res.json()
        self.assertGreaterEqual(stats["total_promo_codes"], 1)
        self.assertGreaterEqual(stats["active_campaigns"], 1)

        # Active Campaign
        camp_res = self.client.get("/api/dashboard/active-campaign", headers=self.auth_headers)
        self.assertEqual(camp_res.status_code, 200)
        camp = camp_res.json()
        self.assertIsNotNone(camp)
        self.assertEqual(camp["status"], "active")
        self.assertIn("remaining_slots", camp)

    # ── Test 6: Promo Codes Real Data ───────────────────────────
    def test_06_promo_codes_real_data(self):
        """GET /api/promo-codes returns list with created promo code."""
        res = self.client.get("/api/promo-codes", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        promos = res.json()
        codes = [p["code"] for p in promos]
        self.assertIn(self.test_code, codes)

    # ── Test 7 & 8: Campaigns Real Data & Pagination ────────────
    def test_07_08_campaigns_real_data_and_pagination(self):
        """Campaigns endpoint returns real campaigns and supports offset/limit."""
        res = self.client.get("/api/campaigns?limit=5&offset=0", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        camps = res.json()
        self.assertLessEqual(len(camps), 5)
        camp_ids = [c["id"] for c in camps]
        self.assertIn(self.camp_id, camp_ids)

    # ── Test 9 & 10: Pending Requests & Request Details ─────────
    def test_09_10_pending_requests_and_details(self):
        """Pending requests list and detail endpoints return correct data."""
        req_id = create_request(
            self.camp_id,
            self.cust_db_id,
            site_id="SITE21_TEST",
            screenshot_file_id="photo_p21",
            status="pending",
        )

        # List
        list_res = self.client.get("/api/requests/pending", headers=self.auth_headers)
        self.assertEqual(list_res.status_code, 200)
        req_ids = [r["id"] for r in list_res.json()]
        self.assertIn(req_id, req_ids)

        # Detail
        detail_res = self.client.get(f"/api/requests/{req_id}", headers=self.auth_headers)
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.json()
        self.assertEqual(detail["id"], req_id)
        self.assertEqual(detail["promo_code"], self.test_code)
        self.assertEqual(detail["site_id"], "SITE21_TEST")
        self.assertTrue(detail["has_screenshot"])

    # ── Test 11, 12, 13: Customers Directory, Search, Pagination 
    def test_11_12_13_customers_search_pagination(self):
        """Customer directory returns real data, filters by search, and paginates."""
        # Directory
        res = self.client.get("/api/customers?page=1&limit=10", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("customers", data)
        self.assertGreaterEqual(data["total"], 1)

        # Search
        search_res = self.client.get(
            "/api/customers?search=p21_user", headers=self.auth_headers
        )
        self.assertEqual(search_res.status_code, 200)
        search_data = search_res.json()
        self.assertEqual(search_data["total"], 1)
        self.assertEqual(search_data["customers"][0]["username"], "p21_user")

    # ── Test 14 & 16: Accept Action & Disappearance from Pending
    def test_14_16_accept_action_removes_from_pending(self):
        """Accepting a request marks it accepted and removes it from pending queue."""
        req_id = create_request(
            self.camp_id, self.cust_db_id, site_id="S21_ACC", status="pending"
        )
        # Accept via API
        res = self.client.post(f"/api/requests/{req_id}/accept", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "accepted")

        # Verify disappears from pending
        pending_res = self.client.get("/api/requests/pending", headers=self.auth_headers)
        pending_ids = [r["id"] for r in pending_res.json()]
        self.assertNotIn(req_id, pending_ids)

    # ── Test 15: Reject Action ──────────────────────────────────
    def test_15_reject_action(self):
        """Rejecting a request marks it rejected via API."""
        req_id = create_request(
            self.camp_id, self.cust_db_id, site_id="S21_REJ", status="pending"
        )
        res = self.client.post(f"/api/requests/{req_id}/reject", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "rejected")

        # Verify DB
        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "rejected")

    # ── Test 17: 409 Conflict on Double Review ──────────────────
    def test_17_conflict_409_on_double_review(self):
        """Reviewing an already processed request returns 409 Conflict."""
        req_id = create_request(
            self.camp_id, self.cust_db_id, site_id="S21_CONF", status="pending"
        )
        res1 = self.client.post(f"/api/requests/{req_id}/accept", headers=self.auth_headers)
        self.assertEqual(res1.status_code, 200)

        res2 = self.client.post(f"/api/requests/{req_id}/accept", headers=self.auth_headers)
        self.assertEqual(res2.status_code, 409)

    # ── Test 18: 401 Unauthorized Handling ──────────────────────
    def test_18_unauthorized_returns_401(self):
        """Requests with missing or invalid tokens return 401."""
        res_no_auth = self.client.get("/api/dashboard/stats")
        self.assertEqual(res_no_auth.status_code, 401)

        res_bad_auth = self.client.get(
            "/api/dashboard/stats", headers={"Authorization": "Bearer invalidtoken123"}
        )
        self.assertEqual(res_bad_auth.status_code, 401)

    # ── Test 19: No Mock Data in API Service Layer ──────────────
    def test_19_no_mock_data_in_api_service(self):
        """api.js must not define mock data dictionaries for active endpoints."""
        api_file = SRC_DIR / "services" / "api.js"
        content = api_file.read_text(encoding="utf-8")

        self.assertNotIn("const MOCK =", content)
        self.assertIn("export async function getDashboardStats", content)
        self.assertIn("export async function getActiveCampaign", content)
        self.assertIn("export async function getPromoCodes", content)
        self.assertIn("export async function getCampaigns", content)
        self.assertIn("export async function getPendingRequests", content)
        self.assertIn("export async function getRequest", content)
        self.assertIn("export async function getCustomers", content)
        self.assertIn("export async function acceptRequest", content)
        self.assertIn("export async function rejectRequest", content)

    # ── Test 20: No Secrets in Frontend Source ──────────────────
    def test_20_no_secrets_in_frontend(self):
        """Frontend files must not contain BOT_TOKEN or ADMIN_TELEGRAM_ID."""
        bot_token = config.BOT_TOKEN
        admin_id_str = str(config.ADMIN_TELEGRAM_ID) if config.ADMIN_TELEGRAM_ID else ""

        for root, _, files in os.walk(DASHBOARD_DIR):
            if "node_modules" in root or "dist" in root:
                continue
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in [".js", ".jsx", ".ts", ".tsx", ".html", ".env"]:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    if bot_token and len(bot_token) > 5:
                        self.assertNotIn(
                            bot_token,
                            content,
                            f"BOT_TOKEN exposed in {file_path.name}",
                        )
                    if admin_id_str and len(admin_id_str) > 4:
                        if file_path.suffix in [".js", ".jsx"]:
                            self.assertNotIn(
                                admin_id_str,
                                content,
                                f"ADMIN_TELEGRAM_ID in {file_path.name}",
                            )

    # ── Test 21: Frontend Build Output ──────────────────────────
    def test_21_frontend_build_artifacts(self):
        """dist/ folder must exist and contain index.html and assets."""
        dist_dir = DASHBOARD_DIR / "dist"
        self.assertTrue(dist_dir.exists(), "dist/ directory must exist from build")
        self.assertTrue((dist_dir / "index.html").exists(), "dist/index.html must exist")


if __name__ == "__main__":
    unittest.main(verbosity=2)
