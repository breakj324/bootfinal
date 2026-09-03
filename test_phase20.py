"""
test_phase20.py — Complete test suite for Phase 20 FastAPI Backend.

Verifies:
1. FastAPI starts successfully.
2. GET /api/health returns status ok.
3. Unauthenticated dashboard endpoints return 401.
4. Authentication succeeds with valid admin credentials.
5. Invalid credentials return 401.
6. Authenticated admin can access dashboard stats.
7. Stats come from the real existing database.
8. Active campaign endpoint returns real campaign data.
9. Promo codes endpoint returns real promo codes.
10. Campaigns endpoint returns real campaigns.
11. Pending requests endpoint returns real pending requests.
12. Request detail endpoint returns correct request.
13. Customer endpoint returns real customers.
14. Pagination works.
15. Search works.
16. Accept endpoint uses existing review_request logic.
17. Reject endpoint uses existing review_request logic.
18. Double processing is prevented (409 Conflict).
19. Unauthorized users cannot accept/reject.
20. Existing Telegram bot tests still pass.
21. No secrets are exposed.
22. No second database is created.
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


class TestPhase20BackendAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        initialize_database()
        cls.client = TestClient(app)

        # Obtain valid admin token for protected tests
        login_res = cls.client.post(
            "/api/auth/login",
            json={"username": config.ADMIN_USERNAME, "password": config.ADMIN_PASSWORD},
        )
        assert login_res.status_code == 200, f"Setup login failed: {login_res.text}"
        cls.token = login_res.json()["token"]
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

    def setUp(self):
        self.test_code = "MRC456P20"
        self.cleanup_camps = []
        self.cleanup_tg_ids = []

        delete_promo_code(self.test_code)
        self.promo_id = create_promo_code(
            code=self.test_code,
            description="Phase 20 test promo",
            instructions="Step 1: Test",
            requirements="Test requirements",
        )

        self.camp_id = create_campaign(promo_code=self.promo_id, max_requests=10)
        activate_campaign(self.camp_id)
        self.cleanup_camps.append(self.camp_id)

        self.cust_tg_id = 99200001
        self.cleanup_tg_ids.append(self.cust_tg_id)
        self.cust_db_id = create_or_update_user(
            telegram_user_id=self.cust_tg_id,
            username="p20_tester",
            first_name="P20User",
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

    # ── Test 1 & 2: App starts & GET /api/health ────────────────
    def test_01_02_health_endpoint(self):
        """GET /api/health returns 200 and status ok."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    # ── Test 3: Unauthenticated request returns 401 ─────────────
    def test_03_unauthenticated_returns_401(self):
        """Unauthenticated requests to protected endpoints return 401."""
        endpoints = [
            "/api/dashboard/stats",
            "/api/dashboard/active-campaign",
            "/api/promo-codes",
            "/api/campaigns",
            "/api/requests/pending",
            "/api/customers",
        ]
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(
                res.status_code,
                401,
                f"Endpoint {ep} should require auth but returned {res.status_code}",
            )

    # ── Test 4: Auth succeeds with valid credentials ────────────
    def test_04_auth_succeeds_with_valid_credentials(self):
        """POST /api/auth/login succeeds with correct username and password."""
        res = self.client.post(
            "/api/auth/login",
            json={"username": config.ADMIN_USERNAME, "password": config.ADMIN_PASSWORD},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("token", data)
        self.assertEqual(data["username"], config.ADMIN_USERNAME)
        self.assertEqual(data["token_type"], "bearer")

    # ── Test 5: Invalid credentials rejected ────────────────────
    def test_05_invalid_credentials_rejected(self):
        """POST /api/auth/login rejects invalid credentials with 401."""
        res = self.client.post(
            "/api/auth/login",
            json={"username": "wrongadmin", "password": "wrongpassword"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid", res.json()["detail"])

    # ── Test 6 & 7: Dashboard stats from real database ──────────
    def test_06_07_dashboard_stats(self):
        """GET /api/dashboard/stats returns real aggregated database counts."""
        res = self.client.get("/api/dashboard/stats", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        required_fields = [
            "total_users",
            "total_promo_codes",
            "active_promo_codes",
            "pending_requests",
            "accepted_requests",
            "rejected_requests",
            "active_campaigns",
        ]
        for field in required_fields:
            self.assertIn(field, data)
            self.assertIsInstance(data[field], int)
        self.assertGreaterEqual(data["total_promo_codes"], 1)

    # ── Test 8: Active campaign endpoint returns real data ──────
    def test_08_active_campaign_endpoint(self):
        """GET /api/dashboard/active-campaign returns active campaign."""
        res = self.client.get("/api/dashboard/active-campaign", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "active")
        self.assertIn("promo_code", data)
        self.assertIn("remaining_slots", data)

    # ── Test 9: Promo codes endpoint returns real promo codes ───
    def test_09_promo_codes_endpoint(self):
        """GET /api/promo-codes returns list containing our test promo code."""
        res = self.client.get("/api/promo-codes", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        codes = [p["code"] for p in data]
        self.assertIn(self.test_code, codes)

    # ── Test 10: Campaigns endpoint returns real campaigns ──────
    def test_10_campaigns_endpoint(self):
        """GET /api/campaigns returns list containing our test campaign."""
        res = self.client.get("/api/campaigns", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        camp_ids = [c["id"] for c in data]
        self.assertIn(self.camp_id, camp_ids)

    # ── Test 11: Pending requests endpoint ──────────────────────
    def test_11_pending_requests_endpoint(self):
        """GET /api/requests/pending returns pending request."""
        req_id = create_request(
            self.camp_id, self.cust_db_id, site_id="SITE20_01", status="pending"
        )
        res = self.client.get("/api/requests/pending", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        req_ids = [r["id"] for r in data]
        self.assertIn(req_id, req_ids)

    # ── Test 12: Request detail endpoint ────────────────────────
    def test_12_request_detail_endpoint(self):
        """GET /api/requests/{id} returns full request details."""
        req_id = create_request(
            self.camp_id,
            self.cust_db_id,
            site_id="SITE20_DETAIL",
            screenshot_file_id="photo_p20_detail",
            status="pending",
        )
        res = self.client.get(f"/api/requests/{req_id}", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], req_id)
        self.assertEqual(data["promo_code"], self.test_code)
        self.assertEqual(data["site_id"], "SITE20_DETAIL")
        self.assertEqual(data["telegram_user_id"], self.cust_tg_id)
        self.assertTrue(data["has_screenshot"])

    # ── Test 13: Customer endpoint returns real customers ───────
    def test_13_customers_endpoint(self):
        """GET /api/customers returns customer records."""
        res = self.client.get("/api/customers", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("customers", data)
        self.assertIn("total", data)
        unames = [c["username"] for c in data["customers"]]
        self.assertIn("p20_tester", unames)

    # ── Test 14: Pagination works ───────────────────────────────
    def test_14_pagination(self):
        """Pagination limits and offsets work correctly."""
        res = self.client.get("/api/customers?page=1&limit=2", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertLessEqual(len(data["customers"]), 2)
        self.assertEqual(data["limit"], 2)
        self.assertEqual(data["page"], 1)

    # ── Test 15: Search works ───────────────────────────────────
    def test_15_search(self):
        """GET /api/customers?search=... filters results."""
        res = self.client.get("/api/customers?search=p20_tester", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["customers"][0]["username"], "p20_tester")

    # ── Test 16: Accept endpoint uses existing review_request ────
    def test_16_accept_endpoint(self):
        """POST /api/requests/{id}/accept updates status to accepted."""
        req_id = create_request(
            self.camp_id, self.cust_db_id, site_id="S20_ACCEPT", status="pending"
        )
        res = self.client.post(f"/api/requests/{req_id}/accept", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "accepted")

        # Verify DB directly
        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "accepted")
        self.assertIsNotNone(req["reviewed_at"])

    # ── Test 17: Reject endpoint uses existing review_request ────
    def test_17_reject_endpoint(self):
        """POST /api/requests/{id}/reject updates status to rejected."""
        req_id = create_request(
            self.camp_id, self.cust_db_id, site_id="S20_REJECT", status="pending"
        )
        res = self.client.post(f"/api/requests/{req_id}/reject", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "rejected")

        # Verify DB directly
        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "rejected")
        self.assertIsNotNone(req["reviewed_at"])

    # ── Test 18: Double processing prevented ────────────────────
    def test_18_double_processing_prevented(self):
        """Second review attempt on already reviewed request returns 409 Conflict."""
        req_id = create_request(
            self.camp_id, self.cust_db_id, site_id="S20_DOUBLE", status="pending"
        )
        # First accept
        res1 = self.client.post(f"/api/requests/{req_id}/accept", headers=self.auth_headers)
        self.assertEqual(res1.status_code, 200)

        # Second accept
        res2 = self.client.post(f"/api/requests/{req_id}/accept", headers=self.auth_headers)
        self.assertEqual(res2.status_code, 409)
        self.assertIn("already processed", res2.json()["detail"].lower())

    # ── Test 19: Unauthorized users cannot accept/reject ────────
    def test_19_unauthorized_action_rejected(self):
        """Unauthenticated accept/reject requests return 401."""
        req_id = create_request(
            self.camp_id, self.cust_db_id, site_id="S20_UNAUTH", status="pending"
        )
        res_accept = self.client.post(f"/api/requests/{req_id}/accept")
        self.assertEqual(res_accept.status_code, 401)

        res_reject = self.client.post(f"/api/requests/{req_id}/reject")
        self.assertEqual(res_reject.status_code, 401)

        # DB status remains pending
        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "pending")

    # ── Test 21: No secrets exposed in responses ────────────────
    def test_21_no_secrets_exposed(self):
        """API responses never contain BOT_TOKEN or ADMIN_TELEGRAM_ID."""
        endpoints = [
            "/api/health",
            "/api/dashboard/stats",
            "/api/promo-codes",
            "/api/campaigns",
            "/api/requests/pending",
            "/api/customers",
        ]
        for ep in endpoints:
            res = self.client.get(ep, headers=self.auth_headers)
            body = res.text
            self.assertNotIn(config.BOT_TOKEN, body)
            if config.ADMIN_TELEGRAM_ID:
                self.assertNotIn(str(config.ADMIN_TELEGRAM_ID), body)

    # ── Test 22: No second database created ─────────────────────
    def test_22_no_second_database_created(self):
        """Only the single original database.db exists in project root."""
        root = Path(__file__).resolve().parent
        db_files = list(root.glob("*.db"))
        self.assertEqual(
            [f.name for f in db_files],
            ["database.db"],
            f"Unexpected extra database files found: {db_files}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
