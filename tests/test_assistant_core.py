import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.activity_logger import ActivityLogger
from features.assistant.ai import (
    ChatTimeoutBudgetError,
    _candidate_models,
    _build_prompt,
    _chat_limits,
    generate_chat_reply,
)
from features.assistant.context import AssistantContext, ContextBuilder, ImagePayload, needs_social_context
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
    mentions=None,
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
        mentions=list(mentions or []),
    )


class AssistantRouterTests(unittest.TestCase):
    def test_tarot_daily_routes_to_existing_tool(self):
        decision = route_locally("cho tôi tarot daily đi")
        self.assertEqual(decision.tool, "tarot.daily")

    def test_tarot_question_draw_uses_original_question(self):
        decision = route_locally("bói bài cho tôi chuyện công việc")
        self.assertEqual(decision.tool, "tarot.draw")
        self.assertEqual(decision.arguments["question"], "chuyện công việc")

    def test_reported_mention_draws_one_card_for_outfit_question(self):
        decision = route_locally("bốc cho quẻ tarot xem mai nên mặc áo màu gì đi nhậu")
        self.assertEqual(decision.tool, "tarot.draw")
        self.assertEqual(decision.arguments["question"], "mai nên mặc áo màu gì đi nhậu")
        self.assertEqual(decision.arguments["spread_key"], "single")
        self.assertEqual(
            CommandToolRegistry._command_for(decision),
            ".m tarot single mai nên mặc áo màu gì đi nhậu",
        )

    def test_question_only_tarot_launcher_is_prefilled(self):
        decision = route_locally("xem tarot cho mình chuyện tình cảm")
        self.assertEqual(decision.tool, "tarot.launch")
        self.assertEqual(decision.arguments["question"], "chuyện tình cảm")
        self.assertEqual(
            CommandToolRegistry._command_for(decision),
            ".m tarot ui chuyện tình cảm",
        )

    def test_tarot_daily_remains_direct_but_today_question_is_not_daily(self):
        self.assertEqual(route_locally("tarot daily đi").tool, "tarot.daily")
        self.assertEqual(route_locally("tarot hôm nay").tool, "tarot.daily")
        decision = route_locally("tarot hôm nay nên mặc áo màu gì?")
        self.assertEqual(decision.tool, "tarot.launch")
        self.assertEqual(decision.arguments["question"], "hôm nay nên mặc áo màu gì")

    def test_empty_tarot_request_never_autodraws(self):
        self.assertEqual(route_locally("bốc tarot đi").tool, "tarot.launch")
        self.assertEqual(CommandToolRegistry._command_for(route_locally("tarot")), ".m tarot")

    def test_question_length_and_mentions_are_safe_in_bridge(self):
        decision = route_locally("bốc tarot xem @everyone " + "a" * 600)
        self.assertLessEqual(len(decision.arguments["question"]), 500)
        self.assertNotIn("@everyone", CommandToolRegistry._command_for(decision))

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

    def test_prune_expired_releases_session_image_memory(self):
        store = SessionStore(ttl_seconds=60, max_turns=2)
        msg = fake_message("image")
        image = ImagePayload(b"x" * 1024, "image/png", "shot.png")
        with patch("features.assistant.session.time.monotonic", return_value=10.0):
            store.record_exchange(msg, 99, "image", "seen", images=[image])
        self.assertEqual(len(store._sessions), 1)

        removed = store.prune_expired(now=71.0)

        self.assertEqual(removed, 1)
        self.assertEqual(len(store._sessions), 0)

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
        self.history_kwargs = None

    def history(self, **kwargs):
        self.history_called = True
        self.history_kwargs = kwargs
        async def _iterate():
            for item in self.items:
                yield item
        return _iterate()


class AssistantContextBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_target_is_kept_alongside_bounded_channel_history(self):
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
        self.assertTrue(channel.history_called)

    async def test_direct_reply_referent_keeps_priority_with_recent_history(self):
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
        self.assertTrue(channel.history_called)

    async def test_social_reply_resolves_speaker_and_recent_banter(self):
        replied = SimpleNamespace(
            id=77,
            content="@banbe thấy tên t dễ thương khommmmm",
            author=SimpleNamespace(display_name="Công túa Bông Gòn"),
            attachments=[],
            embeds=[],
        )
        recent = [
            SimpleNamespace(
                id=78,
                content="Subeo nghe nhạc dân chơi",
                author=SimpleNamespace(display_name="Mr.Bư"),
                attachments=[],
                embeds=[],
            ),
            replied,
        ]
        channel = _FakeHistoryChannel(recent)
        msg = fake_message(
            "<@123> ban thằng này được ko",
            reply_id=77,
            resolved=replied,
            channel=channel,
        )
        msg.author.display_name = "Mike"
        ctx = await ContextBuilder().build(msg, "ban thằng này được ko")
        prompt = _build_prompt("ban thằng này được ko", None, ctx)

        self.assertTrue(channel.history_called)
        self.assertEqual(ctx.requester, "Mike")
        self.assertEqual(ctx.reply.author, "Công túa Bông Gòn")
        self.assertNotIn(77, [line.message_id for line in ctx.recent])
        self.assertIn("mục tiêu mặc định): Mike", prompt)
        self.assertIn("không phải lời của người gọi", prompt)
        self.assertIn("Công túa Bông Gòn", prompt)
        self.assertIn("ban thằng này được ko", prompt)

    async def test_explicit_tag_is_resolved_and_takes_priority_over_reply(self):
        mike = SimpleNamespace(id=30, display_name="Mike")
        bong = SimpleNamespace(id=44, display_name="Công túa Bông Gòn")
        asumi = SimpleNamespace(id=123, display_name="AsumiDaBot")
        replied = SimpleNamespace(
            id=77, content="nghe nhạc phonk",
            author=SimpleNamespace(id=44, display_name="Công túa Bông Gòn"),
            attachments=[], embeds=[],
        )
        channel = _FakeHistoryChannel([])
        msg = fake_message(
            "<@123> triệu hồi <@123> sấy <@44>",
            reply_id=77, resolved=replied, channel=channel,
            mentions=[asumi, bong],
        )
        msg.author = mike
        ctx = await ContextBuilder().build(msg, "triệu hồi sấy <@44>")
        prompt = _build_prompt("triệu hồi sấy <@44>", None, ctx)

        self.assertEqual(ctx.requester, "Mike")
        self.assertEqual(ctx.mentioned_people, [(44, "Công túa Bông Gòn")])
        self.assertEqual(ctx.social_referent, "Công túa Bông Gòn")
        self.assertEqual(ctx.social_referent_source, "mention trong lời yêu cầu")
        self.assertIn("<@44> = Công túa Bông Gòn", prompt)
        self.assertIn("trêu ĐÚNG người đó", prompt)
        self.assertNotIn("<@123> =", prompt)
        self.assertTrue(channel.history_called)

    async def test_targeted_slang_chan_is_preserved_not_autocorrected(self):
        satoou = SimpleNamespace(id=56, display_name="Satoou")
        mike = SimpleNamespace(id=30, display_name="Mike")
        asumi = SimpleNamespace(id=123, display_name="AsumiDaBot")
        msg = fake_message(
            "<@123> chan <@30>",
            author_id=56,
            mentions=[asumi, mike],
            channel=_FakeHistoryChannel([]),
        )
        msg.author = satoou
        ctx = await ContextBuilder().build(msg, "chan <@30>")
        prompt = _build_prompt("chan <@30>", None, ctx)

        self.assertEqual(ctx.requester, "Satoou")
        self.assertEqual(ctx.social_referent, "Mike")
        self.assertIn("chan <@30>", prompt)
        self.assertNotIn("chặn <@30>", prompt)

    async def test_multiple_tags_do_not_select_an_arbitrary_target(self):
        mike = SimpleNamespace(id=30, display_name="Mike")
        bong = SimpleNamespace(id=44, display_name="Bông Gòn")
        asumi = SimpleNamespace(id=123, display_name="AsumiDaBot")
        msg = fake_message(
            "<@123> nói <@30> với <@44>",
            author_id=60,
            mentions=[asumi, mike, bong],
            channel=_FakeHistoryChannel([]),
        )
        ctx = await ContextBuilder().build(msg, "nói <@30> với <@44>")
        self.assertEqual(ctx.mentioned_people, [(30, "Mike"), (44, "Bông Gòn")])
        self.assertIsNone(ctx.social_referent)

    async def test_roast_tagged_person_without_reply_still_fetches_chat_vibe(self):
        bong = SimpleNamespace(id=44, display_name="Công túa Bông Gòn")
        msg = fake_message(
            "<@123> đm <@44> đi",
            mentions=[bong],
            channel=_FakeHistoryChannel([]),
        )
        msg.author.display_name = "Mike"
        ctx = await ContextBuilder().build(msg, "đm <@44> đi")
        self.assertTrue(ctx.used_recent_history is False)
        self.assertTrue(msg.channel.history_called)
        self.assertEqual(ctx.social_referent, "Công túa Bông Gòn")

    async def test_social_reply_fetch_is_bounded_and_moderation_stays_separate(self):
        self.assertTrue(needs_social_context("ban thằng này được ko"))
        self.assertTrue(needs_social_context("hùa theo tui trêu nó"))
        # Fetching contextual messages is not a banter or ban-action decision.
        self.assertTrue(needs_social_context("ban <@123> vì spam liên tục"))
        self.assertIsNone(route_locally("ban <@123> vì spam liên tục").tool)
        self.assertFalse(needs_social_context("cái này nghĩa là gì?"))

        channel = _FakeHistoryChannel([])
        msg = fake_message("<@123> ban thằng này được ko", channel=channel)
        await ContextBuilder(recent_limit=20).build(msg, "ban thằng này được ko")
        self.assertTrue(channel.history_called)

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

    async def test_short_bot_to_bot_invite_uses_fifteen_minute_conversation(self):
        anchor = datetime(2026, 10, 17, 13, 31, tzinfo=timezone.utc)
        regiko = SimpleNamespace(id=44, display_name="Regiko")
        lines = [
            SimpleNamespace(
                id=103,
                content="con của a chỉ cần tag là nó ra th",
                author=SimpleNamespace(display_name="Mike", bot=False),
                created_at=anchor - timedelta(seconds=20),
                attachments=[], embeds=[], mentions=[],
            ),
            SimpleNamespace(
                id=102,
                content="giờ cho 2 con bot chơi với nhau đc ko <@44>",
                author=SimpleNamespace(display_name="Mike", bot=False),
                created_at=anchor - timedelta(seconds=50),
                attachments=[], embeds=[], mentions=[regiko],
            ),
            SimpleNamespace(
                id=101,
                content="cũng là nó nhma e ném cho gehihi làm",
                author=SimpleNamespace(display_name="Regiko", bot=False),
                created_at=anchor - timedelta(minutes=1),
                attachments=[], embeds=[], mentions=[],
            ),
            SimpleNamespace(
                id=100,
                content="chuyện hoàn toàn khác cũ hơn 15 phút",
                author=SimpleNamespace(display_name="Bystander", bot=False),
                created_at=anchor - timedelta(minutes=16),
                attachments=[], embeds=[], mentions=[],
            ),
        ]
        channel = _FakeHistoryChannel(lines)
        msg = fake_message("<@123> chơi ko?", channel=channel)
        msg.created_at = anchor
        ctx = await ContextBuilder().build(msg, "chơi ko?")
        prompt = _build_prompt("chơi ko?", None, ctx)

        self.assertTrue(channel.history_called)
        self.assertEqual(channel.history_kwargs["after"], anchor - timedelta(minutes=15))
        self.assertEqual(channel.history_kwargs["before"], msg)
        self.assertEqual([line.message_id for line in ctx.recent], [101, 102, 103])
        self.assertIn("2 con bot chơi với nhau", prompt)
        self.assertIn("@Regiko", prompt)
        self.assertIn("lời đề nghị", prompt)
        self.assertIn("bot nào được rủ tham gia", prompt)
        self.assertNotIn("chuyện hoàn toàn khác", prompt)

    async def test_recent_bot_messages_and_replies_keep_speaker_roles(self):
        anchor = datetime(2026, 10, 17, 13, 31, tzinfo=timezone.utc)
        person = SimpleNamespace(id=44, display_name="Regiko")
        bot_message = SimpleNamespace(
            id=11,
            content="<@44> thử turn based đi",
            mentions=[person],
            author=SimpleNamespace(display_name="GehihiBot", bot=True),
            created_at=anchor - timedelta(seconds=50),
            attachments=[], embeds=[],
            reference=SimpleNamespace(
                resolved=SimpleNamespace(author=SimpleNamespace(display_name="Mike"))
            ),
        )
        msg = fake_message("<@123> chơi ko?", channel=_FakeHistoryChannel([bot_message]))
        msg.created_at = anchor
        ctx = await ContextBuilder().build(msg, "chơi ko?")
        prompt = _build_prompt("chơi ko?", None, ctx)

        self.assertIn("GehihiBot: [reply to Mike] @Regiko thử turn based", prompt)
        self.assertEqual(ctx.recent[0].author, "GehihiBot")

    async def test_recent_context_prefers_newest_and_caps_message_count(self):
        anchor = datetime(2026, 10, 17, 13, 31, tzinfo=timezone.utc)
        recent = [
            SimpleNamespace(
                id=n, content=f"message {n}",
                author=SimpleNamespace(display_name="User"),
                created_at=anchor - timedelta(seconds=n),
                attachments=[], embeds=[],
            )
            for n in (1, 2, 3, 4)
        ]
        channel = _FakeHistoryChannel(recent)
        msg = fake_message("<@123> ừ", channel=channel)
        msg.created_at = anchor
        ctx = await ContextBuilder(recent_limit=2).build(msg, "ừ")
        self.assertEqual([line.message_id for line in ctx.recent], [2, 1])
        self.assertEqual(channel.history_kwargs["limit"], 2)

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


class AssistantSocialReplyBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def _context(self):
        return AssistantContext(
            requester="Mike",
            mentioned_people=[(44, "Công túa Bông Gòn")],
            social_referent="Công túa Bông Gòn",
            social_referent_source="mention trong lời yêu cầu",
            recent=[
                SimpleNamespace(
                    author="Công túa Bông Gòn",
                    content="thấy tên t dễ thương khôngmmm",
                ),
            ],
        )

    def test_reported_dm_request_becomes_explicit_teasing_instruction(self):
        from features.assistant.social import (
            plan_social_reply, is_social_reply_on_target,
        )
        context = self._context()
        plan = plan_social_reply("đm <@44>", context)
        self.assertEqual(plan.mode, "tease")
        self.assertEqual(plan.target, "Công túa Bông Gòn")
        self.assertIn("dễ thương", plan.topic_hint)

        prompt = _build_prompt("đm <@44>", None, context)
        self.assertIn("TRỰC TIẾP VỚI Công túa Bông Gòn", prompt)
        self.assertIn("ĐỪNG hỏi ngược người gọi", prompt)
        self.assertFalse(is_social_reply_on_target(
            "Hô hô, lại tính làm gì @Công túa Bông Gòn đấy Mike? "
            "Định gọi ra để flex hay tính phá gì tiếp đấy :))", plan
        ))
        self.assertTrue(is_social_reply_on_target(
            "Bông Gòn ơi, dễ thương thì tự nhận vừa vừa thôi, "
            "server còn chỗ cho người khác tự tin nữa =)))", plan
        ))
        self.assertFalse(is_social_reply_on_target(
            "Mike ơi, đừng trêu Bông Gòn nữa nhé =)))", plan
        ))

    def test_slang_and_real_moderation_are_not_mixed(self):
        from features.assistant.social import plan_social_reply
        ctx = AssistantContext(
            requester="Satoou",
            mentioned_people=[(30, "Mike")],
            social_referent="Mike",
        )
        self.assertEqual(plan_social_reply("chan <@30>", ctx).mode, "challenge")
        self.assertIn("'chan' LÀ TỪ LÓNG", _build_prompt("chan <@30>", None, ctx))
        self.assertIsNone(plan_social_reply("ban <@30> vì spam liên tục", ctx))
        self.assertIsNone(plan_social_reply("lúc nào Mike về?", ctx))
        ctx.mentioned_people = [(30, "Mike"), (44, "Bông Gòn")]
        self.assertIsNone(plan_social_reply("sấy <@30> với <@44>", ctx))

    async def test_bad_target_response_is_rejected_then_regenerated(self):
        context = self._context()
        fake_bad = SimpleNamespace(text=(
            "Hô hô, lại tính làm gì Bông Gòn đấy Mike? "
            "Định gọi ra để flex hay tính phá gì tiếp đây?"))
        fake_good = SimpleNamespace(text=(
            "Bông Gòn ơi, flex tên dễ thương hơi nhiều rồi, "
            "để dành tí spotlight cho người khác với =)))"))
        with patch(
            "features.assistant.ai.bounded_ai_generate",
            new=AsyncMock(side_effect=[fake_bad, fake_good]),
        ) as generate:
            result = await generate_chat_reply("đm <@44>", context=context)
        self.assertEqual(generate.await_count, 2)
        self.assertEqual(result.text, fake_good.text)
        retry_prompt = generate.await_args_list[1].kwargs["contents"][0].parts[0].text
        self.assertIn("BẢN NHÁP TRƯỚC BỊ TỪ CHỐI", retry_prompt)
        self.assertIn("Không hỏi Mike", retry_prompt)

    async def test_both_role_reversed_outputs_use_safe_target_fallback(self):
        context = self._context()
        bad = SimpleNamespace(text="Hô hô, Mike định gọi Bông Gòn ra làm gì?")
        with patch(
            "features.assistant.ai.bounded_ai_generate",
            new=AsyncMock(side_effect=[bad, bad]),
        ) as generate:
            result = await generate_chat_reply("đm <@44>", context=context)
        self.assertEqual(generate.await_count, 2)
        self.assertEqual(result.model, "local_social_fallback")
        self.assertIn("Bông Gòn", result.text)
        self.assertNotIn("Mike", result.text)

    async def test_normal_conversation_does_not_use_social_guard(self):
        context = self._context()
        reply = SimpleNamespace(text="Hô hô, Mike đang hỏi gì về bài hát vậy?")
        with patch(
            "features.assistant.ai.bounded_ai_generate",
            new=AsyncMock(return_value=reply),
        ) as generate:
            result = await generate_chat_reply("bài này tên gì?", context=context)
        self.assertEqual(generate.await_count, 1)
        self.assertEqual(result.text, reply.text)


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
    def test_chat_defaults_to_quality_flash(self):
        with patch.dict("os.environ", {}, clear=True):
            models = _candidate_models()
        self.assertEqual(models[0], "gemini-3.8-flash")

    def test_chat_model_can_be_overridden(self):
        with patch("core.constants.ASUMI_CHAT_MODEL", "gemini-custom-chat"):
            models = _candidate_models()
        self.assertEqual(models, ["gemini-3.8-flash"])


