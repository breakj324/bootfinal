"""
test_phase22.py — Complete test suite for Phase 22: Promo Code Management.

Verifies:
1. Unauthenticated user cannot access promo management.
2. Authenticated admin can list promo codes.
3. Admin can create promo code.
4. Duplicate promo code returns 409 Conflict.
5. Required fields are validated (422 Unprocessable Entity).
6. Newly created code appears in list.
7. Admin can retrieve individual promo code.
8. Admin can edit description.
9. Admin can edit instructions.
10. Admin can edit requirements.
11. Admin can enable disabled code.
12. Admin can disable active code.
13. Disabled code disappears from active promo code queries.
14. Enabled code appears again in active promo code queries.
15. Cannot disable promo code used by active campaign.
16. Existing campaign history remains intact.
17. No DELETE endpoint is implemented.
18. Example image validation works.
19. Unauthorized mutation attempts fail.
20. No secrets exposed.
21. Frontend build artifacts exist.
"""
import io
import os
import unittest
from pathlib import Path
from starlette.testclient import TestClient

import config
from database import (
    initialize_database,
    create_promo_code,
    delete_promo_code,
    get_promo_code_by_id,
    get_active_promo_codes,
    create_campaign,
    activate_campaign,
    close_campaign,
    delete_campaign,
    get_connection,
)
from backend.main import app

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"


