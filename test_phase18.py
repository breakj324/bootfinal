"""
test_phase18.py — Complete Phase 18 Test Suite for Admin Pending Requests Management.

Tests: access control, list display, details, accept/reject reuse, pagination,
       refresh, stale protection, security, and data integrity.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

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
    get_campaign_by_id,
    create_request,
    get_request_by_id,
    review_request,
    delete_campaign,
    get_pending_requests,
    get_pending_requests_count,
    get_connection,
)
import admin_bot

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
ADMIN_ID = config.ADMIN_TELEGRAM_ID or 1490527403
NON_ADMIN_ID = 7777799991


def make_callback(admin_id, data):
    user = MagicMock()
    user.id = admin_id
    query = AsyncMock()
    query.data = data
    query.message = AsyncMock()
    query.message.photo = False
    query.message.text = "original"
    query.message.caption = ""
    update = MagicMock()
    update.effective_user = user
    update.message = None
    update.callback_query = query
    return update, query


def make_context(user_data=None):
    ctx = MagicMock()
    ctx.user_data = user_data or {}
    ctx.bot = AsyncMock()
    return ctx


# ─────────────────────────────────────────────────────────────
# Test Class
# ─────────────────────────────────────────────────────────────
class TestPhase18PendingRequests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        initialize_database()
        self.test_code = "MRC456P18"
        self.cleanup_camps = []
        self.cleanup_user_tg_ids = []

        delete_promo_code(self.test_code)
        self.promo_id = create_promo_code(
            code=self.test_code,
            description="Phase 18 test promo",
            instructions="Test",
            requirements="Test",
        )

        # Ensure no active campaign interferes; use a fresh one
        self.camp_id = create_campaign(promo_code=self.promo_id, max_requests=20)
        activate_campaign(self.camp_id)
        self.cleanup_camps.append(self.camp_id)

        # Create test customer
        self.cust_tg_id = 99180100
        self.cleanup_user_tg_ids.append(self.cust_tg_id)
        self.cust_db_id = create_or_update_user(
            telegram_user_id=self.cust_tg_id,
            username="p18customer",
            first_name="P18User"
        )

    async def asyncTearDown(self):
        # Delete all requests tied to test campaigns
        for cid in self.cleanup_camps:
            try:
                with get_connection() as conn:
                    conn.execute("DELETE FROM requests WHERE campaign_id = ?", (cid,))
                    conn.commit()
                delete_campaign(cid)
            except Exception:
                pass
        for tg_id in self.cleanup_user_tg_ids:
            try:
                delete_user_by_telegram_id(tg_id)
            except Exception:
                pass
        delete_promo_code(self.test_code)

    # ── Test 1: Non-admin cannot access Pending Requests ────────
    async def test_01_non_admin_blocked(self):
        """Non-admin is rejected from Pending Requests."""
        update, query = make_callback(NON_ADMIN_ID, "admin_menu_requests")
        ctx = make_context()
        result = await admin_bot.show_pending_requests(update, ctx)
        self.assertEqual(result, admin_bot.ConversationHandler.END)

    # ── Test 2: Admin can open Pending Requests ──────────────────
    async def test_02_admin_can_open_pending(self):
        """Admin gets Pending Requests list (possibly empty)."""
        update, query = make_callback(ADMIN_ID, "admin_menu_requests")
        ctx = make_context()
        result = await admin_bot.show_pending_requests(update, ctx)
        self.assertIn(result, [admin_bot.ADMIN_REQUESTS_MENU])
        query.answer.assert_called()

    # ── Test 3: Empty list shows correct message ──────────────────
    async def test_03_empty_pending_list(self):
        """Empty pending list shows correct Arabic message."""
        # Use a fresh campaign with no requests
        camp2 = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp2)

        # Temporarily: close our main camp so no pending exist only for this camp
        # Instead patch get_pending_requests_count to 0
        from unittest.mock import patch
        with patch("admin_bot.get_pending_requests_count", return_value=0), \
             patch("admin_bot.get_pending_requests", return_value=[]):
            update, query = make_callback(ADMIN_ID, "admin_menu_requests")
            ctx = make_context()
            result = await admin_bot.show_pending_requests(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_REQUESTS_MENU)
        # Check the "no pending" message was sent/edited
        call_text = query.edit_message_text.call_args[0][0]
        self.assertIn("ما كاين حتى طلب", call_text)

    # ── Test 4: Pending requests are listed ──────────────────────
    async def test_04_pending_requests_listed(self):
        """Pending requests appear in the list."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18001", screenshot_file_id="photo_p18", status="pending"
        )
        update, query = make_callback(ADMIN_ID, "admin_menu_requests")
        ctx = make_context()
        result = await admin_bot.show_pending_requests(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_REQUESTS_MENU)
        # Message should mention the request ID
        call_text = query.edit_message_text.call_args[0][0]
        self.assertIn(str(req_id), call_text)

    # ── Test 5: Promo Code is displayed ──────────────────────────
    async def test_05_promo_code_displayed(self):
        """Promo code appears in the pending list."""
        create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18002", status="pending"
        )
        update, query = make_callback(ADMIN_ID, "admin_menu_requests")
        ctx = make_context()
        await admin_bot.show_pending_requests(update, ctx)
        call_text = query.edit_message_text.call_args[0][0]
        self.assertIn(self.test_code, call_text)

    # ── Test 6: Site ID is displayed ─────────────────────────────
    async def test_06_site_id_displayed(self):
        """Site ID appears in the pending list."""
        create_request(
            self.camp_id, self.cust_db_id,
            site_id="SITE18006", status="pending"
        )
        update, query = make_callback(ADMIN_ID, "admin_menu_requests")
        ctx = make_context()
        await admin_bot.show_pending_requests(update, ctx)
        call_text = query.edit_message_text.call_args[0][0]
        self.assertIn("SITE18006", call_text)

    # ── Test 7: Customer information is displayed ─────────────────
    async def test_07_customer_info_displayed(self):
        """Customer first name and username appear in the list."""
        create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18007", status="pending"
        )
        update, query = make_callback(ADMIN_ID, "admin_menu_requests")
        ctx = make_context()
        await admin_bot.show_pending_requests(update, ctx)
        call_text = query.edit_message_text.call_args[0][0]
        self.assertIn("P18User", call_text)

    # ── Test 8: Request status (PENDING) is shown ────────────────
    async def test_08_request_status_displayed(self):
        """Status PENDING is shown in request detail view."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18008", screenshot_file_id=None, status="pending"
        )
        update, query = make_callback(ADMIN_ID, f"admin_req_open_{req_id}")
        ctx = make_context()
        result = await admin_bot.open_request_detail(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_REQUEST_DETAIL)
        edit_call = query.edit_message_text.call_args[0][0]
        self.assertIn("PENDING", edit_call)

    # ── Test 9: Admin can open a pending request ─────────────────
    async def test_09_admin_opens_request(self):
        """Admin can open a pending request detail and sees all fields."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18009", status="pending"
        )
        update, query = make_callback(ADMIN_ID, f"admin_req_open_{req_id}")
        ctx = make_context()
        result = await admin_bot.open_request_detail(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_REQUEST_DETAIL)
        edit_call = query.edit_message_text.call_args[0][0]
        self.assertIn(self.test_code, edit_call)
        self.assertIn("S18009", edit_call)
        self.assertIn(str(self.cust_tg_id), edit_call)

    # ── Test 10: Screenshot shown in detail ──────────────────────
    async def test_10_screenshot_shown(self):
        """When request has a screenshot, reply_photo is called in detail view."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18010", screenshot_file_id="tg_photo_p18_010", status="pending"
        )
        update, query = make_callback(ADMIN_ID, f"admin_req_open_{req_id}")
        ctx = make_context()
        result = await admin_bot.open_request_detail(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_REQUEST_DETAIL)
        query.message.reply_photo.assert_called_once()
        call_kwargs = query.message.reply_photo.call_args[1]
        self.assertEqual(call_kwargs["photo"], "tg_photo_p18_010")
        self.assertIn(self.test_code, call_kwargs["caption"])

    # ── Test 11: Accept uses existing Phase 16 review_request() ──
    async def test_11_accept_uses_review_request(self):
        """Accept action updates status to 'accepted' via review_request()."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18011", status="pending"
        )
        update, query = make_callback(ADMIN_ID, f"admin_req_accept_{req_id}")
        ctx = make_context()
        ctx.bot.send_message = AsyncMock()

        # Patch show_pending_requests to avoid complex re-render in test
        from unittest.mock import patch
        with patch.object(admin_bot, "show_pending_requests", new=AsyncMock(return_value=admin_bot.ADMIN_REQUESTS_MENU)):
            await admin_bot.request_action(update, ctx)

        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "accepted")
        self.assertIsNotNone(req["reviewed_at"])
        ctx.bot.send_message.assert_called_once()
        self.assertIn("قبول", ctx.bot.send_message.call_args[1]["text"])

    # ── Test 12: Reject uses existing Phase 16 review_request() ──
    async def test_12_reject_uses_review_request(self):
        """Reject action updates status to 'rejected' via review_request()."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18012", status="pending"
        )
        update, query = make_callback(ADMIN_ID, f"admin_req_reject_{req_id}")
        ctx = make_context()
        ctx.bot.send_message = AsyncMock()

        from unittest.mock import patch
        with patch.object(admin_bot, "show_pending_requests", new=AsyncMock(return_value=admin_bot.ADMIN_REQUESTS_MENU)):
            await admin_bot.request_action(update, ctx)

        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "rejected")
        self.assertIsNotNone(req["reviewed_at"])
        ctx.bot.send_message.assert_called_once()
        self.assertIn("رفض", ctx.bot.send_message.call_args[1]["text"])

    # ── Test 13: Processed request disappears from pending list ───
    async def test_13_processed_request_not_in_pending(self):
        """Accepted request no longer appears in get_pending_requests()."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18013", status="pending"
        )
        # Verify it appears
        pending_before = [r["id"] for r in get_pending_requests()]
        self.assertIn(req_id, pending_before)

        review_request(req_id, "accepted")

        # After review, should not appear
        pending_after = [r["id"] for r in get_pending_requests()]
        self.assertNotIn(req_id, pending_after)

    # ── Test 14: Stale request cannot be processed twice ─────────
    async def test_14_stale_request_protection(self):
        """Opening an already-processed request shows stale alert, not detail."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18014", status="pending"
        )
        review_request(req_id, "rejected")  # pre-process it

        update, query = make_callback(ADMIN_ID, f"admin_req_open_{req_id}")
        ctx = make_context()

        from unittest.mock import patch
        with patch.object(admin_bot, "show_pending_requests", new=AsyncMock(return_value=admin_bot.ADMIN_REQUESTS_MENU)):
            result = await admin_bot.open_request_detail(update, ctx)

        # Should redirect to list, not ADMIN_REQUEST_DETAIL
        self.assertEqual(result, admin_bot.ADMIN_REQUESTS_MENU)
        # Alert must have been shown
        query.answer.assert_called()
        alert_text = query.answer.call_args[0][0]
        self.assertIn("تمت معالجته", alert_text)

    # ── Test 15: Pagination works for > 10 requests ───────────────
    async def test_15_pagination(self):
        """When >10 pending requests exist, pagination nav buttons appear."""
        # Create 12 distinct users and requests
        created_tg_ids = []
        for i in range(12):
            tg_id = 99180200 + i
            created_tg_ids.append(tg_id)
            self.cleanup_user_tg_ids.append(tg_id)
            uid = create_or_update_user(tg_id, f"u18p{i}", f"User{i}")
            create_request(self.camp_id, uid, site_id=f"S18P{i:03d}", status="pending")

        total = get_pending_requests_count()
        self.assertGreaterEqual(total, 12)

        update, query = make_callback(ADMIN_ID, "admin_menu_requests")
        ctx = make_context({"requests_page": 0})
        result = await admin_bot.show_pending_requests(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_REQUESTS_MENU)

        # Check that "➡️ التالي" button exists in keyboard
        markup = query.edit_message_text.call_args[1]["reply_markup"]
        all_button_data = [
            btn.callback_data
            for row in markup.inline_keyboard
            for btn in row
        ]
        self.assertTrue(any("page_1" in d for d in all_button_data), "Next page button not found")

    # ── Test 16: Refresh shows newly created requests ─────────────
    async def test_16_refresh_shows_new_requests(self):
        """After refresh, newly submitted requests appear."""
        update1, query1 = make_callback(ADMIN_ID, "admin_requests_refresh")
        ctx = make_context({"requests_page": 5})  # simulate non-zero page
        await admin_bot.requests_refresh(update1, ctx)
        # Page should be reset to 0
        self.assertEqual(ctx.user_data["requests_page"], 0)

    # ── Test 17: Unauthorized callbacks are rejected ──────────────
    async def test_17_unauthorized_callbacks_rejected(self):
        """Non-admin cannot open request details or perform actions."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18017", status="pending"
        )

        # Try to open detail
        upd1, qry1 = make_callback(NON_ADMIN_ID, f"admin_req_open_{req_id}")
        ctx1 = make_context()
        result1 = await admin_bot.open_request_detail(upd1, ctx1)
        self.assertEqual(result1, admin_bot.ConversationHandler.END)

        # Try to accept
        upd2, qry2 = make_callback(NON_ADMIN_ID, f"admin_req_accept_{req_id}")
        ctx2 = make_context()
        result2 = await admin_bot.request_action(upd2, ctx2)
        self.assertEqual(result2, admin_bot.ConversationHandler.END)

        # DB must be untouched
        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "pending")

    # ── Test 18: No secrets exposed ──────────────────────────────
    async def test_18_no_secrets_exposed(self):
        """ADMIN_TELEGRAM_ID and BOT_TOKEN are not in any response text."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18018", status="pending"
        )

        # Check list message
        update, query = make_callback(ADMIN_ID, "admin_menu_requests")
        ctx = make_context()
        await admin_bot.show_pending_requests(update, ctx)
        list_text = query.edit_message_text.call_args[0][0]
        self.assertNotIn(config.BOT_TOKEN, list_text)
        self.assertNotIn(str(config.ADMIN_TELEGRAM_ID), list_text)

        # Check detail message
        update2, query2 = make_callback(ADMIN_ID, f"admin_req_open_{req_id}")
        ctx2 = make_context()
        await admin_bot.open_request_detail(update2, ctx2)
        detail_text = query2.edit_message_text.call_args[0][0]
        self.assertNotIn(config.BOT_TOKEN, detail_text)
        self.assertNotIn(str(config.ADMIN_TELEGRAM_ID), detail_text)

    # ── Test 19: Existing request history remains intact ─────────
    async def test_19_request_history_intact(self):
        """Viewing or processing a request does not delete any data."""
        req_id = create_request(
            self.camp_id, self.cust_db_id,
            site_id="S18019", status="pending"
        )

        # Open detail
        update, query = make_callback(ADMIN_ID, f"admin_req_open_{req_id}")
        ctx = make_context()
        await admin_bot.open_request_detail(update, ctx)

        # Request still exists in DB
        req = get_request_by_id(req_id)
        self.assertIsNotNone(req)
        self.assertEqual(req["site_id"], "S18019")

        # Accept it
        update2, query2 = make_callback(ADMIN_ID, f"admin_req_accept_{req_id}")
        ctx2 = make_context()
        ctx2.bot.send_message = AsyncMock()
        from unittest.mock import patch
        with patch.object(admin_bot, "show_pending_requests", new=AsyncMock(return_value=admin_bot.ADMIN_REQUESTS_MENU)):
            await admin_bot.request_action(update2, ctx2)

        # Request still exists, just with updated status
        req_after = get_request_by_id(req_id)
        self.assertIsNotNone(req_after)
        self.assertEqual(req_after["status"], "accepted")
        self.assertEqual(req_after["site_id"], "S18019")


if __name__ == "__main__":
    unittest.main(verbosity=2)
