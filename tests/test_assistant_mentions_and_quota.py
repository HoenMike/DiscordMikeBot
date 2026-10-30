"""Regression tests: trusted Discord mentions and bounded Gemini quota breaker."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from core import ai as shared_ai
from features.assistant.response import format_authorized_mentions, send_conversation_reply


class AuthorizedMentionTests(unittest.TestCase):
    def test_explicit_tagged_person_becomes_real_discord_id(self):
        rendered, users = format_authorized_mentions(
            "Bông Gòn ơi, @Bông Gòn nghe Asumi nói nè!",
            [(123456789012345678, "Bông Gòn")],
        )
        self.assertIn("<@123456789012345678>", rendered)
        self.assertEqual([u.id for u in users], [123456789012345678])
        self.assertNotIn("@Bông Gòn", rendered)

    def test_unmentioned_names_and_arbitrary_ai_ids_never_ping(self):
        rendered, users = format_authorized_mentions(
            "Này @Bông Gòn, @everyone <@999999999999999999>",
            [],
        )
        self.assertIn("@Bông Gòn", rendered)
        self.assertIn("@everyone", rendered)
        self.assertNotIn("<@999999999999999999>", rendered)
        self.assertEqual(users, [])

    def test_duplicate_display_name_is_ambiguous(self):
        rendered, users = format_authorized_mentions(
            "@Mike nghe nè", [(123456789012345678, "Mike"), (223456789012345678, "MIKE")]
        )
        self.assertIn("@Mike", rendered)
        self.assertFalse(users)

    def test_no_prefix_collisions(self):
        rendered, users = format_authorized_mentions(
            "Hello @Anna và @Ann!", [
                (123456789012345678, "Ann"), (223456789012345678, "Anna")
            ],
        )
        self.assertIn("<@223456789012345678>", rendered)
        self.assertIn("<@123456789012345678>", rendered)
        self.assertEqual(len(users), 2)


class AuthorizedMentionDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_allows_only_explicitly_tagged_user(self):
        first = SimpleNamespace(id=51)
        msg = SimpleNamespace(
            reply=AsyncMock(return_value=first),
            channel=SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=52))),
        )
        delivery = await send_conversation_reply(
            msg, "Gọi @Bông Gòn nè, không phải @everyone!",
            mentioned_people=[(123456789012345678, "Bông Gòn")],
        )
        args, kwargs = msg.reply.call_args
        self.assertIn("<@123456789012345678>", args[0])
        self.assertFalse(kwargs["mention_author"])
        self.assertIsInstance(kwargs["allowed_mentions"], discord.AllowedMentions)
        allowed = kwargs["allowed_mentions"]
        self.assertFalse(allowed.everyone)
        self.assertFalse(allowed.roles)
        self.assertFalse(allowed.replied_user)
        self.assertEqual([user.id for user in allowed.users], [123456789012345678])
        self.assertEqual(delivery.message_ids, (51,))


class QuotaCircuitTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        shared_ai._quota_failures.clear()
        shared_ai._quota_paused_until = 0
        shared_ai.AI_CALL_SEMAPHORE = None

    async def test_two_distinct_model_429s_pause_later_calls(self):
        shared_ai._quota_failures.clear()
        shared_ai._quota_paused_until = 0
        client = SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(
            side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")
        )))
        with patch("core.ai.get_aio_client", return_value=client):
            for model in ("gemini-3.8-flash", "gemini-3.5-flash-lite"):
                with self.assertRaisesRegex(RuntimeError, "429"):
                    await shared_ai.bounded_ai_generate(model, "Hi", None, 1)
            with self.assertRaises(shared_ai.GeminiQuotaCircuitOpen):
                await shared_ai.bounded_ai_generate("gemini-3.5-flash-lite", "Hi", None, 1)
        self.assertEqual(client.models.generate_content.await_count, 2)

    async def test_one_429_does_not_block_all_fallbacks(self):
        shared_ai._quota_failures.clear()
        shared_ai._quota_paused_until = 0
        client = SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(
            side_effect=[RuntimeError("429 RESOURCE_EXHAUSTED"), SimpleNamespace(text="ok")]
        )))
        with patch("core.ai.get_aio_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "429"):
                await shared_ai.bounded_ai_generate("gemini-3.8-flash", "Hi", None, 1)
            response = await shared_ai.bounded_ai_generate("gemini-3.5-flash-lite", "Hi", None, 1)
        self.assertEqual(response.text, "ok")


if __name__ == "__main__":
    unittest.main()
