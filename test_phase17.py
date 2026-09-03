"""
test_phase17.py — Complete Phase 17 Test Suite for Admin Campaign Management.

Tests: /admin access control, Campaign menu, Create/Activate/Close flows,
       capacity transitions, concurrency safety, and secrets protection.
"""
import asyncio
import re
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from database import (
    initialize_database,
    create_or_update_user,
    delete_user_by_telegram_id,
    create_promo_code,
    get_promo_code_by_code,
    disable_promo_code,
    enable_promo_code,
    delete_promo_code,
    create_campaign,
    get_campaign_by_id,
    activate_campaign,
    close_campaign,
    get_active_campaign,
    get_campaigns,
    get_campaign_pending_count,
    get_campaign_remaining_slots,
    can_accept_request,
    create_request,
    delete_campaign,
    get_connection,
)
import admin_bot
import bot


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
ADMIN_ID = config.ADMIN_TELEGRAM_ID or 1490527403
NON_ADMIN_ID = 8888877771


def make_admin_update(admin_id=None, text=None):
    """Build a mock Update from the admin user."""
    user = MagicMock()
    user.id = admin_id or ADMIN_ID
    user.username = "admin_user"
    user.first_name = "Admin"

    msg = AsyncMock()
    msg.text = text
    msg.photo = None

    update = MagicMock()
    update.effective_user = user
    update.message = msg
    update.callback_query = None
    return update, msg


