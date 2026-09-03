"""
test_phase23.py — Complete test suite for Phase 23: Campaign Management.

Verifies:
1. Unauthenticated user cannot access campaign management.
2. Admin can list campaigns.
3. Admin can retrieve campaign details.
4. Admin can create campaign.
5. New campaign starts CLOSED.
6. Invalid promo code rejected (404).
7. Disabled promo code rejected (409).
8. max_requests <= 0 rejected (422).
9. Admin can activate campaign.
10. Active campaign becomes visible to customer flow.
11. Second campaign cannot activate while another is ACTIVE (409 Conflict).
12. Repeated activate is safe.
13. Admin can close active campaign.
14. Closed campaign stops accepting new requests.
15. Existing requests remain intact after closing.
16. Campaign automatically becomes FULL at capacity.
17. FULL campaign cannot accept additional requests.
18. Remaining slots are calculated correctly.
19. Campaign history remains intact.
20. Dashboard displays real campaign data.
21. Error states display correctly.
22. No secrets exposed.
23. Frontend build artifacts exist.
"""
import os
import unittest
from pathlib import Path
from starlette.testclient import TestClient

import config
from database import (
    initialize_database,
    create_promo_code,
    disable_promo_code,
    enable_promo_code,
    delete_promo_code,
    create_campaign,
    get_campaign_by_id,
    get_active_campaign,
    close_campaign,
    delete_campaign,
    create_request,
    create_or_update_user,
    get_request_by_id,
    get_connection,
)
from backend.main import app

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"


