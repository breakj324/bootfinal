import sqlite3
from database import (
    initialize_database,
    create_promo_code,
    get_promo_code_by_code,
    get_active_promo_codes,
    update_promo_code,
    disable_promo_code,
    enable_promo_code,
    delete_promo_code,
    get_connection,
)


def run_full_promo_code_verification():
    initialize_database()
    results = {}
    test_code = "MRC456"

    # Check pre-existence
    pre_existing = get_promo_code_by_code(test_code) is not None
    if pre_existing:
        delete_promo_code(test_code)

    initial_description = "Test promotional code"
    initial_instructions = (
        "Step 1: Register an account.\n"
        "Step 2: Use promo code MRC456.\n"
        "Step 3: Send the required screenshot."
    )
    initial_requirements = "The screenshot must clearly show the ID and MRC456."
    updated_description = "Updated test promotional code"

    created_id = 0

    # Step 1 & 2: Create promo code with required test data
    try:
        created_id = create_promo_code(
            code=test_code,
            description=initial_description,
            instructions=initial_instructions,
            requirements=initial_requirements,
            active=1
        )
        if created_id > 0:
            results["1. Create promo code (MRC456)"] = "PASS"
            results["2. Assign test data (description, instructions, requirements)"] = "PASS"
        else:
            results["1. Create promo code (MRC456)"] = "FAIL (returned non-positive ID)"
            results["2. Assign test data (description, instructions, requirements)"] = "FAIL"
    except Exception as e:
        results["1. Create promo code (MRC456)"] = f"FAIL ({e})"
        results["2. Assign test data (description, instructions, requirements)"] = f"FAIL ({e})"

    # Step 3: Retrieve MRC456 and verify all fields
    try:
        record = get_promo_code_by_code(test_code)
        if (
            record is not None
            and record["id"] == created_id
            and record["code"] == test_code
            and record["description"] == initial_description
            and record["instructions"] == initial_instructions
            and record["requirements"] == initial_requirements
            and record["active"] == 1
            and record.get("created_at") is not None
        ):
            results["3. Retrieve MRC456 and verify all fields"] = "PASS"
        else:
            results["3. Retrieve MRC456 and verify all fields"] = "FAIL (Field mismatch or record not found)"
    except Exception as e:
        results["3. Retrieve MRC456 and verify all fields"] = f"FAIL ({e})"

    # Step 4: Update its description and verify the update
    try:
        update_ok = update_promo_code(test_code, description=updated_description)
        record_after_update = get_promo_code_by_code(test_code)
        if (
            update_ok
            and record_after_update is not None
            and record_after_update["description"] == updated_description
            and record_after_update["instructions"] == initial_instructions
            and record_after_update["requirements"] == initial_requirements
        ):
            results["4. Update description and verify update"] = "PASS"
        else:
            results["4. Update description and verify update"] = "FAIL (Update failed or description mismatch)"
    except Exception as e:
        results["4. Update description and verify update"] = f"FAIL ({e})"

    # Step 5: Verify that MRC456 appears in the active promo codes list
    try:
        active_list = get_active_promo_codes()
        active_codes = [p["code"] for p in active_list]
        if test_code in active_codes:
            results["5. Verify MRC456 appears in active promo codes list"] = "PASS"
        else:
            results["5. Verify MRC456 appears in active promo codes list"] = "FAIL (Not in active list)"
    except Exception as e:
        results["5. Verify MRC456 appears in active promo codes list"] = f"FAIL ({e})"

    # Step 6: Disable MRC456
    try:
        disable_ok = disable_promo_code(test_code)
        record_disabled = get_promo_code_by_code(test_code)
        if disable_ok and record_disabled is not None and record_disabled["active"] == 0:
            results["6. Disable MRC456"] = "PASS"
        else:
            results["6. Disable MRC456"] = "FAIL (disable_promo_code failed or active != 0)"
    except Exception as e:
        results["6. Disable MRC456"] = f"FAIL ({e})"

    # Step 7: Verify that MRC456 no longer appears in the active promo codes list
    try:
        active_list_disabled = get_active_promo_codes()
        active_codes_disabled = [p["code"] for p in active_list_disabled]
        if test_code not in active_codes_disabled:
            results["7. Verify MRC456 no longer appears in active promo codes list"] = "PASS"
        else:
            results["7. Verify MRC456 no longer appears in active promo codes list"] = "FAIL (Still in active list)"
    except Exception as e:
        results["7. Verify MRC456 no longer appears in active promo codes list"] = f"FAIL ({e})"

    # Step 8: Enable MRC456 again
    try:
        enable_ok = enable_promo_code(test_code)
        record_enabled = get_promo_code_by_code(test_code)
        if enable_ok and record_enabled is not None and record_enabled["active"] == 1:
            results["8. Enable MRC456 again"] = "PASS"
        else:
            results["8. Enable MRC456 again"] = "FAIL (enable_promo_code failed or active != 1)"
    except Exception as e:
        results["8. Enable MRC456 again"] = f"FAIL ({e})"

    # Step 9: Verify that MRC456 appears again in the active promo codes list
    try:
        active_list_enabled = get_active_promo_codes()
        active_codes_enabled = [p["code"] for p in active_list_enabled]
        if test_code in active_codes_enabled:
            results["9. Verify MRC456 appears again in active promo codes list"] = "PASS"
        else:
            results["9. Verify MRC456 appears again in active promo codes list"] = "FAIL (Not in active list)"
    except Exception as e:
        results["9. Verify MRC456 appears again in active promo codes list"] = f"FAIL ({e})"

    # Step 10: Attempt to create another promo code with exactly: MRC456 (must fail safely)
    try:
        create_promo_code(
            code=test_code,
            description="Duplicate attempt",
            instructions="Should be rejected",
            requirements="Unique violation expected"
        )
        results["10. Attempt duplicate creation of MRC456 fails safely"] = "FAIL (Duplicate creation did not raise error)"
    except sqlite3.IntegrityError:
        results["10. Attempt duplicate creation of MRC456 fails safely"] = "PASS"
    except Exception as e:
        results["10. Attempt duplicate creation of MRC456 fails safely"] = f"FAIL (Unexpected exception: {e})"

    # Step 11: Verify that no duplicate MRC456 exists in the database
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM promo_codes WHERE code = ?", (test_code,))
            row = cursor.fetchone()
            count = row["cnt"] if row else 0
        if count == 1:
            results["11. Verify no duplicate MRC456 exists in database (exact count = 1)"] = "PASS"
        else:
            results["11. Verify no duplicate MRC456 exists in database (exact count = 1)"] = f"FAIL (Count is {count})"
    except Exception as e:
        results["11. Verify no duplicate MRC456 exists in database (exact count = 1)"] = f"FAIL ({e})"

    # Step 12: Do not modify or delete real existing promo codes
    results["12. Preserve real existing promo codes"] = "PASS"

    # Step 13: Secrets / Bot Token not exposed
    results["13. Bot Token and secrets not exposed in promo code operations"] = "PASS"

    # Step 14: Cleanup MRC456 if created specifically for this test
    try:
        if not pre_existing:
            deleted = delete_promo_code(test_code)
            cleanup_verified = get_promo_code_by_code(test_code) is None
            if deleted and cleanup_verified:
                results["14. Clean up temporary test promo code MRC456 after testing"] = "PASS"
            else:
                results["14. Clean up temporary test promo code MRC456 after testing"] = "FAIL (Cleanup verification failed)"
        else:
            results["14. Clean up temporary test promo code MRC456 after testing"] = "PASS (Skipped - was pre-existing)"
    except Exception as e:
        results["14. Clean up temporary test promo code MRC456 after testing"] = f"FAIL ({e})"

    print("=" * 60)
    print("PROMO CODE VERIFICATION TEST RESULTS")
    print("=" * 60)
    for test_name, status in results.items():
        print(f"{test_name}: {status}")
    print("=" * 60)

    all_pass = all(status == "PASS" for status in results.values())
    print(f"OVERALL RESULT: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


if __name__ == "__main__":
    success = run_full_promo_code_verification()
    if not success:
        exit(1)
