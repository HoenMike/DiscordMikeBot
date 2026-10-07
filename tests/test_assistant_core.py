import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from features.assistant.router import route_locally
from features.assistant.session import SessionStore
from features.assistant.tools import CommandToolRegistry
from features.assistant.trigger import has_explicit_mention, strip_bot_mention


def fake_message(content="@Asumi hello", *, reply_id=None):
    return SimpleNamespace(
        content=content,
        guild=SimpleNamespace(id=10),
        channel=SimpleNamespace(id=20),
        author=SimpleNamespace(id=30),
        reference=SimpleNamespace(message_id=reply_id) if reply_id else None,
    )


class AssistantRouterTests(unittest.TestCase):
    def test_tarot_daily_routes_to_existing_tool(self):
        decision = route_locally("cho tôi tarot daily đi")
        self.assertEqual(decision.tool, "tarot.daily")

    def test_tarot_question_routes_to_launcher(self):
        decision = route_locally("bói bài cho tôi chuyện công việc")
        self.assertEqual(decision.tool, "tarot.launch")

    def test_summary_extracts_hours(self):
        decision = route_locally("tóm tắt 2 tiếng vừa rồi")
        self.assertEqual(decision.tool, "summary.catchup")
        self.assertEqual(decision.arguments["hours"], 2.0)

    def test_catchup_phrase_routes_to_summary(self):
        decision = route_locally("nãy giờ có gì vậy?")
        self.assertEqual(decision.tool, "summary.catchup")

    def test_general_chat_does_not_force_tool(self):
        decision = route_locally("nay ăn gì ngon?")
        self.assertEqual(decision.intent, "chat")
        self.assertIsNone(decision.tool)


class AssistantTriggerTests(unittest.TestCase):
    def test_explicit_discord_mention_is_detected(self):
        msg = fake_message("<@123> hello")
        self.assertTrue(has_explicit_mention(msg, 123))
        self.assertEqual(strip_bot_mention(msg.content, 123), "hello")

    def test_nickname_mention_is_detected(self):
        msg = fake_message("<@!123> hello")
        self.assertTrue(has_explicit_mention(msg, 123))
        self.assertEqual(strip_bot_mention(msg.content, 123), "hello")

    def test_dm_is_not_v1_mention_trigger(self):
        msg = fake_message("<@123> hello")
        msg.guild = None
        self.assertFalse(has_explicit_mention(msg, 123))


class AssistantSessionTests(unittest.TestCase):
    def test_only_last_asumi_reply_continues_session(self):
        store = SessionStore(ttl_seconds=1200, max_turns=2)
        original = fake_message("hello")
        session = store.record_exchange(original, 99, "hello", "hi")
        self.assertIsNotNone(session)

        self.assertTrue(store.is_live_reply(fake_message("more", reply_id=99)))
        self.assertFalse(store.is_live_reply(fake_message("more", reply_id=98)))

    def test_session_turns_are_bounded(self):
        store = SessionStore(ttl_seconds=1200, max_turns=2)
        msg = fake_message("x")
        store.record_exchange(msg, 1, "u1", "a1")
        store.record_exchange(msg, 2, "u2", "a2")
        session = store.record_exchange(msg, 3, "u3", "a3")
        self.assertEqual([turn.user for turn in session.turns], ["u2", "u3"])


class AssistantToolBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_bridge_uses_synthetic_message_and_preserves_source(self):
        bot = SimpleNamespace(process_commands=AsyncMock())
        registry = CommandToolRegistry(bot)
        source = fake_message("<@123> tóm tắt 2 tiếng vừa rồi")
        decision = route_locally("tóm tắt 2 tiếng vừa rồi")

        result = await registry.execute(decision, source)

        self.assertTrue(result.handled)
        self.assertEqual(result.command_text, ".m tomtat 2h")
        self.assertEqual(source.content, "<@123> tóm tắt 2 tiếng vừa rồi")
        synthetic = bot.process_commands.await_args.args[0]
        self.assertIsNot(synthetic, source)
        self.assertEqual(synthetic.content, ".m tomtat 2h")


if __name__ == "__main__":
    unittest.main()