class AssistantAdaptiveModelTests(unittest.IsolatedAsyncioTestCase):
    def test_depth_tiers_have_fixed_backend_allowlist(self):
        self.assertEqual(_candidate_models("fast")[0], "gemini-3.5-flash-lite")
        self.assertEqual(_candidate_models("balanced")[0], "gemini-3.8-flash")
        self.assertEqual(_candidate_models("deep"), ["gemini-3.8-flash"])
        self.assertNotIn("gemini-3.1-pro-preview", _candidate_models("deep"))
        self.assertEqual(_candidate_models("arbitrary-model")[0], "gemini-3.8-flash")

    async def test_clef_high_confidence_depth_drives_chat_routing_only(self):
        router = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(return_value=ClefDecision("chat", 0.95, "deep")),
        )
        decision = await route_message(
            "Giải thích và phân tích trade-off kiến trúc microfrontend nhiều bên",
            cloudflare_router=router,
        )
        self.assertEqual(decision.intent, "chat")
        self.assertEqual(decision.model_tier, "deep")

    def test_deep_uses_more_thinking_on_same_flash_model(self):
        self.assertEqual(_candidate_models("balanced")[0], _candidate_models("deep")[0])
        per_model, total, attempts = _chat_limits("deep")
        self.assertEqual((per_model, total, attempts), (12.0, 22.0, 2))

    def test_clef_does_not_accept_untrusted_deep_choice(self):
        self.assertEqual(CloudflareDecisionRouter._parse_depth({
            "choice": "deep", "confidence": 0.55,
        }), "balanced")
        self.assertEqual(CloudflareDecisionRouter._parse_depth({
            "choice": ["deep"], "confidence": 0.99,
        }), "balanced")


