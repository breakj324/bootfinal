import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from database import (
    initialize_database,
    create_or_update_user,
    get_user_by_telegram_id,
    delete_user_by_telegram_id,
    create_promo_code,
    get_promo_code_by_code,
    delete_promo_code,
    create_campaign,
    get_campaign_by_id,
    activate_campaign,
    get_campaign_pending_count,
    create_request,
    get_request_by_id,
    review_request,
    delete_campaign,
    get_connection,
)
import bot


class TestPhase16AdminReviewSystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        initialize_database()
        self.test_admin_id = config.ADMIN_TELEGRAM_ID or 1490527403
        self.test_customer_tg_id = 999777111
        self.unauthorized_tg_id = 999777999
        self.test_code = "MRC456"

        delete_user_by_telegram_id(self.test_customer_tg_id)
        delete_user_by_telegram_id(self.unauthorized_tg_id)
        delete_promo_code(self.test_code)

        # Setup Promo Code & Campaign
        self.promo_id = create_promo_code(
            code=self.test_code,
            description="Phase 16 Admin Review Test Bonus",
            instructions="Sign up with MRC456",
            requirements="Send Site ID screenshot"
        )
        self.camp_id = create_campaign(promo_code=self.test_code, max_requests=5)
        activate_campaign(self.camp_id)

        # Create Customer
        self.cust_db_id = create_or_update_user(
            telegram_user_id=self.test_customer_tg_id,
            username="test_customer",
            first_name="CustomerOne"
        )

        self.campaigns_to_cleanup = [self.camp_id]

    async def asyncTearDown(self):
        for cid in self.campaigns_to_cleanup:
            delete_campaign(cid)
        delete_user_by_telegram_id(self.test_customer_tg_id)
        delete_user_by_telegram_id(self.unauthorized_tg_id)
        delete_promo_code(self.test_code)

    def test_1_admin_id_loaded_safely(self):
        """Verify ADMIN_TELEGRAM_ID is loaded safely without printing secrets."""
        self.assertIsNotNone(config.ADMIN_TELEGRAM_ID)
        self.assertIsInstance(config.ADMIN_TELEGRAM_ID, int)
        self.assertGreater(config.ADMIN_TELEGRAM_ID, 0)

    async def test_2_customer_submission_notifies_admin(self):
        """Verify admin receives notification with promo code, site ID, user info, photo, and buttons."""
        user = MagicMock()
        user.id = self.test_customer_tg_id
        user.username = "test_customer"
        user.first_name = "CustomerOne"

        message = AsyncMock()
        message.text = "ID: 38938378"
        update = MagicMock()
        update.effective_user = user
        update.message = message

        context = MagicMock()
        context.user_data = {
            "campaign_id": self.camp_id,
            "db_user_id": self.cust_db_id,
            "promo_code": self.test_code,
            "screenshot_file_id": "tg_photo_id_777",
        }
        context.bot.send_photo = AsyncMock()
        context.bot.send_message = AsyncMock()

        res = await bot.handle_site_id(update, context)
        self.assertEqual(res, bot.ConversationHandler.END)

        # Confirm admin received notification
        context.bot.send_photo.assert_called_once()
        call_args = context.bot.send_photo.call_args[1]

        self.assertEqual(call_args["chat_id"], config.ADMIN_TELEGRAM_ID)
        self.assertEqual(call_args["photo"], "tg_photo_id_777")
        caption = call_args["caption"]
        self.assertIn("MRC456", caption)
        self.assertIn("38938378", caption)
        self.assertIn(str(self.test_customer_tg_id), caption)
        self.assertIn("CustomerOne", caption)

        # Verify buttons
        markup = call_args["reply_markup"]
        self.assertIsNotNone(markup)
        buttons = markup.inline_keyboard[0]
        self.assertEqual(buttons[0].text, "✅ قبول الطلب")
        self.assertEqual(buttons[1].text, "❌ رفض الطلب")

    async def test_3_admin_accept_flow(self):
        """Verify admin Accept action updates status to accepted, sets reviewed_at, and notifies customer."""
        req_id = create_request(
            campaign_id=self.camp_id,
            user_id=self.cust_db_id,
            site_id="38938378",
            screenshot_file_id="photo_123",
            status="pending"
        )

        admin_user = MagicMock()
        admin_user.id = config.ADMIN_TELEGRAM_ID

        cb_query = AsyncMock()
        cb_query.data = f"admin_accept_{req_id}"
        cb_query.message = AsyncMock()
        cb_query.message.photo = True
        cb_query.message.caption = "Original caption"

        update = MagicMock()
        update.effective_user = admin_user
        update.callback_query = cb_query

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await bot.handle_admin_review(update, context)

        # Check DB status
        req = get_request_by_id(req_id)
        self.assertIsNotNone(req)
        self.assertEqual(req["status"], "accepted")
        self.assertIsNotNone(req["reviewed_at"])

        # Check admin UI update
        cb_query.answer.assert_called()
        cb_query.edit_message_caption.assert_called_once()
        self.assertIn("✅ تم القبول", cb_query.edit_message_caption.call_args[1]["caption"])

        # Check customer notification
        context.bot.send_message.assert_called_once()
        cust_call = context.bot.send_message.call_args[1]
        self.assertEqual(cust_call["chat_id"], self.test_customer_tg_id)
        self.assertIn("تم قبول الطلب ديالك بنجاح", cust_call["text"])
        self.assertIn("MRC456", cust_call["text"])
        self.assertIn("38938378", cust_call["text"])

    async def test_4_admin_reject_flow(self):
        """Verify admin Reject action updates status to rejected, sets reviewed_at, and notifies customer."""
        req_id = create_request(
            campaign_id=self.camp_id,
            user_id=self.cust_db_id,
            site_id="38938378",
            screenshot_file_id="photo_123",
            status="pending"
        )

        admin_user = MagicMock()
        admin_user.id = config.ADMIN_TELEGRAM_ID

        cb_query = AsyncMock()
        cb_query.data = f"admin_reject_{req_id}"
        cb_query.message = AsyncMock()
        cb_query.message.photo = True
        cb_query.message.caption = "Original caption"

        update = MagicMock()
        update.effective_user = admin_user
        update.callback_query = cb_query

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await bot.handle_admin_review(update, context)

        # Check DB status
        req = get_request_by_id(req_id)
        self.assertIsNotNone(req)
        self.assertEqual(req["status"], "rejected")
        self.assertIsNotNone(req["reviewed_at"])

        # Check admin UI update
        cb_query.answer.assert_called()
        cb_query.edit_message_caption.assert_called_once()
        self.assertIn("❌ تم الرفض", cb_query.edit_message_caption.call_args[1]["caption"])

        # Check customer notification
        context.bot.send_message.assert_called_once()
        cust_call = context.bot.send_message.call_args[1]
        self.assertEqual(cust_call["chat_id"], self.test_customer_tg_id)
        self.assertIn("تم رفض الطلب ديالك", cust_call["text"])

    async def test_5_6_prevent_double_processing(self):
        """Verify second click on already reviewed request is rejected safely."""
        req_id = create_request(
            campaign_id=self.camp_id,
            user_id=self.cust_db_id,
            site_id="38938378",
            status="pending"
        )
        # First review -> accepted
        success1, _ = review_request(req_id, "accepted")
        self.assertTrue(success1)

        # Second review -> rejected attempt
        success2, msg2 = review_request(req_id, "rejected")
        self.assertFalse(success2)
        self.assertIn("already processed", msg2.lower())

        # Attempt via bot handler
        admin_user = MagicMock()
        admin_user.id = config.ADMIN_TELEGRAM_ID
        cb_query = AsyncMock()
        cb_query.data = f"admin_reject_{req_id}"
        cb_query.message = AsyncMock()

        update = MagicMock()
        update.effective_user = admin_user
        update.callback_query = cb_query

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await bot.handle_admin_review(update, context)

        # Confirm customer was NOT notified a second time
        context.bot.send_message.assert_not_called()
        # Confirm DB status remains accepted
        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "accepted")

    async def test_7_reject_unauthorized_user(self):
        """Verify unauthorized users cannot execute admin review actions."""
        req_id = create_request(
            campaign_id=self.camp_id,
            user_id=self.cust_db_id,
            site_id="38938378",
            status="pending"
        )

        unauth_user = MagicMock()
        unauth_user.id = self.unauthorized_tg_id  # Not the admin

        cb_query = AsyncMock()
        cb_query.data = f"admin_accept_{req_id}"

        update = MagicMock()
        update.effective_user = unauth_user
        update.callback_query = cb_query

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await bot.handle_admin_review(update, context)

        # Alert unauthorized
        cb_query.answer.assert_called_once_with("❌ غير مصرح لك بالقيام بهذا الإجراء.", show_alert=True)
        # Verify request status untouched
        req = get_request_by_id(req_id)
        self.assertEqual(req["status"], "pending")
        # Verify customer not notified
        context.bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
