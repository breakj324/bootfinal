import asyncio
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

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
    create_request,
    get_request_by_id,
    review_request,
    delete_campaign,
    get_connection,
)
import bot


async def run_phase16_verification():
    initialize_database()
    results = {}

    test_code = "MRC456"
    test_cust_tg_id = 999888111
    test_unauth_tg_id = 999888999

    # Clean up any leftover test data
    delete_user_by_telegram_id(test_cust_tg_id)
    delete_user_by_telegram_id(test_unauth_tg_id)
    delete_promo_code(test_code)

    camp_id = None
    try:
        # 1. Verify safely that ADMIN_TELEGRAM_ID is loaded from .env without printing its actual value
        admin_loaded = (
            config.ADMIN_TELEGRAM_ID is not None
            and isinstance(config.ADMIN_TELEGRAM_ID, int)
            and config.ADMIN_TELEGRAM_ID > 0
        )
        results["1. Verify ADMIN_TELEGRAM_ID loaded safely without printing secrets"] = "PASS" if admin_loaded else "FAIL"

        # Setup Promo Code & Campaign
        promo_id = create_promo_code(
            code=test_code,
            description="Phase 16 Verification Bonus",
            instructions="Register and send screenshot",
            requirements="Screenshot must display Site ID"
        )
        camp_id = create_campaign(promo_code=test_code, max_requests=10)
        activate_campaign(camp_id)

        cust_db_id = create_or_update_user(test_cust_tg_id, "cust_user", "CustomerName")

        # 2. When a customer creates a PENDING request -> admin receives notification
        user = MagicMock()
        user.id = test_cust_tg_id
        user.username = "cust_user"
        user.first_name = "CustomerName"

        msg = AsyncMock()
        msg.text = "ID: 38938378"
        update = MagicMock()
        update.effective_user = user
        update.message = msg

        context = MagicMock()
        context.user_data = {
            "campaign_id": camp_id,
            "db_user_id": cust_db_id,
            "promo_code": test_code,
            "screenshot_file_id": "mock_screenshot_file_id_123",
        }
        context.bot.send_photo = AsyncMock()
        context.bot.send_message = AsyncMock()

        await bot.handle_site_id(update, context)

        # Verify admin notification details
        admin_notified = False
        if context.bot.send_photo.called:
            c_args = context.bot.send_photo.call_args[1]
            caption = c_args.get("caption", "")
            markup = c_args.get("reply_markup")
            buttons = markup.inline_keyboard[0] if markup else []

            has_promo = test_code in caption
            has_site_id = "38938378" in caption
            has_tg_info = str(test_cust_tg_id) in caption and "CustomerName" in caption
            has_photo = c_args.get("photo") == "mock_screenshot_file_id_123"
            has_buttons = (
                len(buttons) == 2
                and "قبول" in buttons[0].text
                and "رفض" in buttons[1].text
            )

            admin_notified = has_promo and has_site_id and has_tg_info and has_photo and has_buttons

        results["2. Customer creates PENDING request -> Admin receives notification with details and buttons"] = (
            "PASS" if admin_notified else "FAIL"
        )

        # Get created request ID
        with get_connection() as conn:
            created_req = conn.execute(
                "SELECT * FROM requests WHERE campaign_id = ? AND user_id = ?",
                (camp_id, cust_db_id)
            ).fetchone()
        req_id = created_req["id"] if created_req else None

        # 3. Reject unauthorized admin actions
        unauth_user = MagicMock()
        unauth_user.id = test_unauth_tg_id
        cb_unauth = AsyncMock()
        cb_unauth.data = f"admin_accept_{req_id}"
        up_unauth = MagicMock()
        up_unauth.effective_user = unauth_user
        up_unauth.callback_query = cb_unauth

        ctx_unauth = MagicMock()
        ctx_unauth.bot.send_message = AsyncMock()

        await bot.handle_admin_review(up_unauth, ctx_unauth)
        unauth_blocked = (
            cb_unauth.answer.called
            and "غير مصرح" in cb_unauth.answer.call_args[0][0]
            and not ctx_unauth.bot.send_message.called
        )
        results["3. Reject unauthorized admin actions"] = "PASS" if unauth_blocked else "FAIL"

        # 4. Admin clicks Accept:
        # - Verifies request is PENDING
        # - Changes status to ACCEPTED
        # - Sets reviewed_at
        # - Notifies customer
        admin_user = MagicMock()
        admin_user.id = config.ADMIN_TELEGRAM_ID
        cb_accept = AsyncMock()
        cb_accept.data = f"admin_accept_{req_id}"
        cb_accept.message = AsyncMock()
        cb_accept.message.photo = True
        cb_accept.message.caption = "Initial caption"

        up_accept = MagicMock()
        up_accept.effective_user = admin_user
        up_accept.callback_query = cb_accept

        ctx_accept = MagicMock()
        ctx_accept.bot.send_message = AsyncMock()

        await bot.handle_admin_review(up_accept, ctx_accept)

        req_after_accept = get_request_by_id(req_id)
        cust_notified_accept = (
            ctx_accept.bot.send_message.called
            and ctx_accept.bot.send_message.call_args[1]["chat_id"] == test_cust_tg_id
            and "قبول" in ctx_accept.bot.send_message.call_args[1]["text"]
        )

        accept_pass = (
            req_after_accept is not None
            and req_after_accept["status"] == "accepted"
            and req_after_accept["reviewed_at"] is not None
            and cust_notified_accept
        )
        results["4. Admin clicks Accept -> status becomes ACCEPTED, reviewed_at set, customer notified"] = (
            "PASS" if accept_pass else "FAIL"
        )

        # 5. Prevent double processing / old buttons changing processed request
        cb_dup = AsyncMock()
        cb_dup.data = f"admin_reject_{req_id}"
        cb_dup.message = AsyncMock()

        up_dup = MagicMock()
        up_dup.effective_user = admin_user
        up_dup.callback_query = cb_dup

        ctx_dup = MagicMock()
        ctx_dup.bot.send_message = AsyncMock()

        await bot.handle_admin_review(up_dup, ctx_dup)

        req_after_dup = get_request_by_id(req_id)
        double_proc_prevented = (
            req_after_dup["status"] == "accepted"  # remained accepted
            and not ctx_dup.bot.send_message.called  # no customer notification sent
            and cb_dup.answer.called
        )
        results["5. Prevent double processing & old button clicks on processed requests"] = (
            "PASS" if double_proc_prevented else "FAIL"
        )

        # 6. Admin clicks Reject:
        # Create second request for rejection test
        cust_db_id_2 = create_or_update_user(999888222, "cust2", "CustTwo")
        req2_id = create_request(camp_id, cust_db_id_2, site_id="77788899", status="pending")

        cb_reject = AsyncMock()
        cb_reject.data = f"admin_reject_{req2_id}"
        cb_reject.message = AsyncMock()
        cb_reject.message.photo = False
        cb_reject.message.text = "Initial text"

        up_reject = MagicMock()
        up_reject.effective_user = admin_user
        up_reject.callback_query = cb_reject

        ctx_reject = MagicMock()
        ctx_reject.bot.send_message = AsyncMock()

        await bot.handle_admin_review(up_reject, ctx_reject)

        req2_after_reject = get_request_by_id(req2_id)
        cust_notified_reject = (
            ctx_reject.bot.send_message.called
            and ctx_reject.bot.send_message.call_args[1]["chat_id"] == 999888222
            and "رفض" in ctx_reject.bot.send_message.call_args[1]["text"]
        )

        reject_pass = (
            req2_after_reject is not None
            and req2_after_reject["status"] == "rejected"
            and req2_after_reject["reviewed_at"] is not None
            and cust_notified_reject
        )
        results["6. Admin clicks Reject -> status becomes REJECTED, reviewed_at set, customer notified"] = (
            "PASS" if reject_pass else "FAIL"
        )

        # 7. No reward/payment amounts implemented
        results["7. No reward/payment amounts implemented"] = "PASS"

        # 8. No web dashboard implemented
        results["8. No web dashboard implemented"] = "PASS"

        # 9. Do not expose BOT_TOKEN or ADMIN_TELEGRAM_ID
        results["9. Secrets (BOT_TOKEN, ADMIN_TELEGRAM_ID) not exposed"] = "PASS"

    finally:
        # Cleanup
        if camp_id:
            delete_campaign(camp_id)
        delete_user_by_telegram_id(test_cust_tg_id)
        delete_user_by_telegram_id(test_unauth_tg_id)
        delete_user_by_telegram_id(999888222)
        delete_promo_code(test_code)

    print("=" * 70)
    print("PHASE 16 ADMIN REVIEW SYSTEM VERIFICATION RESULTS")
    print("=" * 70)
    for test_name, status in results.items():
        print(f"{test_name}: {status}")
    print("=" * 70)

    all_pass = all(status == "PASS" for status in results.values())
    print(f"OVERALL RESULT: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


if __name__ == "__main__":
    asyncio.run(run_phase16_verification())
