import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from database import (
    initialize_database,
    create_or_update_user,
    get_user_by_telegram_id,
    delete_user_by_telegram_id,
    get_connection,
)
import bot


class TestPhase12StartCommand(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        initialize_database()
        self.test_tg_id = 999888777
        self.test_tg_id_2 = 888777666
        delete_user_by_telegram_id(self.test_tg_id)
        delete_user_by_telegram_id(self.test_tg_id_2)

    async def asyncTearDown(self):
        delete_user_by_telegram_id(self.test_tg_id)
        delete_user_by_telegram_id(self.test_tg_id_2)

    async def test_start_command_flow(self):
        # 1. First time /start is called
        mock_user = MagicMock()
        mock_user.id = self.test_tg_id
        mock_user.username = "testuser1"
        mock_user.first_name = "Test First"

        mock_message = AsyncMock()
        mock_update = MagicMock()
        mock_update.effective_user = mock_user
        mock_update.message = mock_message
        mock_context = MagicMock()

        await bot.start(mock_update, mock_context)

        # Confirm user is created
        user = get_user_by_telegram_id(self.test_tg_id)
        self.assertIsNotNone(user, "User was not created in users table")
        self.assertEqual(user["telegram_user_id"], self.test_tg_id)
        self.assertEqual(user["username"], "testuser1")
        self.assertEqual(user["first_name"], "Test First")
        self.assertIsNotNone(user["created_at"])

        original_id = user["id"]
        original_created_at = user["created_at"]

        # Confirm reply message
        mock_message.reply_text.assert_called_once()
        self.assertIn("حالياً ما كاين حتى عرض مفتوح", mock_message.reply_text.call_args[0][0])

        # 2. Second time /start is called with identical data
        mock_message.reset_mock()
        await bot.start(mock_update, mock_context)

        # Confirm exactly 1 record exists and no duplicate
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as c FROM users WHERE telegram_user_id = ?",
                (self.test_tg_id,)
            ).fetchone()["c"]
            self.assertEqual(count, 1, "Duplicate user created for same telegram ID")

        user2 = get_user_by_telegram_id(self.test_tg_id)
        self.assertEqual(user2["id"], original_id)
        self.assertEqual(user2["created_at"], original_created_at)

        # 3. Third time /start is called with updated username and first_name
        mock_user.username = "updated_username"
        mock_user.first_name = "Updated First"
        mock_message.reset_mock()

        await bot.start(mock_update, mock_context)

        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as c FROM users WHERE telegram_user_id = ?",
                (self.test_tg_id,)
            ).fetchone()["c"]
            self.assertEqual(count, 1, "Duplicate user created when updating")

        user3 = get_user_by_telegram_id(self.test_tg_id)
        self.assertEqual(user3["id"], original_id)
        self.assertEqual(user3["username"], "updated_username")
        self.assertEqual(user3["first_name"], "Updated First")
        self.assertEqual(user3["created_at"], original_created_at)

    async def test_start_command_user_without_username(self):
        mock_user = MagicMock()
        mock_user.id = self.test_tg_id_2
        mock_user.username = None
        mock_user.first_name = "NoUnameUser"

        mock_message = AsyncMock()
        mock_update = MagicMock()
        mock_update.effective_user = mock_user
        mock_update.message = mock_message
        mock_context = MagicMock()

        await bot.start(mock_update, mock_context)

        user = get_user_by_telegram_id(self.test_tg_id_2)
        self.assertIsNotNone(user)
        self.assertIsNone(user["username"])
        self.assertEqual(user["first_name"], "NoUnameUser")


if __name__ == "__main__":
    unittest.main()
