import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.activity_logger import ActivityLogger
from features.assistant.ai import _candidate_models
from features.assistant.router import route_locally, route_message
from features.assistant.session import SessionStore
from features.assistant.tools import CommandToolRegistry
from features.assistant.trigger import has_explicit_mention, strip_bot_mention
from features.assistant.providers.cloudflare import ClefDecision, CloudflareDecisionRouter


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


class AssistantChatModelTests(unittest.TestCase):
    def test_chat_defaults_to_high_rpd_flash_lite(self):
        with patch.dict("os.environ", {}, clear=True):
            models = _candidate_models()
        self.assertEqual(models[0], "gemini-3.5-flash-lite")

    def test_chat_model_can_be_overridden(self):
        with patch.dict(
            "os.environ",
            {"ASUMI_CHAT_MODEL": "gemini-custom-chat"},
            clear=True,
        ):
            models = _candidate_models()
        self.assertEqual(models[0], "gemini-custom-chat")


class AssistantClefRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_obvious_greeting_skips_clef(self):
        router = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(return_value=ClefDecision("summarize", 0.99)),
        )
        decision = await route_message("hello, test tes", router, 0.55)
        self.assertEqual(decision.intent, "chat")
        self.assertIsNone(decision.tool)
        self.assertEqual(decision.source, "local_chat")
        router.classify.assert_not_awaited()

    async def test_high_confidence_clef_can_route_ambiguous_summary(self):
        router = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(return_value=ClefDecision("summarize", 0.91)),
        )
        decision = await route_message("kể lại giúp tôi chuyện vừa xảy ra", router, 0.55)
        self.assertEqual(decision.tool, "summary.catchup")

    async def test_low_confidence_clef_falls_back_to_local_chat(self):
        router = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(return_value=ClefDecision("tarot", 0.20)),
        )
        decision = await route_message("nói chuyện với tôi đi", router, 0.55)
        self.assertEqual(decision.intent, "chat")
        self.assertIsNone(decision.tool)

    async def test_clef_failure_falls_back_without_breaking_message(self):
        router = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(side_effect=TimeoutError("timeout")),
        )
        decision = await route_message("nói chuyện với tôi đi", router, 0.55)
        self.assertEqual(decision.intent, "chat")
        self.assertIsNone(decision.tool)


class CloudflareAdapterTests(unittest.TestCase):
    def test_choice_parser_reads_cloudflare_shape(self):
        result = CloudflareDecisionRouter._parse_choice({
            "choice": "tarot",
            "confidence": 0.88,
            "probabilities": {"tarot": 0.88, "chat": 0.12},
        })
        self.assertEqual(result.intent, "tarot")
        self.assertAlmostEqual(result.confidence, 0.88)

    def test_cloudflare_stays_disabled_without_credentials(self):
        with patch.dict("os.environ", {"CF_ASSISTANT_ENABLED": "true"}, clear=True):
            router = CloudflareDecisionRouter.from_env()
        self.assertFalse(router.enabled)

    def test_short_model_name_is_normalized(self):
        router = CloudflareDecisionRouter(
            account_id="account",
            api_token="token",
            enabled=True,
            model="clef-flash",
        )
        self.assertTrue(router.enabled)
        self.assertEqual(router.model, "@cf/cloudflare/clef-flash")


class AssistantDashboardTelemetryTests(unittest.TestCase):
    def test_activity_logger_counts_assistant_telemetry(self):
        logger = ActivityLogger(maxlen=5)
        logger.log(
            action_type="assistant",
            action_name="Asumi Chat",
            user_id=1,
            user_name="Tester",
            duration_ms=3672.0,
            details={
                "path": "chat",
                "model": "gemini-3.5-flash-lite",
                "route_ms": 2.0,
                "clef_ms": 0.0,
                "ai_ms": 3238.0,
                "send_ms": 432.0,
                "total_ms": 3672.0,
            },
        )

        result = logger.get_activities(limit=5)

        self.assertEqual(result["counts"]["assistant"], 1)
        self.assertEqual(result["items"][0]["action_type"], "assistant")
        self.assertEqual(result["items"][0]["details"]["ai_ms"], 3238.0)


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