def make_callback_update(admin_id, data):
    """Build a mock Update with a callback_query."""
    user = MagicMock()
    user.id = admin_id

    query = AsyncMock()
    query.data = data
    query.message = AsyncMock()
    query.message.photo = False
    query.message.caption = ""
    query.message.text = "original"

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
class TestPhase17AdminCampaigns(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        initialize_database()
        self.test_code = "MRC456TEST17"
        self.inactive_code = "INACTTEST17"
        self.cleanup_camps = []

        # Clean stale data
        delete_promo_code(self.test_code)
        delete_promo_code(self.inactive_code)

        # Active promo code for tests
        self.promo_id = create_promo_code(
            code=self.test_code,
            description="Phase 17 test promo",
            instructions="Test instructions",
            requirements="Test requirements",
        )
        # Inactive promo code
        self.inactive_promo_id = create_promo_code(
            code=self.inactive_code,
            description="Inactive promo",
            active=0,
        )

    async def asyncTearDown(self):
        for cid in self.cleanup_camps:
            try:
                delete_campaign(cid)
            except Exception:
                pass
        delete_promo_code(self.test_code)
        delete_promo_code(self.inactive_code)

    # ── Test 1: Non-admin cannot access /admin ──────────────
    async def test_01_non_admin_cannot_access(self):
        """Non-admin user is rejected from /admin."""
        update, msg = make_admin_update(admin_id=NON_ADMIN_ID)
        ctx = make_context()
        result = await admin_bot.admin_command(update, ctx)
        self.assertEqual(result, admin_bot.ConversationHandler.END)
        msg.reply_text.assert_called_once()
        self.assertIn("مشرف", msg.reply_text.call_args[0][0])

    # ── Test 2: Admin can access /admin ─────────────────────
    async def test_02_admin_can_access(self):
        """Admin gets main menu via /admin."""
        update, msg = make_admin_update()
        ctx = make_context()
        result = await admin_bot.admin_command(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_MENU)
        msg.reply_text.assert_called_once()
        text = msg.reply_text.call_args[0][0]
        self.assertIn("لوحة تحكم", text)

    # ── Test 3: Campaign menu opens ─────────────────────────
    async def test_03_campaign_menu_opens(self):
        """Admin can open Campaigns menu."""
        update, query = make_callback_update(ADMIN_ID, "admin_menu_campaigns")
        ctx = make_context()
        result = await admin_bot.show_campaigns_menu(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_CAMPAIGNS_MENU)
        query.answer.assert_called()

    # ── Test 4: Active promo codes displayed ────────────────
    async def test_04_active_promos_displayed(self):
        """Start campaign creation shows only active promo codes."""
        update, query = make_callback_update(ADMIN_ID, "admin_camp_create")
        ctx = make_context()
        result = await admin_bot.start_create_campaign(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_SELECTING_PROMO)
        # The edit call should show active promo codes
        call_text = query.edit_message_text.call_args[0][0]
        self.assertIn(self.test_code, str(query.edit_message_text.call_args))

    # ── Test 5: Inactive promo codes cannot be selected ─────
    async def test_05_inactive_promo_cannot_be_selected(self):
        """Inactive promo code button click is safely rejected."""
        update, query = make_callback_update(
            ADMIN_ID, f"admin_promo_select_{self.inactive_promo_id}"
        )
        ctx = make_context()
        result = await admin_bot.promo_selected(update, ctx)
        # Should not proceed to max_requests step
        self.assertNotEqual(result, admin_bot.ADMIN_ENTERING_MAX)
        # Should show error message
        query.edit_message_text.assert_called_once()
        self.assertIn("مو نشط", query.edit_message_text.call_args[0][0])

    # ── Test 6: Admin can select MRC456 ─────────────────────
    async def test_06_admin_can_select_promo(self):
        """Admin selects active promo code and proceeds to enter max_requests."""
        update, query = make_callback_update(
            ADMIN_ID, f"admin_promo_select_{self.promo_id}"
        )
        ctx = make_context()
        result = await admin_bot.promo_selected(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_ENTERING_MAX)
        self.assertEqual(ctx.user_data["new_camp_promo_id"], self.promo_id)
        self.assertEqual(ctx.user_data["new_camp_promo_code"], self.test_code)

    # ── Test 7: Admin can enter 15 ──────────────────────────
    async def test_07_admin_enters_max_requests(self):
        """Admin enters valid max_requests = 15."""
        update, msg = make_admin_update(text="15")
        ctx = make_context(user_data={
            "new_camp_promo_id": self.promo_id,
            "new_camp_promo_code": self.test_code,
        })
        result = await admin_bot.receive_max_requests(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_CAMPAIGNS_MENU)
        # Verify campaign was created
        camp_id = ctx.user_data.get("last_created_camp_id")
        self.assertIsNotNone(camp_id)
        self.cleanup_camps.append(camp_id)
        msg.reply_text.assert_called_once()
        self.assertIn("تخلقات", msg.reply_text.call_args[0][0])

    # ── Test 8 & 9: Campaign created, starts CLOSED ─────────
    async def test_08_09_campaign_created_as_closed(self):
        """Newly created campaign starts with status='closed'."""
        update, msg = make_admin_update(text="10")
        ctx = make_context(user_data={
            "new_camp_promo_id": self.promo_id,
            "new_camp_promo_code": self.test_code,
        })
        await admin_bot.receive_max_requests(update, ctx)
        camp_id = ctx.user_data.get("last_created_camp_id")
        self.assertIsNotNone(camp_id)
        self.cleanup_camps.append(camp_id)
        camp = get_campaign_by_id(camp_id)
        self.assertIsNotNone(camp)
        self.assertEqual(camp["status"], "closed")

    # ── Test 10: Closed campaign cannot accept requests ──────
    async def test_10_closed_campaign_no_requests(self):
        """A CLOSED campaign cannot accept customer requests."""
        camp_id = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp_id)
        self.assertFalse(can_accept_request(camp_id))

    # ── Test 11 & 12: Admin activates campaign ────────────────
    async def test_11_12_admin_activates_campaign(self):
        """Admin activates a closed campaign; it becomes ACTIVE."""
        # Ensure no active campaign exists
        existing = get_active_campaign()
        if existing:
            close_campaign(existing["id"])

        camp_id = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp_id)

        update, query = make_callback_update(ADMIN_ID, "admin_camp_activate")
        ctx = make_context()
        result = await admin_bot.admin_activate_campaign(update, ctx)
        self.assertEqual(result, admin_bot.ADMIN_CAMPAIGNS_MENU)

        camp = get_campaign_by_id(camp_id)
        self.assertEqual(camp["status"], "active")

    # ── Test 13: Customer flow sees active campaign ──────────
    async def test_13_customer_sees_active_campaign(self):
        """When campaign is active, get_active_campaign() returns it."""
        existing = get_active_campaign()
        if existing:
            close_campaign(existing["id"])

        camp_id = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp_id)
        activate_campaign(camp_id)

        active = get_active_campaign()
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], camp_id)
        self.assertEqual(active["promo_code"], self.test_code)

    # ── Test 14: Cannot activate second campaign ─────────────
    async def test_14_cannot_activate_second_campaign(self):
        """If one campaign is active, cannot activate another."""
        # Ensure one is active
        existing = get_active_campaign()
        if not existing:
            camp1 = create_campaign(promo_code=self.promo_id, max_requests=5)
            self.cleanup_camps.append(camp1)
            activate_campaign(camp1)

        # Try to activate another
        camp2 = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp2)

        update, query = make_callback_update(ADMIN_ID, "admin_camp_activate")
        ctx = make_context()
        await admin_bot.admin_activate_campaign(update, ctx)
        # Second campaign must still be closed
        camp2_record = get_campaign_by_id(camp2)
        self.assertEqual(camp2_record["status"], "closed")

    # ── Test 15: Admin views campaign statistics ─────────────
    async def test_15_admin_views_statistics(self):
        """Campaign statistics block contains required fields."""
        camp_id = create_campaign(promo_code=self.promo_id, max_requests=7)
        self.cleanup_camps.append(camp_id)
        camp = get_campaign_by_id(camp_id)
        pending = get_campaign_pending_count(camp_id)
        remaining = get_campaign_remaining_slots(camp_id)

        stats = admin_bot.build_campaign_stats(camp, pending, remaining)
        self.assertIn(self.test_code, stats)
        self.assertIn("7", stats)
        self.assertIn(str(pending), stats)
        self.assertIn(str(remaining), stats)

    # ── Test 16 & 17: Pending count and remaining slots ──────
    async def test_16_17_pending_count_and_slots(self):
        """Pending count and remaining slots update accurately after request creation."""
        camp_id = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp_id)
        activate_campaign(camp_id)

        u1 = create_or_update_user(telegram_user_id=99170001, username="u1")
        u2 = create_or_update_user(telegram_user_id=99170002, username="u2")
        create_request(camp_id, u1, site_id="S001", status="pending")
        create_request(camp_id, u2, site_id="S002", status="pending")

        self.assertEqual(get_campaign_pending_count(camp_id), 2)
        self.assertEqual(get_campaign_remaining_slots(camp_id), 3)

        # cleanup: remove requests first (FK constraint), then users
        with get_connection() as conn:
            conn.execute("DELETE FROM requests WHERE campaign_id = ?", (camp_id,))
            conn.commit()
        delete_user_by_telegram_id(99170001)
        delete_user_by_telegram_id(99170002)

    # ── Test 18 & 19: Campaign auto-FULL, no new requests ────
    async def test_18_19_campaign_full_no_new_requests(self):
        """Campaign becomes FULL when capacity reached; no new requests accepted."""
        camp_id = create_campaign(promo_code=self.promo_id, max_requests=2)
        self.cleanup_camps.append(camp_id)
        activate_campaign(camp_id)

        u1 = create_or_update_user(telegram_user_id=99180001, username="u18a")
        u2 = create_or_update_user(telegram_user_id=99180002, username="u18b")
        u3 = create_or_update_user(telegram_user_id=99180003, username="u18c")
        create_request(camp_id, u1, site_id="S001", status="pending")
        create_request(camp_id, u2, site_id="S002", status="pending")

        camp = get_campaign_by_id(camp_id)
        self.assertEqual(camp["status"], "full")
        self.assertFalse(can_accept_request(camp_id))

        with self.assertRaises(ValueError):
            create_request(camp_id, u3, site_id="S003", status="pending")

        # cleanup: remove requests first (FK), then users
        with get_connection() as conn:
            conn.execute("DELETE FROM requests WHERE campaign_id = ?", (camp_id,))
            conn.commit()
        for tid in [99180001, 99180002, 99180003]:
            delete_user_by_telegram_id(tid)

    # ── Test 20 & 21: Admin closes campaign ──────────────────
    async def test_20_21_admin_closes_campaign(self):
        """Admin closes active campaign; it stops accepting requests."""
        existing = get_active_campaign()
        if existing:
            close_campaign(existing["id"])

        camp_id = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp_id)
        activate_campaign(camp_id)

        # Step 1: confirm dialog
        update1, query1 = make_callback_update(ADMIN_ID, "admin_camp_close")
        ctx = make_context()
        result1 = await admin_bot.admin_close_campaign_confirm(update1, ctx)
        self.assertEqual(result1, admin_bot.ADMIN_CONFIRM_CLOSE)

        # Step 2: execute close
        update2, query2 = make_callback_update(ADMIN_ID, f"admin_camp_close_confirm_{camp_id}")
        ctx2 = make_context()
        result2 = await admin_bot.admin_close_campaign_execute(update2, ctx2)
        self.assertEqual(result2, admin_bot.ADMIN_CAMPAIGNS_MENU)

        camp = get_campaign_by_id(camp_id)
        self.assertEqual(camp["status"], "closed")
        self.assertFalse(can_accept_request(camp_id))

    # ── Test 22: Existing requests remain intact ─────────────
    async def test_22_existing_requests_intact(self):
        """Closing a campaign does not delete existing requests."""
        existing = get_active_campaign()
        if existing:
            close_campaign(existing["id"])

        camp_id = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp_id)
        activate_campaign(camp_id)

        u1 = create_or_update_user(telegram_user_id=99220001, username="u22a")
        req_id = create_request(camp_id, u1, site_id="S001", status="pending")
        close_campaign(camp_id)

        with get_connection() as conn:
            row = conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "pending")

        # cleanup: delete requests first, then user
        with get_connection() as conn:
            conn.execute("DELETE FROM requests WHERE campaign_id = ?", (camp_id,))
            conn.commit()
        delete_user_by_telegram_id(99220001)

    # ── Test 23: Repeated Activate clicks are safe ───────────
    async def test_23_repeated_activate_safe(self):
        """Clicking Activate twice does not break state."""
        existing = get_active_campaign()
        if existing:
            close_campaign(existing["id"])

        camp_id = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp_id)

        update1, query1 = make_callback_update(ADMIN_ID, "admin_camp_activate")
        ctx1 = make_context()
        result1 = await admin_bot.admin_activate_campaign(update1, ctx1)
        self.assertEqual(result1, admin_bot.ADMIN_CAMPAIGNS_MENU)

        # Second click — already active, no second campaign should activate
        camp2 = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp2)

        update2, query2 = make_callback_update(ADMIN_ID, "admin_camp_activate")
        ctx2 = make_context()
        result2 = await admin_bot.admin_activate_campaign(update2, ctx2)
        self.assertEqual(result2, admin_bot.ADMIN_CAMPAIGNS_MENU)

        # camp2 must still be closed
        self.assertEqual(get_campaign_by_id(camp2)["status"], "closed")

    # ── Test 24: Repeated Close clicks are safe ──────────────
    async def test_24_repeated_close_safe(self):
        """Clicking Close twice is handled gracefully."""
        existing = get_active_campaign()
        if existing:
            close_campaign(existing["id"])

        camp_id = create_campaign(promo_code=self.promo_id, max_requests=5)
        self.cleanup_camps.append(camp_id)
        activate_campaign(camp_id)

        # First close
        update1, query1 = make_callback_update(ADMIN_ID, f"admin_camp_close_confirm_{camp_id}")
        ctx1 = make_context()
        result1 = await admin_bot.admin_close_campaign_execute(update1, ctx1)
        self.assertEqual(get_campaign_by_id(camp_id)["status"], "closed")

        # Second close attempt — already closed, should handle gracefully
        update2, query2 = make_callback_update(ADMIN_ID, f"admin_camp_close_confirm_{camp_id}")
        ctx2 = make_context()
        # Should not raise; should show info or silently handle
        try:
            result2 = await admin_bot.admin_close_campaign_execute(update2, ctx2)
        except Exception as e:
            self.fail(f"Second close raised exception: {e}")
        # Campaign status must not break
        self.assertEqual(get_campaign_by_id(camp_id)["status"], "closed")

    # ── Test 25: No secrets exposed ─────────────────────────
    async def test_25_no_secrets_exposed(self):
        """ADMIN_TELEGRAM_ID and BOT_TOKEN are not exposed in any response."""
        update, msg = make_admin_update()
        ctx = make_context()
        await admin_bot.admin_command(update, ctx)
        response_text = msg.reply_text.call_args[0][0]
        self.assertNotIn(str(config.ADMIN_TELEGRAM_ID), response_text)
        self.assertNotIn(config.BOT_TOKEN, response_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
