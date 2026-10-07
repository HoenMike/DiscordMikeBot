import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.activity_logger import ActivityLogger
from features.assistant.ai import _candidate_models, _build_prompt, generate_chat_reply
from features.assistant.context import AssistantContext, ContextBuilder, ImagePayload
from features.assistant.cog import choose_conversation_route
from features.assistant.router import route_locally, route_message
from features.assistant.session import SessionStore
from features.assistant.tools import CommandToolRegistry
from features.assistant.trigger import has_explicit_mention, strip_bot_mention
from features.assistant.providers.cloudflare import ClefDecision, CloudflareDecisionRouter
from features.assistant.response import send_conversation_reply


def fake_message(
    content="@Asumi hello",
    *,
    reply_id=None,
    author_id=30,
    channel=None,
    attachments=None,
    resolved=None,
):
    reference = None
    if reply_id is not None:
        reference = SimpleNamespace(message_id=reply_id, resolved=resolved)
    return SimpleNamespace(
        id=1000 + author_id,
        content=content,
        guild=SimpleNamespace(id=10),
        channel=channel or SimpleNamespace(id=20),
        author=SimpleNamespace(id=author_id, display_name=f"User{author_id}"),
        reference=reference,
        attachments=list(attachments or []),
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


    def test_other_user_cannot_continue_someone_elses_session(self):
        store = SessionStore(ttl_seconds=1200, max_turns=2)
        owner = fake_message("hello", author_id=30)
        store.record_exchange(owner, 99, "hello", "hi")
        other = fake_message("more", reply_id=99, author_id=31)
        self.assertFalse(store.is_live_reply(other))

    def test_expired_session_does_not_continue(self):
        store = SessionStore(ttl_seconds=60, max_turns=2)
        msg = fake_message("hello")
        with patch("features.assistant.session.time.monotonic", return_value=10.0):
            store.record_exchange(msg, 99, "hello", "hi")
        with patch("features.assistant.session.time.monotonic", return_value=71.0):
            self.assertFalse(store.is_live_reply(fake_message("more", reply_id=99)))

    def test_session_keeps_bounded_image_snapshot_for_followup(self):
        store = SessionStore(ttl_seconds=1200, max_turns=2)
        msg = fake_message("image")
        image = ImagePayload(b"img", "image/png", "shot.png")
        first = store.record_exchange(msg, 99, "image", "seen", images=[image])
        self.assertEqual(first.images[0].filename, "shot.png")
        followup = store.record_exchange(msg, 100, "where?", "there")
        self.assertEqual(followup.images[0].filename, "shot.png")


    def test_any_chunk_of_latest_response_can_continue_session(self):
        store = SessionStore(ttl_seconds=1200, max_turns=2)
        msg = fake_message("hello")
        store.record_exchange(
            msg,
            101,
            "hello",
            "long answer",
            response_message_ids=[99, 100, 101],
        )
        self.assertTrue(store.is_live_reply(fake_message("part 1?", reply_id=99)))
        self.assertTrue(store.is_live_reply(fake_message("part 2?", reply_id=100)))
        self.assertTrue(store.is_live_reply(fake_message("part 3?", reply_id=101)))
        self.assertFalse(store.is_live_reply(fake_message("old?", reply_id=98)))

    def test_tool_session_tracks_all_tool_output_ids(self):
        store = SessionStore(ttl_seconds=1200, max_turns=2)
        msg = fake_message("tarot")
        session = store.record_exchange(
            msg,
            201,
            "tarot daily",
            "tool output",
            intent="tarot_daily",
            response_message_ids=[200, 201],
            tool="tarot.daily",
        )
        self.assertEqual(session.last_tool, "tarot.daily")
        self.assertEqual(session.response_message_ids, [200, 201])
        self.assertTrue(store.is_live_reply(fake_message("lá này?", reply_id=200)))


class _FakeHistoryChannel:
    def __init__(self, items):
        self.id = 20
        self.items = list(items)
        self.history_called = False

    def history(self, **kwargs):
        self.history_called = True
        async def _iterate():
            for item in self.items:
                yield item
        return _iterate()


class AssistantContextBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_target_is_included_without_channel_history(self):
        replied = SimpleNamespace(
            id=77,
            content="Theo gửi link https://example.com/game",
            author=SimpleNamespace(display_name="Theo"),
            attachments=[],
        )
        channel = _FakeHistoryChannel([])
        msg = fake_message(
            "<@123> game này có mobile không?",
            reply_id=77,
            resolved=replied,
            channel=channel,
        )
        ctx = await ContextBuilder().build(msg, "game này có mobile không?")
        self.assertEqual(ctx.reply.author, "Theo")
        self.assertIn("https://example.com/game", ctx.urls)
        self.assertFalse(channel.history_called)

    async def test_direct_reply_referent_does_not_scan_recent_history(self):
        replied = SimpleNamespace(
            id=77,
            content="nội dung cần hỏi",
            author=SimpleNamespace(display_name="Theo"),
            attachments=[],
            embeds=[],
        )
        channel = _FakeHistoryChannel([])
        msg = fake_message(
            "<@123> cái này nghĩa là gì?",
            reply_id=77,
            resolved=replied,
            channel=channel,
        )

        ctx = await ContextBuilder().build(msg, "cái này nghĩa là gì?")

        self.assertIsNotNone(ctx.reply)
        self.assertFalse(channel.history_called)

    async def test_broad_catchup_still_scans_recent_even_with_reply(self):
        replied = SimpleNamespace(
            id=77,
            content="mốc tham chiếu",
            author=SimpleNamespace(display_name="Theo"),
            attachments=[],
            embeds=[],
        )
        history_item = SimpleNamespace(
            id=1,
            content="có chuyện mới",
            author=SimpleNamespace(display_name="Mai"),
            attachments=[],
            embeds=[],
        )
        channel = _FakeHistoryChannel([history_item])
        msg = fake_message(
            "<@123> nãy giờ mọi người đang bàn gì?",
            reply_id=77,
            resolved=replied,
            channel=channel,
        )

        ctx = await ContextBuilder().build(
            msg,
            "nãy giờ mọi người đang bàn gì?",
        )

        self.assertTrue(channel.history_called)
        self.assertTrue(ctx.used_recent_history)

    async def test_recent_history_is_only_fetched_for_contextual_cues(self):
        # discord.py history(oldest_first=False) yields newest -> oldest.
        recent = [
            SimpleNamespace(
                id=2,
                content="có vẻ hay",
                author=SimpleNamespace(display_name="Mai"),
                attachments=[],
            ),
            SimpleNamespace(
                id=1,
                content="game mới nè https://example.com/a",
                author=SimpleNamespace(display_name="Theo"),
                attachments=[],
            ),
        ]
        channel = _FakeHistoryChannel(recent)
        msg = fake_message("<@123> game Theo gửi phía trên là gì?", channel=channel)
        ctx = await ContextBuilder(recent_limit=8).build(
            msg,
            "game Theo gửi phía trên là gì?",
        )
        self.assertTrue(channel.history_called)
        self.assertTrue(ctx.used_recent_history)
        self.assertEqual([x.author for x in ctx.recent], ["Theo", "Mai"])
        self.assertIn("https://example.com/a", ctx.urls)

    async def test_reply_embed_metadata_is_included(self):
        embed = SimpleNamespace(
            title="Game page",
            description="Co-op farming game",
            url="https://example.com/game",
        )
        replied = SimpleNamespace(
            id=77,
            content="",
            author=SimpleNamespace(display_name="Theo"),
            attachments=[],
            embeds=[embed],
        )
        msg = fake_message(
            "<@123> cái này có coop không?",
            reply_id=77,
            resolved=replied,
        )
        ctx = await ContextBuilder().build(msg, "cái này có coop không?")
        self.assertIn("[Embed] Game page", ctx.reply.content)
        self.assertIn("Co-op farming game", ctx.reply.content)
        self.assertIn("https://example.com/game", ctx.urls)

    async def test_missing_content_type_infers_image_from_extension(self):
        attachment = SimpleNamespace(
            content_type=None,
            filename="screen.PNG",
            size=3,
            read=AsyncMock(return_value=b"png"),
        )
        msg = fake_message("<@123> xem cái này", attachments=[attachment])
        ctx = await ContextBuilder().build(msg, "xem cái này")
        self.assertEqual(len(ctx.images), 1)
        self.assertEqual(ctx.images[0].mime_type, "image/png")

    async def test_direct_image_attachment_is_loaded(self):
        attachment = SimpleNamespace(
            content_type="image/png",
            filename="error.png",
            size=3,
            read=AsyncMock(return_value=b"png"),
        )
        msg = fake_message("<@123> lỗi gì đây?", attachments=[attachment])
        ctx = await ContextBuilder().build(msg, "lỗi gì đây?")
        self.assertEqual(len(ctx.images), 1)
        self.assertEqual(ctx.images[0].filename, "error.png")
        self.assertEqual(ctx.images[0].source, "attachment")

    async def test_replied_image_is_loaded(self):
        attachment = SimpleNamespace(
            content_type="image/jpeg",
            filename="meme.jpg",
            size=4,
            read=AsyncMock(return_value=b"jpeg"),
        )
        replied = SimpleNamespace(
            id=77,
            content="",
            author=SimpleNamespace(display_name="Theo"),
            attachments=[attachment],
        )
        msg = fake_message(
            "<@123> meme này joke gì?",
            reply_id=77,
            resolved=replied,
        )
        ctx = await ContextBuilder().build(msg, "meme này joke gì?")
        self.assertEqual(len(ctx.images), 1)
        self.assertEqual(ctx.images[0].source, "reply")

    async def test_live_followup_reuses_session_image_but_skips_bot_reply_text(self):
        image = ImagePayload(b"img", "image/webp", "screen.webp")
        session = SimpleNamespace(last_response_message_id=99, images=[image])
        bot_reply = SimpleNamespace(
            id=99,
            content="Đây là lỗi config.",
            author=SimpleNamespace(display_name="Asumi"),
            attachments=[],
        )
        msg = fake_message(
            "vậy sửa chỗ nào?",
            reply_id=99,
            resolved=bot_reply,
        )
        ctx = await ContextBuilder().build(
            msg,
            "vậy sửa chỗ nào?",
            session=session,
            is_live_continuation=True,
        )
        self.assertIsNone(ctx.reply)
        self.assertTrue(ctx.used_session_images)
        self.assertEqual(ctx.images[0].filename, "screen.webp")

    async def test_live_tool_followup_reads_current_edited_output_and_image(self):
        attachment = SimpleNamespace(
            content_type="image/png",
            filename="tarot_spread.png",
            size=3,
            read=AsyncMock(return_value=b"img"),
        )
        embed = SimpleNamespace(
            title="Daily Reading",
            description="The Fool — bước khởi đầu mới",
            url="",
        )
        bot_reply = SimpleNamespace(
            id=99,
            content="",
            author=SimpleNamespace(display_name="Asumi"),
            attachments=[attachment],
            embeds=[embed],
        )
        session = SimpleNamespace(
            last_response_message_id=99,
            response_message_ids=[99],
            last_tool="tarot.daily",
            images=[],
        )
        msg = fake_message(
            "lá này nghĩa sao?",
            reply_id=99,
            resolved=bot_reply,
        )

        ctx = await ContextBuilder().build(
            msg,
            "lá này nghĩa sao?",
            session=session,
            is_live_continuation=True,
        )

        self.assertIsNotNone(ctx.reply)
        self.assertIn("The Fool", ctx.reply.content)
        self.assertEqual(len(ctx.images), 1)
        self.assertEqual(ctx.images[0].filename, "tarot_spread.png")

    async def test_oversize_image_is_skipped(self):
        attachment = SimpleNamespace(
            content_type="image/png",
            filename="huge.png",
            size=300000,
            read=AsyncMock(return_value=b"x" * 300000),
        )
        msg = fake_message("<@123> xem ảnh", attachments=[attachment])
        ctx = await ContextBuilder(max_image_bytes=512).build(msg, "xem ảnh")
        self.assertEqual(ctx.images, [])
        self.assertTrue(ctx.warnings)
        attachment.read.assert_not_awaited()


class AssistantMultimodalPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_chat_reply_sends_image_part(self):
        context = AssistantContext(
            images=[ImagePayload(b"img", "image/png", "shot.png")]
        )
        fake_response = SimpleNamespace(text="mình thấy ảnh")
        with patch(
            "features.assistant.ai.bounded_ai_generate",
            new=AsyncMock(return_value=fake_response),
        ) as generate:
            result = await generate_chat_reply("ảnh này là gì?", context=context)
        self.assertEqual(result.text, "mình thấy ảnh")
        contents = generate.await_args.kwargs["contents"]
        self.assertEqual(len(contents[0].parts), 2)
        self.assertEqual(contents[0].parts[1].inline_data.mime_type, "image/png")

    async def test_url_context_tool_is_enabled_when_context_has_url(self):
        context = AssistantContext(urls=["https://example.com/article"])
        fake_response = SimpleNamespace(text="đã đọc")
        with patch(
            "features.assistant.ai.bounded_ai_generate",
            new=AsyncMock(return_value=fake_response),
        ) as generate:
            await generate_chat_reply("link này nói gì?", context=context)
        config = generate.await_args.kwargs["config"]
        self.assertIsNotNone(config.tools)

    def test_context_prompt_respects_configured_char_cap(self):
        ctx = AssistantContext(
            prompt_char_limit=1000,
            recent=[
                SimpleNamespace(author="A", content="x" * 2000),
            ],
        )
        self.assertLessEqual(len(ctx.to_prompt_text()), 1000)

    def test_prompt_contains_reply_context(self):
        ctx = AssistantContext()
        ctx.reply = SimpleNamespace(author="Theo", content="test message")
        prompt = _build_prompt("giải thích đi", None, ctx)
        self.assertIn("Theo: test message", prompt)


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


class AssistantFollowupRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_followup_never_reopens_tool_router(self):
        previous = SimpleNamespace(intent="tarot")
        router = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(return_value=ClefDecision("tarot", 0.99)),
        )
        with patch(
            "features.assistant.cog.route_message",
            new=AsyncMock(),
        ) as route:
            decision = await choose_conversation_route(
                "lá thứ 2 nghĩa sao?",
                previous_session=previous,
                is_live_continuation=True,
                has_images=False,
                cloudflare_router=router,
                min_confidence=0.55,
            )
        self.assertEqual(decision.intent, "tarot")
        self.assertIsNone(decision.tool)
        self.assertEqual(decision.source, "session_followup")
        route.assert_not_awaited()

    async def test_image_only_request_goes_to_vision_chat_not_help(self):
        decision = await choose_conversation_route(
            "",
            previous_session=None,
            is_live_continuation=False,
            has_images=True,
            cloudflare_router=None,
            min_confidence=0.55,
        )
        self.assertEqual(decision.intent, "vision")
        self.assertIsNone(decision.tool)
        self.assertEqual(decision.source, "image_only")


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


class AssistantDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_split_response_returns_all_message_ids(self):
        first = SimpleNamespace(id=501)
        second = SimpleNamespace(id=502)
        source = SimpleNamespace(
            reply=AsyncMock(return_value=first),
            channel=SimpleNamespace(send=AsyncMock(return_value=second)),
        )
        with patch(
            "features.assistant.response.split_text",
            return_value=["part one", "part two"],
        ):
            delivery = await send_conversation_reply(source, "ignored")

        self.assertEqual(delivery.message_ids, (501, 502))
        self.assertIs(delivery.last_message, second)


class AssistantToolBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_bridge_captures_bot_output_refs_and_context(self):
        output = SimpleNamespace(
            id=700,
            author=SimpleNamespace(id=999),
            content="",
            embeds=[
                SimpleNamespace(
                    title="Daily Reading",
                    description="The Fool",
                    fields=[],
                )
            ],
            attachments=[],
        )

        class Channel:
            id = 20
            def history(self, **kwargs):
                async def _iter():
                    yield output
                return _iter()

        bot = SimpleNamespace(
            user=SimpleNamespace(id=999),
            process_commands=AsyncMock(),
        )
        registry = CommandToolRegistry(bot)
        source = fake_message(
            "<@123> tarot daily",
            channel=Channel(),
        )
        decision = route_locally("tarot daily")

        result = await registry.execute(decision, source)

        self.assertTrue(result.handled)
        self.assertEqual(result.response_message_ids, (700,))
        self.assertIn("Daily Reading", result.response_context)
        self.assertIn("The Fool", result.response_context)

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