class AssistantChatTimeoutBudgetTests(unittest.IsolatedAsyncioTestCase):
    def test_default_chat_limits_are_fast_fail(self):
        with patch.dict("os.environ", {}, clear=True):
            per_model, total_budget, max_attempts = _chat_limits()
        self.assertEqual(per_model, 12.0)
        self.assertEqual(total_budget, 18.0)
        self.assertEqual(max_attempts, 2)

    def test_default_fallback_prefers_lightweight_model(self):
        with patch.dict("os.environ", {}, clear=True):
            models = _candidate_models()
        self.assertEqual(models[0], "gemini-3.8-flash")
        self.assertEqual(models, ["gemini-3.8-flash"])

    async def test_total_budget_prevents_second_attempt_after_exhaustion(self):
        with patch.dict(
            "os.environ",
            {
                "ASUMI_CHAT_MODEL_TIMEOUT_SECONDS": "4",
                "ASUMI_CHAT_TOTAL_BUDGET_SECONDS": "8",
                "ASUMI_CHAT_MAX_ATTEMPTS": "2",
            },
            clear=True,
        ), patch(
            "features.assistant.ai.bounded_ai_generate",
            new=AsyncMock(side_effect=TimeoutError()),
        ) as generate, patch(
            "features.assistant.ai.time.perf_counter",
            side_effect=[0.0, 0.0, 0.0, 8.0, 18.0],
        ):
            with self.assertRaises(ChatTimeoutBudgetError) as ctx:
                await generate_chat_reply("hello")

        self.assertEqual(generate.await_count, 1)
        self.assertEqual(ctx.exception.attempts, 1)
        self.assertEqual(ctx.exception.budget_seconds, 18.0)

    async def test_timeout_does_not_downgrade_general_to_lite(self):
        with patch("features.assistant.ai.bounded_ai_generate",
                   new=AsyncMock(side_effect=TimeoutError("slow"))) as generate:
            with self.assertRaises(ChatTimeoutBudgetError) as raised:
                await generate_chat_reply("Giải thích kiến trúc phần mềm")
        self.assertEqual(generate.await_count, 1)
        self.assertEqual(generate.await_args.kwargs["model"], "gemini-3.8-flash")
        self.assertEqual(raised.exception.models_tried, ("gemini-3.8-flash",))


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
