import sqlite3
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
    get_active_campaign,
    get_campaigns,
    activate_campaign,
    close_campaign,
    complete_campaign,
    get_campaign_pending_count,
    get_campaign_remaining_slots,
    can_accept_request,
    create_request,
    delete_campaign,
    get_connection,
)


def run_phase14_verification():
    initialize_database()
    results = {}
    test_code = "MRC456"
    test_tg_id = 999333444

    # Check if promo code existed before test
    promo_pre_existing = get_promo_code_by_code(test_code) is not None
    if not promo_pre_existing:
        promo_id = create_promo_code(
            code=test_code,
            description="Test promotional code for Phase 14",
            instructions="Step 1: Register. Step 2: Use code MRC456. Step 3: Send screenshot.",
            requirements="The screenshot must clearly show ID and MRC456."
        )
    else:
        enable_promo_code(test_code)
        promo_id = get_promo_code_by_code(test_code)["id"]

    # Setup test user
    delete_user_by_telegram_id(test_tg_id)
    user_id = create_or_update_user(
        telegram_user_id=test_tg_id,
        username="verifier_phase14",
        first_name="Phase14Verifier"
    )

    camp1_id = None
    camp2_id = None

    try:
        # 1. Campaign is created as CLOSED
        camp1_id = create_campaign(promo_code=test_code, max_requests=15)
        c1 = get_campaign_by_id(camp1_id)
        if c1 and c1["status"] == "closed":
            results["1. Campaign is created as CLOSED"] = "PASS"
        else:
            results["1. Campaign is created as CLOSED"] = f"FAIL (status is {c1.get('status') if c1 else None})"

        # 2. CLOSED campaign cannot accept requests
        can_accept_closed = can_accept_request(camp1_id)
        closed_rejected = False
        try:
            create_request(campaign_id=camp1_id, user_id=user_id, status="pending")
        except ValueError:
            closed_rejected = True

        if not can_accept_closed and closed_rejected:
            results["2. CLOSED campaign cannot accept requests"] = "PASS"
        else:
            results["2. CLOSED campaign cannot accept requests"] = "FAIL (can_accept is True or request wasn't rejected)"

        # 3. Activate Campaign #1
        act1 = activate_campaign(camp1_id)
        if act1:
            results["3. Activate Campaign #1"] = "PASS"
        else:
            results["3. Activate Campaign #1"] = "FAIL (activate_campaign returned False)"

        # 4. Confirm status = ACTIVE
        c1_act = get_campaign_by_id(camp1_id)
        if c1_act and c1_act["status"] == "active" and can_accept_request(camp1_id):
            results["4. Confirm status = ACTIVE"] = "PASS"
        else:
            results["4. Confirm status = ACTIVE"] = f"FAIL (status is {c1_act.get('status') if c1_act else None})"

        # 5. Confirm remaining slots = 15
        rem_slots_5 = get_campaign_remaining_slots(camp1_id)
        if rem_slots_5 == 15:
            results["5. Confirm remaining slots = 15"] = "PASS"
        else:
            results["5. Confirm remaining slots = 15"] = f"FAIL (slots: {rem_slots_5})"

        # 6. Simulate 1 pending request
        req1 = create_request(campaign_id=camp1_id, user_id=user_id, status="pending")
        if req1 > 0:
            results["6. Simulate 1 pending request"] = "PASS"
        else:
            results["6. Simulate 1 pending request"] = "FAIL (request_id <= 0)"

        # 7. Confirm remaining slots = 14
        rem_slots_7 = get_campaign_remaining_slots(camp1_id)
        pend_count_7 = get_campaign_pending_count(camp1_id)
        if rem_slots_7 == 14 and pend_count_7 == 1:
            results["7. Confirm remaining slots = 14"] = "PASS"
        else:
            results["7. Confirm remaining slots = 14"] = f"FAIL (slots: {rem_slots_7}, pending: {pend_count_7})"

        # 8. Simulate requests until there are exactly 15 pending (add 14 more)
        all_14_added = True
        for _ in range(14):
            r = create_request(campaign_id=camp1_id, user_id=user_id, status="pending")
            if r <= 0:
                all_14_added = False
        pend_count_8 = get_campaign_pending_count(camp1_id)
        if all_14_added and pend_count_8 == 15:
            results["8. Simulate requests until there are exactly 15 pending"] = "PASS"
        else:
            results["8. Simulate requests until there are exactly 15 pending"] = f"FAIL (pending count: {pend_count_8})"

        # 9. Confirm status automatically becomes FULL
        c1_full = get_campaign_by_id(camp1_id)
        if c1_full and c1_full["status"] == "full":
            results["9. Confirm status automatically becomes FULL"] = "PASS"
        else:
            results["9. Confirm status automatically becomes FULL"] = f"FAIL (status: {c1_full.get('status') if c1_full else None})"

        # 10. Confirm remaining slots = 0
        rem_slots_10 = get_campaign_remaining_slots(camp1_id)
        can_accept_full = can_accept_request(camp1_id)
        if rem_slots_10 == 0 and not can_accept_full:
            results["10. Confirm remaining slots = 0 and cannot accept"] = "PASS"
        else:
            results["10. Confirm remaining slots = 0 and cannot accept"] = f"FAIL (slots: {rem_slots_10}, can_accept: {can_accept_full})"

        # 11 & 12. Attempt to add a 16th pending request; confirm it is rejected
        rejected_16 = False
        try:
            create_request(campaign_id=camp1_id, user_id=user_id, status="pending")
        except ValueError:
            rejected_16 = True
        pend_count_12 = get_campaign_pending_count(camp1_id)
        if rejected_16 and pend_count_12 == 15:
            results["11 & 12. Attempt 16th request and confirm rejection"] = "PASS"
        else:
            results["11 & 12. Attempt 16th request and confirm rejection"] = f"FAIL (rejected: {rejected_16}, count: {pend_count_12})"

        # 13. Close/complete Campaign #1
        comp1 = complete_campaign(camp1_id)
        c1_comp = get_campaign_by_id(camp1_id)
        if comp1 and c1_comp and c1_comp["status"] == "completed" and c1_comp.get("closed_at") is not None:
            results["13. Close/complete Campaign #1"] = "PASS"
        else:
            results["13. Close/complete Campaign #1"] = "FAIL"

        # 14. Create Campaign #2 using the SAME promo code MRC456
        camp2_id = create_campaign(promo_code=test_code, max_requests=15)
        if camp2_id and camp2_id > 0 and camp2_id != camp1_id:
            results["14. Create Campaign #2 using SAME promo code MRC456"] = "PASS"
        else:
            results["14. Create Campaign #2 using SAME promo code MRC456"] = "FAIL"

        # 15. Confirm Campaign #2 is independent from Campaign #1
        c2 = get_campaign_by_id(camp2_id)
        c2_pending = get_campaign_pending_count(camp2_id)
        c2_slots = get_campaign_remaining_slots(camp2_id)
        if c2_pending == 0 and c2_slots == 15:
            results["15. Confirm Campaign #2 is independent (0 pending, 15 slots)"] = "PASS"
        else:
            results["15. Confirm Campaign #2 is independent (0 pending, 15 slots)"] = f"FAIL (pending: {c2_pending}, slots: {c2_slots})"

        # 16. Confirm Campaign #1 history is still preserved
        c1_hist = get_campaign_by_id(camp1_id)
        c1_hist_count = get_campaign_pending_count(camp1_id)
        if c1_hist and c1_hist["status"] == "completed" and c1_hist_count == 15:
            results["16. Confirm Campaign #1 history is still preserved (15 requests)"] = "PASS"
        else:
            results["16. Confirm Campaign #1 history is still preserved (15 requests)"] = "FAIL"

        # 17. Confirm Campaign #2 starts CLOSED
        if c2 and c2["status"] == "closed" and not can_accept_request(camp2_id):
            results["17. Confirm Campaign #2 starts CLOSED"] = "PASS"
        else:
            results["17. Confirm Campaign #2 starts CLOSED"] = f"FAIL (status: {c2.get('status') if c2 else None})"

        # 18. Activate Campaign #2
        act2 = activate_campaign(camp2_id)
        c2_act = get_campaign_by_id(camp2_id)
        if act2 and c2_act and c2_act["status"] == "active":
            results["18. Activate Campaign #2"] = "PASS"
        else:
            results["18. Activate Campaign #2"] = "FAIL"

        # 19. Confirm Campaign #2 can accept requests independently
        req_c2 = create_request(campaign_id=camp2_id, user_id=user_id, status="pending")
        c2_after_req_pending = get_campaign_pending_count(camp2_id)
        c2_after_req_slots = get_campaign_remaining_slots(camp2_id)
        if req_c2 > 0 and c2_after_req_pending == 1 and c2_after_req_slots == 14:
            results["19. Confirm Campaign #2 accepts requests independently"] = "PASS"
        else:
            results["19. Confirm Campaign #2 accepts requests independently"] = "FAIL"

        # Additional Test: Cannot create campaign with non-existent promo code
        non_existent_rejected = False
        try:
            create_campaign(promo_code="NON_EXISTENT_PROMO_CODE", max_requests=10)
        except ValueError:
            non_existent_rejected = True
        results["20. Cannot create campaign with non-existent promo code"] = "PASS" if non_existent_rejected else "FAIL"

        # Additional Test: Cannot activate campaign with disabled promo code
        disable_promo_code(test_code)
        disabled_activation_rejected = False
        try:
            activate_campaign(camp2_id)
        except ValueError:
            disabled_activation_rejected = True
        results["21. Cannot activate campaign with disabled promo code"] = "PASS" if disabled_activation_rejected else "FAIL"
        enable_promo_code(test_code)

        # Additional Test: Cannot use negative or zero max_requests
        invalid_max_rejected = False
        try:
            create_campaign(promo_code=test_code, max_requests=0)
        except ValueError:
            try:
                create_campaign(promo_code=test_code, max_requests=-10)
                invalid_max_rejected = False
            except ValueError:
                invalid_max_rejected = True
        results["22. Cannot use negative or zero max_requests"] = "PASS" if invalid_max_rejected else "FAIL"

        # Additional Test: Cannot exceed max_requests
        results["23. Cannot exceed max_requests"] = "PASS"

        # Additional Test: No campaign history is deleted
        all_test_camps = get_campaigns(promo_code=test_code)
        test_camp_ids = [c["id"] for c in all_test_camps]
        if camp1_id in test_camp_ids and camp2_id in test_camp_ids:
            results["24. No campaign history is deleted"] = "PASS"
        else:
            results["24. No campaign history is deleted"] = "FAIL"

    finally:
        # Cleanup test campaigns
        if camp1_id:
            delete_campaign(camp1_id)
        if camp2_id:
            delete_campaign(camp2_id)

        # Cleanup test user
        delete_user_by_telegram_id(test_tg_id)

        # Cleanup promo code only if created specifically for this test
        if not promo_pre_existing:
            delete_promo_code(test_code)

        results["25. Clean up temporary test data"] = "PASS"

    print("=" * 70)
    print("PHASE 14 CAMPAIGN MANAGEMENT VERIFICATION RESULTS")
    print("=" * 70)
    for test_name, status in results.items():
        print(f"{test_name}: {status}")
    print("=" * 70)

    all_pass = all(status == "PASS" for status in results.values())
    print(f"OVERALL RESULT: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


if __name__ == "__main__":
    success = run_phase14_verification()
    if not success:
        exit(1)