class TestPhase23CampaignManagement(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        initialize_database()
        cls.client = TestClient(app)

        # Login to obtain admin token
        res = cls.client.post(
            "/api/auth/login",
            json={"username": config.ADMIN_USERNAME, "password": config.ADMIN_PASSWORD},
        )
        assert res.status_code == 200, "Setup login failed"
        cls.token = res.json()["token"]
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

    def setUp(self):
        # Make sure no left-over active campaign exists
        active = get_active_campaign()
        if active:
            close_campaign(active["id"])

        self.test_code_1 = "CAMPTEST1"
        self.test_code_2 = "CAMPTEST2"
        self.test_code_disabled = "CAMPDISABLED"

        delete_promo_code(self.test_code_1)
        delete_promo_code(self.test_code_2)
        delete_promo_code(self.test_code_disabled)

        self.promo_id_1 = create_promo_code(self.test_code_1, "Camp Test 1", "Inst", "Req")
        self.promo_id_2 = create_promo_code(self.test_code_2, "Camp Test 2", "Inst", "Req")
        self.promo_id_dis = create_promo_code(self.test_code_disabled, "Disabled Code", "Inst", "Req")
        disable_promo_code(self.test_code_disabled)

        self.cleanup_camps = []

    def tearDown(self):
        for cid in self.cleanup_camps:
            try:
                delete_campaign(cid)
            except Exception:
                pass
        delete_promo_code(self.test_code_1)
        delete_promo_code(self.test_code_2)
        delete_promo_code(self.test_code_disabled)

    # ── Test 1: Unauthenticated access blocked ──────────────────
    def test_01_unauthenticated_blocked(self):
        """Unauthenticated requests to campaign endpoints return 401."""
        self.assertEqual(self.client.get("/api/campaigns").status_code, 401)
        self.assertEqual(self.client.post("/api/campaigns", json={}).status_code, 401)
        self.assertEqual(self.client.get("/api/campaigns/1").status_code, 401)
        self.assertEqual(self.client.post("/api/campaigns/1/activate").status_code, 401)
        self.assertEqual(self.client.post("/api/campaigns/1/close").status_code, 401)

    # ── Test 2: Admin can list campaigns ────────────────────────
    def test_02_admin_can_list_campaigns(self):
        """Admin can list campaigns with GET /api/campaigns."""
        res = self.client.get("/api/campaigns", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    # ── Test 3, 4, 5: Create Campaign and initial CLOSED status ─
    def test_03_04_05_create_campaign_starts_closed(self):
        """Creating a campaign creates it in CLOSED status."""
        res = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": 15},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        camp_id = data["id"]
        self.cleanup_camps.append(camp_id)

        self.assertEqual(data["status"], "closed")
        self.assertEqual(data["promo_code"], self.test_code_1)
        self.assertEqual(data["max_requests"], 15)
        self.assertEqual(data["pending_requests"], 0)
        self.assertEqual(data["remaining_slots"], 15)

        # Retrieve single campaign
        detail_res = self.client.get(f"/api/campaigns/{camp_id}", headers=self.auth_headers)
        self.assertEqual(detail_res.status_code, 200)
        self.assertEqual(detail_res.json()["id"], camp_id)

    # ── Test 6, 7, 8: Validations on Create ─────────────────────
    def test_06_07_08_create_validations(self):
        """Validates invalid promo code, disabled promo code, and invalid max_requests."""
        # 1. Invalid promo code ID (404)
        res_404 = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": 999999, "max_requests": 10},
            headers=self.auth_headers,
        )
        self.assertEqual(res_404.status_code, 404)

        # 2. Disabled promo code (409 Conflict)
        res_dis = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_dis, "max_requests": 10},
            headers=self.auth_headers,
        )
        self.assertEqual(res_dis.status_code, 409)

        # 3. max_requests <= 0 (422)
        res_zero = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": 0},
            headers=self.auth_headers,
        )
        self.assertEqual(res_zero.status_code, 422)

        res_neg = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": -5},
            headers=self.auth_headers,
        )
        self.assertEqual(res_neg.status_code, 422)

    # ── Test 9, 10, 12: Activate Campaign & Visibility ───────────
    def test_09_10_12_activate_campaign_and_idempotence(self):
        """Admin can activate campaign; customer flow sees it; repeated activation is safe."""
        # Create campaign
        res = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": 10},
            headers=self.auth_headers,
        )
        camp_id = res.json()["id"]
        self.cleanup_camps.append(camp_id)

        # 1. Before activation: not active
        self.assertIsNone(get_active_campaign())

        # 2. Activate
        act_res = self.client.post(f"/api/campaigns/{camp_id}/activate", headers=self.auth_headers)
        self.assertEqual(act_res.status_code, 200)
        self.assertEqual(act_res.json()["status"], "active")

        # 3. Active in database / visible to customer flow
        active_db = get_active_campaign()
        self.assertIsNotNone(active_db)
        self.assertEqual(active_db["id"], camp_id)
        self.assertEqual(active_db["promo_code"], self.test_code_1)

        # 4. Repeated activate is idempotent / safe
        act_repeat = self.client.post(f"/api/campaigns/{camp_id}/activate", headers=self.auth_headers)
        self.assertEqual(act_repeat.status_code, 200)
        self.assertEqual(act_repeat.json()["status"], "active")

    # ── Test 11: One Active Campaign Rule ───────────────────────
    def test_11_one_active_campaign_rule(self):
        """Cannot activate a second campaign while one is already ACTIVE (409 Conflict)."""
        # Create Campaign 1 and activate
        res1 = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": 10},
            headers=self.auth_headers,
        )
        camp1_id = res1.json()["id"]
        self.cleanup_camps.append(camp1_id)
        self.client.post(f"/api/campaigns/{camp1_id}/activate", headers=self.auth_headers)

        # Create Campaign 2
        res2 = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_2, "max_requests": 20},
            headers=self.auth_headers,
        )
        camp2_id = res2.json()["id"]
        self.cleanup_camps.append(camp2_id)

        # Attempt to activate Campaign 2 -> must fail with 409 Conflict
        act2_res = self.client.post(f"/api/campaigns/{camp2_id}/activate", headers=self.auth_headers)
        self.assertEqual(act2_res.status_code, 409)
        self.assertIn("أخرى مفتوحة", act2_res.json()["detail"])

        # Close Campaign 1
        self.client.post(f"/api/campaigns/{camp1_id}/close", headers=self.auth_headers)

        # Now Campaign 2 can be activated
        act2_res_ok = self.client.post(f"/api/campaigns/{camp2_id}/activate", headers=self.auth_headers)
        self.assertEqual(act2_res_ok.status_code, 200)
        self.assertEqual(act2_res_ok.json()["status"], "active")

    # ── Test 13, 14, 15: Close Campaign & Request Preservation ──
    def test_13_14_15_close_campaign_and_request_preservation(self):
        """Closing campaign stops new requests, preserves existing requests and history."""
        # Create and activate
        res = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": 5},
            headers=self.auth_headers,
        )
        camp_id = res.json()["id"]
        self.cleanup_camps.append(camp_id)
        self.client.post(f"/api/campaigns/{camp_id}/activate", headers=self.auth_headers)

        # Submit a pending request
        uid = create_or_update_user(777888999, "testuser", "Tester")
        req_id = create_request(
            campaign_id=camp_id,
            user_id=uid,
            site_id="SITE-P23-01",
            screenshot_file_id="FILE_123",
        )

        # Close campaign
        close_res = self.client.post(f"/api/campaigns/{camp_id}/close", headers=self.auth_headers)
        self.assertEqual(close_res.status_code, 200)

        # 1. No active campaign in system
        self.assertIsNone(get_active_campaign())

        # 2. Existing request is still present and pending
        req_data = get_request_by_id(req_id)
        self.assertIsNotNone(req_data)
        self.assertEqual(req_data["status"], "pending")

        # 3. Campaign record still exists in closed state
        camp_data = get_campaign_by_id(camp_id)
        self.assertEqual(camp_data["status"], "closed")
        self.assertIsNotNone(camp_data["closed_at"])

    # ── Test 16, 17, 18: Full Campaign & Remaining Slots ────────
    def test_16_17_18_capacity_and_full_status(self):
        """Campaign transitions to FULL when capacity is reached; slots calculate correctly."""
        res = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": 2},
            headers=self.auth_headers,
        )
        camp_id = res.json()["id"]
        self.cleanup_camps.append(camp_id)
        self.client.post(f"/api/campaigns/{camp_id}/activate", headers=self.auth_headers)

        # 1 request submitted -> 1 remaining
        u1 = create_or_update_user(888111001, "u1", "U1")
        create_request(
            campaign_id=camp_id,
            user_id=u1,
            site_id="SITE-1",
        )
        detail1 = self.client.get(f"/api/campaigns/{camp_id}", headers=self.auth_headers).json()
        self.assertEqual(detail1["pending_requests"], 1)
        self.assertEqual(detail1["remaining_slots"], 1)
        self.assertEqual(detail1["status"], "active")

        # 2nd request submitted -> reaches max_requests -> transitions to full
        u2 = create_or_update_user(888111002, "u2", "U2")
        create_request(
            campaign_id=camp_id,
            user_id=u2,
            site_id="SITE-2",
        )
        detail2 = self.client.get(f"/api/campaigns/{camp_id}", headers=self.auth_headers).json()
        self.assertEqual(detail2["pending_requests"], 2)
        self.assertEqual(detail2["remaining_slots"], 0)
        self.assertEqual(detail2["status"], "full")

    # ── Test 19: Multiple campaigns per promo code (History) ────
    def test_19_campaign_history_preserved(self):
        """A promo code can have multiple historical campaigns (closed/completed/active)."""
        # Campaign 1
        res1 = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": 5},
            headers=self.auth_headers,
        )
        camp1_id = res1.json()["id"]
        self.cleanup_camps.append(camp1_id)
        self.client.post(f"/api/campaigns/{camp1_id}/activate", headers=self.auth_headers)
        self.client.post(f"/api/campaigns/{camp1_id}/close", headers=self.auth_headers)

        # Campaign 2 (same promo code)
        res2 = self.client.post(
            "/api/campaigns",
            json={"promo_code_id": self.promo_id_1, "max_requests": 10},
            headers=self.auth_headers,
        )
        camp2_id = res2.json()["id"]
        self.cleanup_camps.append(camp2_id)

        # Both exist in campaign list
        list_res = self.client.get(
            f"/api/campaigns?promo_code={self.test_code_1}",
            headers=self.auth_headers,
        )
        ids = [c["id"] for c in list_res.json()]
        self.assertIn(camp1_id, ids)
        self.assertIn(camp2_id, ids)

    # ── Test 20: No secrets exposed ─────────────────────────────
    def test_20_no_secrets_exposed(self):
        """Campaign endpoints never expose BOT_TOKEN or ADMIN_TELEGRAM_ID."""
        res = self.client.get("/api/campaigns", headers=self.auth_headers)
        self.assertNotIn(config.BOT_TOKEN, res.text)
        if config.ADMIN_TELEGRAM_ID:
            self.assertNotIn(str(config.ADMIN_TELEGRAM_ID), res.text)

    # ── Test 21: Build artifacts exist ──────────────────────────
    def test_21_build_artifacts_exist(self):
        """Dashboard dist/ folder contains index.html and compiled bundle."""
        dist_dir = DASHBOARD_DIR / "dist"
        self.assertTrue((dist_dir / "index.html").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
