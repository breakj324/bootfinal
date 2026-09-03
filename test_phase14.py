import unittest
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
)


class TestPhase14CampaignManagement(unittest.TestCase):
    def setUp(self):
        initialize_database()
        self.test_code = "MRC456"
        self.test_tg_id = 999111222

        # Create test user for submitting requests
        delete_user_by_telegram_id(self.test_tg_id)
        self.user_id = create_or_update_user(
            telegram_user_id=self.test_tg_id,
            username="tester_phase14",
            first_name="Phase14Tester"
        )

        # Check if MRC456 exists; if not, create it
        self.promo = get_promo_code_by_code(self.test_code)
        self.created_promo_for_test = False
        if not self.promo:
            self.promo_id = create_promo_code(
                code=self.test_code,
                description="Test promotional code for Phase 14",
                instructions="Step 1: Register. Step 2: Use code MRC456. Step 3: Send screenshot.",
                requirements="The screenshot must clearly show ID and MRC456."
            )
            self.created_promo_for_test = True
        else:
            self.promo_id = self.promo["id"]
            enable_promo_code(self.test_code)

        self.campaigns_to_cleanup = []

    def tearDown(self):
        # Cleanup test campaigns
        for cid in self.campaigns_to_cleanup:
            delete_campaign(cid)

        # Cleanup test user
        delete_user_by_telegram_id(self.test_tg_id)

        # Cleanup test promo code only if created specifically for this test
        if self.created_promo_for_test:
            delete_promo_code(self.test_code)

    def test_full_campaign_lifecycle_mrc456(self):
        """
        Complete 19-step lifecycle test for Campaign #1 and Campaign #2 with promo code MRC456.
        """
        # Step 1: Create Campaign #1 with promo code = MRC456, max_requests = 15
        camp1_id = create_campaign(promo_code=self.test_code, max_requests=15)
        self.campaigns_to_cleanup.append(camp1_id)
        self.assertGreater(camp1_id, 0)

        camp1 = get_campaign_by_id(camp1_id)
        self.assertEqual(camp1["status"], "closed", "Step 1: Campaign should start as CLOSED")

        # Step 2: CLOSED campaign cannot accept requests
        self.assertFalse(can_accept_request(camp1_id), "Step 2: CLOSED campaign must not accept requests")
        with self.assertRaises(ValueError):
            create_request(campaign_id=camp1_id, user_id=self.user_id)

        # Step 3: Activate Campaign #1
        act_ok = activate_campaign(camp1_id)
        self.assertTrue(act_ok, "Step 3: activate_campaign should return True")

        # Step 4: Confirm status = ACTIVE
        camp1_active = get_campaign_by_id(camp1_id)
        self.assertEqual(camp1_active["status"], "active", "Step 4: Status must be ACTIVE")
        self.assertTrue(can_accept_request(camp1_id), "Step 4: ACTIVE campaign should accept requests")

        # Step 5: Confirm remaining slots = 15
        slots_start = get_campaign_remaining_slots(camp1_id)
        self.assertEqual(slots_start, 15, "Step 5: Initial remaining slots must be 15")

        # Step 6: Simulate 1 pending request
        req1 = create_request(campaign_id=camp1_id, user_id=self.user_id, status="pending")
        self.assertGreater(req1, 0, "Step 6: Request should be created")

        # Step 7: Confirm remaining slots = 14
        slots_after_1 = get_campaign_remaining_slots(camp1_id)
        self.assertEqual(slots_after_1, 14, "Step 7: Remaining slots must be 14 after 1 request")
        self.assertEqual(get_campaign_pending_count(camp1_id), 1)

        # Step 8: Simulate requests until there are exactly 15 pending (add 14 more requests from distinct users)
        for i in range(14):
            sim_u_id = create_or_update_user(telegram_user_id=888000 + i, username=f"sim_user_{i}")
            req_id = create_request(campaign_id=camp1_id, user_id=sim_u_id, status="pending")
            self.assertGreater(req_id, 0)

        self.assertEqual(get_campaign_pending_count(camp1_id), 15, "Step 8: Pending count must be 15")

        # Step 9: Confirm status automatically becomes FULL
        camp1_full = get_campaign_by_id(camp1_id)
        self.assertEqual(camp1_full["status"], "full", "Step 9: Status must automatically become FULL")

        # Step 10: Confirm remaining slots = 0
        slots_full = get_campaign_remaining_slots(camp1_id)
        self.assertEqual(slots_full, 0, "Step 10: Remaining slots must be 0")
        self.assertFalse(can_accept_request(camp1_id), "Step 10: FULL campaign cannot accept requests")

        # Step 11 & 12: Attempt to add a 16th pending request; confirm it is rejected
        sim_u_16 = create_or_update_user(telegram_user_id=888999, username="sim_user_16")
        with self.assertRaises(ValueError):
            create_request(campaign_id=camp1_id, user_id=sim_u_16, status="pending")

        # Confirm pending count still 15
        self.assertEqual(get_campaign_pending_count(camp1_id), 15, "Step 12: Pending count must remain 15")

        # Step 13: Close/complete Campaign #1
        comp_ok = complete_campaign(camp1_id)
        self.assertTrue(comp_ok, "Step 13: complete_campaign should succeed")
        camp1_comp = get_campaign_by_id(camp1_id)
        self.assertEqual(camp1_comp["status"], "completed", "Step 13: Status should be COMPLETED")
        self.assertIsNotNone(camp1_comp["closed_at"])

        # Step 14: Create Campaign #2 using the SAME promo code MRC456
        camp2_id = create_campaign(promo_code=self.test_code, max_requests=15)
        self.campaigns_to_cleanup.append(camp2_id)
        self.assertGreater(camp2_id, 0, "Step 14: Campaign #2 must be created")
        self.assertNotEqual(camp1_id, camp2_id, "Step 14: Campaign #2 must have a distinct ID")

        # Step 15: Confirm Campaign #2 is independent from Campaign #1
        camp2 = get_campaign_by_id(camp2_id)
        self.assertEqual(get_campaign_pending_count(camp2_id), 0, "Step 15: Campaign #2 pending count starts at 0")
        self.assertEqual(get_campaign_remaining_slots(camp2_id), 15, "Step 15: Campaign #2 remaining slots = 15")

        # Step 16: Confirm Campaign #1 history is still preserved
        camp1_check = get_campaign_by_id(camp1_id)
        self.assertIsNotNone(camp1_check, "Step 16: Campaign #1 must still exist")
        self.assertEqual(camp1_check["status"], "completed")
        self.assertEqual(get_campaign_pending_count(camp1_id), 15, "Step 16: Campaign #1 still has its 15 requests")

        # Step 17: Confirm Campaign #2 starts CLOSED
        self.assertEqual(camp2["status"], "closed", "Step 17: Campaign #2 must start CLOSED")
        self.assertFalse(can_accept_request(camp2_id), "Step 17: Campaign #2 cannot accept requests while CLOSED")

        # Step 18: Activate Campaign #2
        act2_ok = activate_campaign(camp2_id)
        self.assertTrue(act2_ok, "Step 18: activate_campaign on Campaign #2 should succeed")
        camp2_active = get_campaign_by_id(camp2_id)
        self.assertEqual(camp2_active["status"], "active", "Step 18: Campaign #2 status must be ACTIVE")

        # Step 19: Confirm Campaign #2 can accept requests independently
        self.assertTrue(can_accept_request(camp2_id), "Step 19: Campaign #2 must accept requests")
        req_c2 = create_request(campaign_id=camp2_id, user_id=self.user_id, status="pending")
        self.assertGreater(req_c2, 0, "Step 19: Request on Campaign #2 created successfully")
        self.assertEqual(get_campaign_pending_count(camp2_id), 1)
        self.assertEqual(get_campaign_remaining_slots(camp2_id), 14)

    def test_validation_and_business_rules(self):
        """Test business constraints and edge cases."""
        # 1. Cannot create campaign with non-existent promo code
        with self.assertRaises(ValueError):
            create_campaign(promo_code="NON_EXISTENT_CODE_XYZ", max_requests=10)

        with self.assertRaises(ValueError):
            create_campaign(promo_code=9999999, max_requests=10)

        # 2. Cannot use negative or zero max_requests
        with self.assertRaises(ValueError):
            create_campaign(promo_code=self.test_code, max_requests=0)

        with self.assertRaises(ValueError):
            create_campaign(promo_code=self.test_code, max_requests=-5)

        # 3. Cannot create / activate campaign with disabled promo code
        disable_promo_code(self.test_code)
        with self.assertRaises(ValueError):
            create_campaign(promo_code=self.test_code, max_requests=5)

        # Re-enable to create a campaign, then disable promo code and verify activation is rejected
        enable_promo_code(self.test_code)
        c_temp_id = create_campaign(promo_code=self.test_code, max_requests=5)
        self.campaigns_to_cleanup.append(c_temp_id)

        disable_promo_code(self.test_code)
        with self.assertRaises(ValueError):
            activate_campaign(c_temp_id)

        self.assertFalse(can_accept_request(c_temp_id))

        # Re-enable promo code
        enable_promo_code(self.test_code)

    def test_get_campaigns_and_get_active_campaign(self):
        """Test retrieving campaign lists and filtering."""
        c1 = create_campaign(promo_code=self.test_code, max_requests=10)
        c2 = create_campaign(promo_code=self.test_code, max_requests=20)
        self.campaigns_to_cleanup.extend([c1, c2])

        activate_campaign(c1)
        active_camp = get_active_campaign(promo_code=self.test_code)
        self.assertIsNotNone(active_camp)
        self.assertEqual(active_camp["id"], c1)

        all_camps = get_campaigns(promo_code=self.test_code)
        camp_ids = [c["id"] for c in all_camps]
        self.assertIn(c1, camp_ids)
        self.assertIn(c2, camp_ids)

        closed_camps = get_campaigns(promo_code=self.test_code, status="closed")
        closed_ids = [c["id"] for c in closed_camps]
        self.assertIn(c2, closed_ids)
        self.assertNotIn(c1, closed_ids)


if __name__ == "__main__":
    unittest.main()
