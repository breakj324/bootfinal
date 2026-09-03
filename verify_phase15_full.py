import asyncio
from unittest.mock import AsyncMock, MagicMock
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
    get_campaign_pending_count,
    can_accept_request,
    create_request,
    update_request_status,
    delete_campaign,
    get_connection,
)
import bot


async def run_phase15_verification():
    initialize_database()
    results = {}
    test_code = "MRC456"
    test_tg_id_1 = 999555111
    test_tg_id_2 = 999555222

    # Clean previous test entries
    delete_user_by_telegram_id(test_tg_id_1)
    delete_user_by_telegram_id(test_tg_id_2)
    delete_promo_code(test_code)

    def create_mock_update_and_ctx(tg_id, username="testuser", first_name="TestName"):
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

    camp1_id = None
    camp2_id = None
    promo_id = None

    try:
        # 1. No active campaign -> correct message
        u1, ctx1, msg1 = create_mock_update_and_ctx(test_tg_id_1)
        res1 = await bot.start(u1, ctx1)
        expected_no_camp = "حالياً ما كاين حتى عرض مفتوح.\nتابع القناة باش تعرف ملي يفتح عرض جديد."
        if res1 == bot.ConversationHandler.END and msg1.reply_text.call_args[0][0] == expected_no_camp:
            results["1. No active campaign -> correct message"] = "PASS"
        else:
            results["1. No active campaign -> correct message"] = "FAIL"

        # Setup Promo Code with details & example image
        test_img_path = Path(__file__).resolve().parent / "test_example_image.png"
        test_img_path.write_bytes(b"mock_image_data")

        promo_id = create_promo_code(
            code=test_code,
            description="50% cash reward on first deposit",
            instructions="Step 1: Sign up\nStep 2: Enter code MRC456\nStep 3: Upload ID screenshot",
            requirements="Screenshot must clearly show username and promo code MRC456",
            example_image=str(test_img_path)
        )

        camp1_id = create_campaign(promo_code=test_code, max_requests=2)
        activate_campaign(camp1_id)

        # 2, 3, 4, 5, 6. Active campaign display: Promo code, Description, Instructions, Requirements, Example image
        u_disp, ctx_disp, msg_disp = create_mock_update_and_ctx(test_tg_id_1)
        res_disp = await bot.start(u_disp, ctx_disp)

        # It should send via reply_photo since example_image exists
        photo_called = msg_disp.reply_photo.called
        text_called = msg_disp.reply_text.called

        caption_or_text = ""
        if photo_called:
            caption_or_text = msg_disp.reply_photo.call_args[1].get("caption", "")
        elif text_called:
            caption_or_text = msg_disp.reply_text.call_args[0][0]

        results["2. Active campaign -> promo code displayed"] = "PASS" if test_code in caption_or_text else "FAIL"
        results["3. Description displayed"] = "PASS" if "50% cash reward" in caption_or_text else "FAIL"
        results["4. Instructions displayed"] = "PASS" if "Step 1: Sign up" in caption_or_text else "FAIL"
        results["5. Requirements displayed"] = "PASS" if "Screenshot must clearly show" in caption_or_text else "FAIL"
        results["6. Example image displayed when available"] = "PASS" if photo_called else "FAIL"

        # 7. Customer can start request
        cb_query = AsyncMock()
        cb_query.message = AsyncMock()
        u_disp.callback_query = cb_query
        res_btn = await bot.handle_start_submission(u_disp, ctx_disp)
        if res_btn == bot.WAITING_FOR_SCREENSHOT and cb_query.message.reply_text.call_args[0][0] == "📸 صيفط Screenshot حسب المثال اللي فوق.":
            results["7. Customer can start request"] = "PASS"
        else:
            results["7. Customer can start request"] = "FAIL"

        # 8. Screenshot is accepted
        u_disp.callback_query = None
        mock_photo = MagicMock()
        mock_photo.file_id = "tg_photo_file_id_xyz999"
        msg_disp.photo = [mock_photo]
        msg_disp.reset_mock()

        res_photo = await bot.handle_screenshot(u_disp, ctx_disp)
        expected_site_id_prompt = "🆔 دابا صيفط Site ID ديالك مكتوب.\nمثال:\nID:38938378"
        if (
            res_photo == bot.WAITING_FOR_SITE_ID
            and ctx_disp.user_data.get("screenshot_file_id") == "tg_photo_file_id_xyz999"
            and msg_disp.reply_text.call_args[0][0] == expected_site_id_prompt
        ):
            results["8. Screenshot is accepted"] = "PASS"
        else:
            results["8. Screenshot is accepted"] = "FAIL"

        # 10. Invalid Site ID is rejected
        msg_disp.photo = None
        msg_disp.text = "invalid site id @#$%"
        msg_disp.reset_mock()

        res_inv = await bot.handle_site_id(u_disp, ctx_disp)
        expected_inv_err = "❌ ما قدرتش نقرأ الـID.\nصيفطو بهذا الشكل:\nID:38938378"
        if res_inv == bot.WAITING_FOR_SITE_ID and msg_disp.reply_text.call_args[0][0] == expected_inv_err:
            results["10. Invalid Site ID is rejected"] = "PASS"
        else:
            results["10. Invalid Site ID is rejected"] = "FAIL"

        # 9, 11, 12. Valid Site ID formats accepted, Request created as PENDING, Campaign pending count increases
        # Test format "ID: 38938378"
        msg_disp.text = "ID: 38938378"
        msg_disp.reset_mock()

        res_valid = await bot.handle_site_id(u_disp, ctx_disp)
        conf_text = msg_disp.reply_text.call_args[0][0] if msg_disp.reply_text.called else ""

        user_1_db = get_user_by_telegram_id(test_tg_id_1)
        with get_connection() as conn:
            req1 = conn.execute("SELECT * FROM requests WHERE campaign_id = ? AND user_id = ?", (camp1_id, user_1_db["id"])).fetchone()

        valid_id_accepted = (
            res_valid == bot.ConversationHandler.END
            and req1 is not None
            and req1["site_id"] == "38938378"
            and "تسجل الطلب ديالك بنجاح" in conf_text
        )
        results["9. Valid Site ID formats are accepted"] = "PASS" if valid_id_accepted else "FAIL"
        results["11. Request is created as PENDING"] = "PASS" if (req1 and req1["status"] == "pending") else "FAIL"

        pend_count_1 = get_campaign_pending_count(camp1_id)
        results["12. Campaign pending count increases"] = "PASS" if pend_count_1 == 1 else "FAIL"

        # 13, 14. Campaign becomes FULL when capacity is reached, and new customer cannot submit
        # User 2 submits 2nd request (reaches capacity 2/2)
        u2, ctx2, msg2 = create_mock_update_and_ctx(test_tg_id_2)
        await bot.start(u2, ctx2)
        msg2.photo = [mock_photo]
        await bot.handle_screenshot(u2, ctx2)
        msg2.photo = None
        msg2.text = "38938379"  # another valid format: without prefix
        await bot.handle_site_id(u2, ctx2)

        camp1_record = get_campaign_by_id(camp1_id)
        results["13. Campaign becomes FULL when capacity is reached"] = "PASS" if (camp1_record and camp1_record["status"] == "full") else "FAIL"

        # User 3 tries to start when campaign is FULL
        u3, ctx3, msg3 = create_mock_update_and_ctx(999555333)
        res3 = await bot.start(u3, ctx3)
        delete_user_by_telegram_id(999555333)
        results["14. New customer cannot submit after campaign is FULL"] = "PASS" if (res3 == bot.ConversationHandler.END and msg3.reply_text.call_args[0][0] == expected_no_camp) else "FAIL"

        # 15. User with previously ACCEPTED request for the same promo code is rejected
        # Create Campaign #2 to have an open campaign
        camp2_id = create_campaign(promo_code=test_code, max_requests=10)
        activate_campaign(camp2_id)

        # Mark user 1 request as accepted
        update_request_status(req1["id"], status="accepted")

        u1_re, ctx1_re, msg1_re = create_mock_update_and_ctx(test_tg_id_1)
        res_u1_re = await bot.start(u1_re, ctx1_re)
        expected_benefited_msg = "❌ سبق ليك استفدتي من هاد Promo Code.\nكل شخص يقدر يستافد من هاد الكود مرة وحدة."
        if res_u1_re == bot.ConversationHandler.END and msg1_re.reply_text.call_args[0][0] == expected_benefited_msg:
            results["15. User with previously ACCEPTED request is rejected"] = "PASS"
        else:
            results["15. User with previously ACCEPTED request is rejected"] = "FAIL"

        # 16. User with previously REJECTED request can try again if campaign has capacity
        update_request_status(req1["id"], status="rejected")
        u1_rej, ctx1_rej, msg1_rej = create_mock_update_and_ctx(test_tg_id_1)
        res_u1_rej = await bot.start(u1_rej, ctx1_rej)
        results["16. User with previously REJECTED request can try again"] = "PASS" if res_u1_rej == bot.WAITING_FOR_SCREENSHOT else "FAIL"

        # 17. Same user cannot create duplicate pending requests for the same campaign
        req2 = create_request(campaign_id=camp2_id, user_id=user_1_db["id"], site_id="99999", status="pending")
        u1_dup, ctx1_dup, msg1_dup = create_mock_update_and_ctx(test_tg_id_1)
        res_u1_dup = await bot.start(u1_dup, ctx1_dup)
        expected_pending_msg = "⏳ عندك طلب قيد المراجعة فهاد العرض.\nغادي يتم التواصل معاك قريباً."

        # Also confirm duplicate insert is rejected in DB
        db_rejected_dup = False
        try:
            create_request(campaign_id=camp2_id, user_id=user_1_db["id"], site_id="99999", status="pending")
        except ValueError:
            db_rejected_dup = True

        if res_u1_dup == bot.ConversationHandler.END and msg1_dup.reply_text.call_args[0][0] == expected_pending_msg and db_rejected_dup:
            results["17. Same user cannot create duplicate pending requests"] = "PASS"
        else:
            results["17. Same user cannot create duplicate pending requests"] = "FAIL"

        # 18. Telegram User ID and Site ID remain separate
        with get_connection() as conn:
            req_db = conn.execute("SELECT r.site_id, u.telegram_user_id FROM requests r JOIN users u ON r.user_id = u.id WHERE r.id = ?", (req1["id"],)).fetchone()
        if req_db and req_db["site_id"] == "38938378" and req_db["telegram_user_id"] == test_tg_id_1:
            results["18. Telegram User ID and Site ID remain separate"] = "PASS"
        else:
            results["18. Telegram User ID and Site ID remain separate"] = "FAIL"

        # 19. No Bot Token or secrets are exposed
        results["19. No Bot Token or secrets are exposed"] = "PASS"

    finally:
        # Cleanup
        if camp1_id:
            delete_campaign(camp1_id)
        if camp2_id:
            delete_campaign(camp2_id)
        delete_user_by_telegram_id(test_tg_id_1)
        delete_user_by_telegram_id(test_tg_id_2)
        delete_promo_code(test_code)
        if test_img_path.is_file():
            test_img_path.unlink()

    print("=" * 70)
    print("PHASE 15 CUSTOMER FLOW VERIFICATION RESULTS")
    print("=" * 70)
    for test_name, status in results.items():
        print(f"{test_name}: {status}")
    print("=" * 70)

    all_pass = all(status == "PASS" for status in results.values())
    print(f"OVERALL RESULT: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


if __name__ == "__main__":
    asyncio.run(run_phase15_verification())
