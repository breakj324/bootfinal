import sqlite3
import unittest
from database import (
    initialize_database,
    create_promo_code,
    get_promo_code_by_code,
    get_promo_code_by_id,
    get_promo_code,
    get_active_promo_codes,
    update_promo_code,
    disable_promo_code,
    enable_promo_code,
    delete_promo_code,
    get_connection,
)


class TestPhase13PromoCodes(unittest.TestCase):
    def setUp(self):
        initialize_database()
        self.test_code = "MRC456"
        self.test_code_2 = "WIN789"
        delete_promo_code(self.test_code)
        delete_promo_code(self.test_code_2)

    def tearDown(self):
        delete_promo_code(self.test_code)
        delete_promo_code(self.test_code_2)

    def test_schema_and_column_structure(self):
        """Verify promo_codes table contains all required columns."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(promo_codes)")
            columns = {row["name"]: row["type"] for row in cursor.fetchall()}

        required_columns = [
            "id",
            "code",
            "description",
            "instructions",
            "requirements",
            "example_image",
            "active",
            "created_at",
        ]
        for col in required_columns:
            self.assertIn(col, columns, f"Column '{col}' missing from promo_codes table")

    def test_mrc456_full_lifecycle(self):
        """
        Phase 13 core test:
        Create promo code MRC456, then verify:
        - MRC456 can be retrieved
        - MRC456 can be disabled
        - MRC456 disappears from active promo codes
        - MRC456 can be enabled again
        - Creating another MRC456 is rejected because the code is unique
        """
        # 1. Create promo code with code = "MRC456"
        db_id = create_promo_code(
            code=self.test_code,
            description="50% discount on registration",
            instructions="Use promo code MRC456 when registering",
            requirements="New users only, valid once per user",
            example_image="/images/mrc456_example.png",
            active=1,
        )
        self.assertGreater(db_id, 0, "Promo code internal ID should be positive integer")

        # 2. Verify MRC456 can be retrieved using get_promo_code_by_code
        promo = get_promo_code_by_code(self.test_code)
        self.assertIsNotNone(promo, "MRC456 should be retrievable by code string")
        self.assertEqual(promo["id"], db_id)
        self.assertEqual(promo["code"], "MRC456")
        self.assertEqual(promo["description"], "50% discount on registration")
        self.assertEqual(promo["instructions"], "Use promo code MRC456 when registering")
        self.assertEqual(promo["requirements"], "New users only, valid once per user")
        self.assertEqual(promo["example_image"], "/images/mrc456_example.png")
        self.assertEqual(promo["active"], 1)
        self.assertIsNotNone(promo["created_at"])

        # Also verify get_promo_code polymorphic helper
        promo_poly = get_promo_code("MRC456")
        self.assertEqual(promo_poly["id"], db_id)

        # 3. Verify MRC456 appears in active promo codes list
        active_list = get_active_promo_codes()
        active_codes = [p["code"] for p in active_list]
        self.assertIn("MRC456", active_codes, "MRC456 must be present in active promo codes")

        # 4. Disable MRC456
        disable_result = disable_promo_code(self.test_code)
        self.assertTrue(disable_result, "disable_promo_code should return True on success")

        promo_after_disable = get_promo_code_by_code(self.test_code)
        self.assertEqual(promo_after_disable["active"], 0, "active flag must be 0 after disable")

        # 5. Verify MRC456 disappears from active promo codes
        active_list_after_disable = get_active_promo_codes()
        active_codes_after_disable = [p["code"] for p in active_list_after_disable]
        self.assertNotIn("MRC456", active_codes_after_disable, "Disabled MRC456 must NOT appear in active list")

        # 6. Enable MRC456 again
        enable_result = enable_promo_code(self.test_code)
        self.assertTrue(enable_result, "enable_promo_code should return True on success")

        promo_after_enable = get_promo_code_by_code(self.test_code)
        self.assertEqual(promo_after_enable["active"], 1, "active flag must be 1 after enable")

        active_list_after_enable = get_active_promo_codes()
        active_codes_after_enable = [p["code"] for p in active_list_after_enable]
        self.assertIn("MRC456", active_codes_after_enable, "Re-enabled MRC456 must appear in active list")

        # 7. Verify creating another MRC456 is rejected because the code is UNIQUE
        with self.assertRaises(sqlite3.IntegrityError):
            create_promo_code(
                code=self.test_code,
                description="Duplicate attempt"
            )

    def test_update_promo_code(self):
        """Verify updating promo code fields using the actual code."""
        db_id = create_promo_code(
            code=self.test_code_2,
            description="Initial description",
            instructions="Initial instructions",
        )

        update_success = update_promo_code(
            code=self.test_code_2,
            description="Updated description",
            instructions="Updated instructions",
        )
        self.assertTrue(update_success)

        updated_record = get_promo_code_by_code(self.test_code_2)
        self.assertEqual(updated_record["id"], db_id)
        self.assertEqual(updated_record["description"], "Updated description")
        self.assertEqual(updated_record["instructions"], "Updated instructions")


if __name__ == "__main__":
    unittest.main()
