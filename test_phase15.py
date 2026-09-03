import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

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
    close_campaign,
    complete_campaign,
    get_campaign_pending_count,
    get_campaign_remaining_slots,
    can_accept_request,
    create_request,
    update_request_status,
    delete_campaign,
    get_connection,
)
import bot


class TestPhase15CustomerFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        initialize_database()
        self.test_tg_id_1 = 999111001
        self.test_tg_id_2 = 999111002
        self.test_code = "MRC456"

        delete_user_by_telegram_id(self.test_tg_id_1)
        delete_user_by_telegram_id(self.test_tg_id_2)
        delete_promo_code(self.test_code)

        # Create Promo Code
        self.promo_id = create_promo_code(
            code=self.test_code,
            description="50% deposit bonus on registration",
            instructions="1. Create account\n2. Use code MRC456\n3. Take screenshot",
            requirements="Screenshot must display Site ID clearly",
            example_image=None
        )

        self.campaigns_to_cleanup = []

    async def asyncTearDown(self):
        for cid in self.campaigns_to_cleanup:
            delete_campaign(cid)
        delete_user_by_telegram_id(self.test_tg_id_1)
        delete_user_by_telegram_id(self.test_tg_id_2)
        delete_promo_code(self.test_code)

    def _create_mock_update_and_context(self, tg_id, username="test_cust", first_name="Cust"):
        user = MagicMock()
        user.id = tg_id
        user.username = username
        user.first_name = first_name

        message = AsyncMock()
        update = MagicMock()
        update.effective_user = user
        update.message = message
        update.callback_query = None

        context = MagicMock()
        context.user_data = {}

        return update, context, message

    async def test_1_no_active_campaign(self):
        """Test: No active campaign -> correct message."""
        update, context, message = self._create_mock_update_and_context(self.test_tg_id_1)

        res = await bot.start(update, context)
        self.assertEqual(res, bot.ConversationHandler.END)
        message.reply_text.assert_called_once_with(
            "حالياً ما كاين حتى عرض مفتوح.\n"
            "تابع القناة باش تعرف ملي يفتح عرض جديد."
        )

    async def test_2_to_6_active_campaign_display(self):
        """Test: Active campaign -> Promo code, description, instructions, requirements, image displayed."""
        camp_id = create_campaign(promo_code=self.test_code, max_requests=10)
        self.campaigns_to_cleanup.append(camp_id)
        activate_campaign(camp_id)

        update, context, message = self._create_mock_update_and_context(self.test_tg_id_1)
        res = await bot.start(update, context)

        self.assertEqual(res, bot.WAITING_FOR_SCREENSHOT)
        message.reply_text.assert_called_once()
        call_text = message.reply_text.call_args[0][0]

        # Verify promo code, description, instructions, requirements
        self.assertIn("MRC456", call_text)
        self.assertIn("50% deposit bonus", call_text)
        self.assertIn("1. Create account", call_text)
        self.assertIn("Screenshot must display Site ID", call_text)

        # Verify button
        reply_markup = message.reply_text.call_args[1].get("reply_markup")
        self.assertIsNotNone(reply_markup)
        button_text = reply_markup.inline_keyboard[0][0].text
        self.assertEqual(button_text, "✅ فهمت، نبدأ")

    async def test_7_to_12_full_successful_request_flow(self):
        """
        Test:
        7. Customer starts request
        8. Screenshot is accepted
        9. Valid Site ID formats accepted (e.g. ID: 38938378)
        10. Request created as PENDING
        11. Campaign pending count increases
        12. Confirmation message displayed with details
        """
        camp_id = create_campaign(promo_code=self.test_code, max_requests=10)
        self.campaigns_to_cleanup.append(camp_id)
        activate_campaign(camp_id)

        # 1. /start
        update, context, message = self._create_mock_update_and_context(self.test_tg_id_1)
        res_start = await bot.start(update, context)
        self.assertEqual(res_start, bot.WAITING_FOR_SCREENSHOT)

        # 2. Click start button
        cb_query = AsyncMock()
        cb_query.message = AsyncMock()
        update.callback_query = cb_query
        res_btn = await bot.handle_start_submission(update, context)
        self.assertEqual(res_btn, bot.WAITING_FOR_SCREENSHOT)
        cb_query.message.reply_text.assert_called_once_with("📸 صيفط Screenshot حسب المثال اللي فوق.")

        # 3. Send Photo
        update.callback_query = None
        mock_photo = MagicMock()
        mock_photo.file_id = "test_telegram_file_id_abc123"
        message.photo = [mock_photo]
        message.reset_mock()

        res_photo = await bot.handle_screenshot(update, context)
        self.assertEqual(res_photo, bot.WAITING_FOR_SITE_ID)
        self.assertEqual(context.user_data["screenshot_file_id"], "test_telegram_file_id_abc123")
        message.reply_text.assert_called_once_with(
            "🆔 دابا صيفط Site ID ديالك مكتوب.\n"
            "مثال:\n"
            "ID:38938378"
        )

        # 4. Send Site ID
        message.photo = None
        message.text = "ID: 38938378"
        message.reset_mock()

        res_site_id = await bot.handle_site_id(update, context)
        self.assertEqual(res_site_id, bot.ConversationHandler.END)

        # Verify confirmation message
        message.reply_text.assert_called_once()
        conf_msg = message.reply_text.call_args[0][0]
        self.assertIn("تسجل الطلب ديالك بنجاح", conf_msg)
        self.assertIn("MRC456", conf_msg)
        self.assertIn("38938378", conf_msg)
        self.assertIn("قيد المراجعة", conf_msg)

        # Verify database record
        user_rec = get_user_by_telegram_id(self.test_tg_id_1)
        self.assertIsNotNone(user_rec)
        db_user_id = user_rec["id"]

        with get_connection() as conn:
            req = conn.execute(
                "SELECT * FROM requests WHERE campaign_id = ? AND user_id = ?",
                (camp_id, db_user_id)
            ).fetchone()
            self.assertIsNotNone(req)
            self.assertEqual(req["site_id"], "38938378")
            self.assertEqual(req["screenshot_file_id"], "test_telegram_file_id_abc123")
            self.assertEqual(req["status"], "pending")

        # Verify pending count
        self.assertEqual(get_campaign_pending_count(camp_id), 1)

    async def test_10_invalid_site_id_rejected(self):
        """Test: Invalid site ID format is rejected with error prompt."""
        camp_id = create_campaign(promo_code=self.test_code, max_requests=10)
        self.campaigns_to_cleanup.append(camp_id)
        activate_campaign(camp_id)

        update, context, message = self._create_mock_update_and_context(self.test_tg_id_1)
        context.user_data["campaign_id"] = camp_id
        context.user_data["promo_code"] = self.test_code
        context.user_data["screenshot_file_id"] = "file_123"

        message.text = "invalid site id with spaces and @ symbols !!!"
        res = await bot.handle_site_id(update, context)
        self.assertEqual(res, bot.WAITING_FOR_SITE_ID)
        message.reply_text.assert_called_once_with(
            "❌ ما قدرتش نقرأ الـID.\n"
            "صيفطو بهذا الشكل:\n"
            "ID:38938378"
        )

    async def test_13_14_capacity_and_full_transition(self):
        """Test: Campaign becomes FULL at capacity and new customer cannot submit."""
        camp_id = create_campaign(promo_code=self.test_code, max_requests=1)
        self.campaigns_to_cleanup.append(camp_id)
        activate_campaign(camp_id)

        # Customer 1 submits request
        update1, ctx1, msg1 = self._create_mock_update_and_context(self.test_tg_id_1)
        await bot.start(update1, ctx1)
        mock_photo = MagicMock()
        mock_photo.file_id = "photo_1"
        msg1.photo = [mock_photo]
        await bot.handle_screenshot(update1, ctx1)
        msg1.photo = None
        msg1.text = "38938378"
        await bot.handle_site_id(update1, ctx1)

        # Confirm campaign is now FULL
        camp = get_campaign_by_id(camp_id)
        self.assertEqual(camp["status"], "full")
        self.assertFalse(can_accept_request(camp_id))

        # Customer 2 sends /start
        update2, ctx2, msg2 = self._create_mock_update_and_context(self.test_tg_id_2)
        res2 = await bot.start(update2, ctx2)
        self.assertEqual(res2, bot.ConversationHandler.END)
        msg2.reply_text.assert_called_once_with(
            "حالياً ما كاين حتى عرض مفتوح.\n"
            "تابع القناة باش تعرف ملي يفتح عرض جديد."
        )

    async def test_15_accepted_user_rejected(self):
        """Test: User with previously ACCEPTED request for same promo code is rejected."""
        camp_id = create_campaign(promo_code=self.test_code, max_requests=10)
        self.campaigns_to_cleanup.append(camp_id)
        activate_campaign(camp_id)

        # Setup accepted request for user 1
        db_user_id = create_or_update_user(self.test_tg_id_1, "user1", "User1")
        req_id = create_request(camp_id, db_user_id, site_id="11111", status="pending")
        update_request_status(req_id, status="accepted")

        # User 1 sends /start
        update, context, message = self._create_mock_update_and_context(self.test_tg_id_1)
        res = await bot.start(update, context)
        self.assertEqual(res, bot.ConversationHandler.END)
        message.reply_text.assert_called_once_with(
            "❌ سبق ليك استفدتي من هاد Promo Code.\n"
            "كل شخص يقدر يستافد من هاد الكود مرة وحدة."
        )

    async def test_16_rejected_user_can_retry(self):
        """Test: User with previously REJECTED request can submit again if capacity exists."""
        camp_id = create_campaign(promo_code=self.test_code, max_requests=10)
        self.campaigns_to_cleanup.append(camp_id)
        activate_campaign(camp_id)

        # Setup rejected request for user 1
        db_user_id = create_or_update_user(self.test_tg_id_1, "user1", "User1")
        req_id = create_request(camp_id, db_user_id, site_id="11111", status="pending")
        update_request_status(req_id, status="rejected")

        # User 1 sends /start
        update, context, message = self._create_mock_update_and_context(self.test_tg_id_1)
        res = await bot.start(update, context)
        self.assertEqual(res, bot.WAITING_FOR_SCREENSHOT)
        message.reply_text.assert_called_once()
        self.assertIn("MRC456", message.reply_text.call_args[0][0])

    async def test_17_duplicate_pending_rejected(self):
        """Test: Same user cannot create duplicate pending requests for same campaign."""
        camp_id = create_campaign(promo_code=self.test_code, max_requests=10)
        self.campaigns_to_cleanup.append(camp_id)
        activate_campaign(camp_id)

        db_user_id = create_or_update_user(self.test_tg_id_1, "user1", "User1")
        create_request(camp_id, db_user_id, site_id="11111", status="pending")

        # User 1 sends /start again
        update, context, message = self._create_mock_update_and_context(self.test_tg_id_1)
        res = await bot.start(update, context)
        self.assertEqual(res, bot.ConversationHandler.END)
        message.reply_text.assert_called_once_with(
            "⏳ عندك طلب قيد المراجعة فهاد العرض.\n"
            "غادي يتم التواصل معاك قريباً."
        )


if __name__ == "__main__":
    unittest.main()