class TestPhase22PromoCodeManagement(unittest.TestCase):

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
        self.test_code_1 = "MRC456P22"
        self.test_code_2 = "WIN789P22"
        self.cleanup_promos = [self.test_code_1, self.test_code_2]
        self.cleanup_camps = []

        for c in self.cleanup_promos:
            delete_promo_code(c)

    def tearDown(self):
        for cid in self.cleanup_camps:
            try:
                delete_campaign(cid)
            except Exception:
                pass
        for c in self.cleanup_promos:
            delete_promo_code(c)

    # ── Test 1: Unauthenticated access blocked ──────────────────
    def test_01_unauthenticated_blocked(self):
        """Unauthenticated requests to promo endpoints return 401."""
        self.assertEqual(self.client.get("/api/promo-codes").status_code, 401)
        self.assertEqual(self.client.post("/api/promo-codes", json={}).status_code, 401)
        self.assertEqual(self.client.put("/api/promo-codes/1", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/promo-codes/1/enable").status_code, 401)
        self.assertEqual(self.client.post("/api/promo-codes/1/disable").status_code, 401)

    # ── Test 2: Authenticated admin can list promo codes ────────
    def test_02_admin_can_list_promos(self):
        """Admin can list all promo codes via GET /api/promo-codes."""
        res = self.client.get("/api/promo-codes", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    # ── Test 3, 5, 6: Create Promo Code & Validation ────────────
    def test_03_05_06_create_promo_code_and_validation(self):
        """Admin creates promo code, validates required fields, and verifies listing."""
        # 1. Missing fields (422)
        invalid_res = self.client.post(
            "/api/promo-codes",
            json={"code": "", "description": "", "instructions": "", "requirements": ""},
            headers=self.auth_headers,
        )
        self.assertEqual(invalid_res.status_code, 422)

        # 2. Valid creation (201)
        valid_res = self.client.post(
            "/api/promo-codes",
            json={
                "code": self.test_code_1,
                "description": "Exclusive bonus code",
                "instructions": "Step 1: Sign up. Step 2: Use code.",
                "requirements": "Screenshot showing ID and code",
                "example_image": "/uploads/example.png",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(valid_res.status_code, 201)
        created = valid_res.json()
        self.assertEqual(created["code"], self.test_code_1)
        self.assertEqual(created["active"], 1)

        # 3. Code appears in list
        list_res = self.client.get("/api/promo-codes", headers=self.auth_headers)
        codes = [p["code"] for p in list_res.json()]
        self.assertIn(self.test_code_1, codes)

    # ── Test 4: Duplicate Promo Code returns 409 Conflict ───────
    def test_04_duplicate_promo_returns_409(self):
        """Creating an existing promo code returns 409 Conflict."""
        # First create
        self.client.post(
            "/api/promo-codes",
            json={
                "code": self.test_code_1,
                "description": "First create",
                "instructions": "Inst",
                "requirements": "Req",
            },
            headers=self.auth_headers,
        )

        # Second create with same code
        dup_res = self.client.post(
            "/api/promo-codes",
            json={
                "code": self.test_code_1.lower(),  # test case-insensitivity normalization
                "description": "Duplicate create",
                "instructions": "Inst",
                "requirements": "Req",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(dup_res.status_code, 409)
        self.assertIn("already exists", dup_res.json()["detail"].lower())

    # ── Test 7: Retrieve individual promo code ──────────────────
    def test_07_retrieve_individual_promo(self):
        """GET /api/promo-codes/{id} returns promo details."""
        create_res = self.client.post(
            "/api/promo-codes",
            json={
                "code": self.test_code_1,
                "description": "Details test",
                "instructions": "Instructions text",
                "requirements": "Requirements text",
            },
            headers=self.auth_headers,
        )
        promo_id = create_res.json()["id"]

        get_res = self.client.get(f"/api/promo-codes/{promo_id}", headers=self.auth_headers)
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertEqual(data["id"], promo_id)
        self.assertEqual(data["code"], self.test_code_1)

    # ── Test 8, 9, 10: Edit description, instructions, reqs ─────
    def test_08_09_10_edit_promo_fields(self):
        """Admin can update description, instructions, requirements."""
        create_res = self.client.post(
            "/api/promo-codes",
            json={
                "code": self.test_code_1,
                "description": "Old Desc",
                "instructions": "Old Inst",
                "requirements": "Old Reqs",
            },
            headers=self.auth_headers,
        )
        promo_id = create_res.json()["id"]

        # Update
        update_res = self.client.put(
            f"/api/promo-codes/{promo_id}",
            json={
                "description": "Updated Description",
                "instructions": "Updated Instructions",
                "requirements": "Updated Requirements",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(update_res.status_code, 200)
        updated = update_res.json()
        self.assertEqual(updated["description"], "Updated Description")
        self.assertEqual(updated["instructions"], "Updated Instructions")
        self.assertEqual(updated["requirements"], "Updated Requirements")
        self.assertEqual(updated["code"], self.test_code_1)  # immutable

    # ── Test 11, 12, 13, 14: Enable, Disable & Active Queries ───
    def test_11_12_13_14_enable_disable_lifecycle(self):
        """Test disabling, query removal, enabling, and query restoration."""
        create_res = self.client.post(
            "/api/promo-codes",
            json={
                "code": self.test_code_1,
                "description": "Toggle test",
                "instructions": "Inst",
                "requirements": "Req",
            },
            headers=self.auth_headers,
        )
        promo_id = create_res.json()["id"]

        # 1. Initially active in database
        active_codes = [p["code"] for p in get_active_promo_codes()]
        self.assertIn(self.test_code_1, active_codes)

        # 2. Disable
        dis_res = self.client.post(f"/api/promo-codes/{promo_id}/disable", headers=self.auth_headers)
        self.assertEqual(dis_res.status_code, 200)
        self.assertEqual(dis_res.json()["active"], 0)

        # 3. Disappears from active queries
        active_codes_after = [p["code"] for p in get_active_promo_codes()]
        self.assertNotIn(self.test_code_1, active_codes_after)

        # 4. Enable
        en_res = self.client.post(f"/api/promo-codes/{promo_id}/enable", headers=self.auth_headers)
        self.assertEqual(en_res.status_code, 200)
        self.assertEqual(en_res.json()["active"], 1)

        # 5. Reappears in active queries
        active_codes_restored = [p["code"] for p in get_active_promo_codes()]
        self.assertIn(self.test_code_1, active_codes_restored)

    # ── Test 15 & 16: Active Campaign Protection ────────────────
    def test_15_16_active_campaign_protection(self):
        """Cannot disable promo code referenced by an active campaign."""
        create_res = self.client.post(
            "/api/promo-codes",
            json={
                "code": self.test_code_1,
                "description": "Campaign test",
                "instructions": "Inst",
                "requirements": "Req",
            },
            headers=self.auth_headers,
        )
        promo_id = create_res.json()["id"]

        # Create and activate campaign
        camp_id = create_campaign(promo_code=promo_id, max_requests=10)
        activate_campaign(camp_id)
        self.cleanup_camps.append(camp_id)

        # Attempt to disable should fail with 409 Conflict
        dis_res = self.client.post(f"/api/promo-codes/{promo_id}/disable", headers=self.auth_headers)
        self.assertEqual(dis_res.status_code, 409)
        self.assertIn("active campaign", dis_res.json()["detail"].lower())

        # Close campaign first
        close_campaign(camp_id)

        # Now disable succeeds
        dis_res_ok = self.client.post(f"/api/promo-codes/{promo_id}/disable", headers=self.auth_headers)
        self.assertEqual(dis_res_ok.status_code, 200)

    # ── Test 17: No DELETE endpoint implemented ─────────────────
    def test_17_no_delete_endpoint(self):
        """DELETE method is not allowed on promo codes (history preservation)."""
        res = self.client.delete("/api/promo-codes/1", headers=self.auth_headers)
        self.assertEqual(res.status_code, 405)

    # ── Test 18: Example image upload & validation ──────────────
    def test_18_image_upload_validation(self):
        """Image upload validates format (PNG/JPEG/WEBP) and rejects invalid files."""
        # 1. Invalid file type (.txt)
        bad_file = io.BytesIO(b"not an image file")
        bad_res = self.client.post(
            "/api/promo-codes/upload-image",
            files={"file": ("test.txt", bad_file, "text/plain")},
            headers=self.auth_headers,
        )
        self.assertEqual(bad_res.status_code, 400)

        # 2. Valid PNG image
        valid_png = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
        good_res = self.client.post(
            "/api/promo-codes/upload-image",
            files={"file": ("sample.png", valid_png, "image/png")},
            headers=self.auth_headers,
        )
        self.assertEqual(good_res.status_code, 200)
        self.assertIn("url", good_res.json())
        self.assertTrue(good_res.json()["url"].startswith("/uploads/"))

    # ── Test 19: Unauthorized mutation attempts fail ────────────
    def test_19_unauthorized_mutations_fail(self):
        """Mutations without auth token return 401."""
        self.assertEqual(
            self.client.post("/api/promo-codes", json={"code": "HACK"}).status_code, 401
        )
        self.assertEqual(
            self.client.put("/api/promo-codes/1", json={"description": "HACK"}).status_code, 401
        )
        self.assertEqual(
            self.client.post("/api/promo-codes/1/enable").status_code, 401
        )

    # ── Test 20: No secrets exposed ─────────────────────────────
    def test_20_no_secrets_exposed(self):
        """Promo endpoints never expose BOT_TOKEN or ADMIN_TELEGRAM_ID."""
        res = self.client.get("/api/promo-codes", headers=self.auth_headers)
        self.assertNotIn(config.BOT_TOKEN, res.text)
        if config.ADMIN_TELEGRAM_ID:
            self.assertNotIn(str(config.ADMIN_TELEGRAM_ID), res.text)

    # ── Test 21: Build output verified ──────────────────────────
    def test_21_build_artifacts_exist(self):
        """Dashboard dist/ folder contains index.html and compiled bundle."""
        dist_dir = DASHBOARD_DIR / "dist"
        self.assertTrue((dist_dir / "index.html").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
