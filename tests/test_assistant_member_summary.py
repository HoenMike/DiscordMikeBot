"""Asumi 3.7.8: member-only natural language recap must not summarize whole channel."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.router import route_locally, route_message
from features.assistant.cog import choose_conversation_route
from features.assistant.tools import CommandToolRegistry
from features.summary.cog import SummaryCog


USER_ID = 123456789012345678
OTHER_ID = 123456789012345679

def make_line(uid, content, at, bot=False):
    return SimpleNamespace(
        author=SimpleNamespace(
            id=uid, bot=bot,
            display_name="TargetUser" if uid == USER_ID else "OtherUser",
        ),
        content=content, created_at=at,
    )


class SummaryRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_screenshot_intent_is_member_not_channel(self):
        q = f"tóm tắt xem qua giờ <@{USER_ID}> đã nhắn gì"
        decision = route_locally(q)
        self.assertEqual(decision.tool, "summary.member")
        self.assertEqual(decision.arguments["author_ids"], [USER_ID])
        self.assertNotIn("hours", decision.arguments)

    async def test_explicit_hours_and_nickname_mention(self):
        q = f"tóm tắt trong 1 giờ qua <@!{USER_ID}> đã nói gì"
        decision = route_locally(q)
        self.assertEqual(decision.tool, "summary.member")
        self.assertEqual(decision.arguments["hours"], 1.0)

    async def test_non_member_summary_remains_original(self):
        self.assertEqual(route_locally("tóm tắt 2 giờ qua").tool, "summary.catchup")
        self.assertEqual(
            (await route_message(f"tóm tắt xem qua giờ <@{USER_ID}> đã nhắn gì")).tool,
            "summary.member",
        )

    async def test_member_request_overrides_prior_chat_reply(self):
        q = f"tóm tắt xem qua giờ <@{USER_ID}> đã nhắn gì"
        choice = await choose_conversation_route(
            q, previous_session=SimpleNamespace(intent="chat"),
            is_live_continuation=True, has_images=False,
            cloudflare_router=None, min_confidence=0.55,
        )
        self.assertEqual(choice.tool, "summary.member")

    async def test_multiple_tags_do_not_silently_select_author(self):
        q = f"tóm tắt xem <@{USER_ID}> và <@{OTHER_ID}> đã nhắn gì"
        self.assertEqual(
            route_locally(q).arguments["author_ids"], [USER_ID, OTHER_ID]
        )


class ChannelFilterTests(unittest.IsolatedAsyncioTestCase):
    async def run_filter(self, *, mode="hours", target=USER_ID):
        now = datetime.now(timezone.utc)
        records = [
            make_line(USER_ID, "Target only A", now - timedelta(minutes=40)),
            make_line(OTHER_ID, "OTHER SECRET MUST NOT LEAK", now - timedelta(minutes=30)),
            make_line(USER_ID, "Target only B", now - timedelta(minutes=20)),
            make_line(USER_ID, "Old target", now - timedelta(hours=5)),
            make_line(OTHER_ID, "Bot secret", now - timedelta(minutes=10), bot=True),
        ]
        channel = SimpleNamespace()
        async def history(**kwargs):
            selected = records
            if kwargs.get("after") is not None and isinstance(kwargs["after"], datetime):
                selected = [m for m in selected if m.created_at > kwargs["after"]]
            if kwargs.get("before") is not None and isinstance(kwargs["before"], datetime):
                selected = [m for m in selected if m.created_at < kwargs["before"]]
            if kwargs.get("oldest_first"):
                selected = sorted(selected, key=lambda m: m.created_at)
            else:
                selected = sorted(selected, key=lambda m: m.created_at, reverse=True)
            for item in selected:
                yield item
        channel.history = history
        kw = {"target_channel": channel, "author_filter_id": target}
        if mode == "hours":
            kw["hours"] = 2
        elif mode == "date":
            kw["start_time_utc"] = now - timedelta(hours=2)
            kw["end_time_utc"] = now
        elif mode == "anchor":
            # Simulated Snowflake bound; validates author filter in anchor path.
            kw["after_message_id"] = 123456789012345600
        return await SummaryCog._fetch_messages(**kw)

    async def test_one_author_only_in_every_scan_mode(self):
        for mode in ("hours", "date", "anchor"):
            with self.subTest(mode=mode):
                lines, time_span = await self.run_filter(mode=mode)
                self.assertTrue(lines)
                self.assertTrue(all("TargetUser:" in x for x in lines))
                self.assertNotIn("OTHER SECRET", str(lines))
                self.assertNotIn("Bot secret", str(lines))
                self.assertTrue(time_span)

    async def test_no_author_messages_returns_empty(self):
        messages, interval = await self.run_filter(target=123456789012345680)
        self.assertEqual(messages, [])
        self.assertEqual(interval, "Không có tin nhắn")


class MemberToolTests(unittest.IsolatedAsyncioTestCase):
    def setup_request(self, *, people=None, allow=True):
        requester = SimpleNamespace(id=11)
        bot = SimpleNamespace(id=99)
        target = SimpleNamespace(id=USER_ID, display_name="I'm BD", name="BD")
        channel = SimpleNamespace()
        channel.permissions_for = lambda who: SimpleNamespace(
            view_channel=allow, read_message_history=allow
        )
        guild = SimpleNamespace(me=bot)
        channel.guild = guild
        message = SimpleNamespace(
            author=requester, guild=guild, channel=channel,
            mentions=[bot, target] if people is None else people,
            reply=AsyncMock(return_value=SimpleNamespace(id=100)),
        )
        cog = SimpleNamespace(_execute_summary_flow=AsyncMock())
        api = SimpleNamespace(
            get_cog=lambda name: cog if name == "SummaryCog" else None,
            get_context=AsyncMock(return_value=SimpleNamespace()),
            user=bot,
        )
        return CommandToolRegistry(api), message, cog, api

    async def test_member_summary_uses_real_cog_with_correct_filter(self):
        registry, msg, cog, bot = self.setup_request()
        decision = route_locally(f"tóm tắt xem qua giờ <@{USER_ID}> đã nhắn gì")
        with patch.object(registry, "_capture_bot_outputs",
                          new=AsyncMock(return_value=((), ""))):
            result = await registry.execute(decision, msg)
        self.assertTrue(result.handled)
        self.assertEqual(result.details["summary_scope"], "member")
        self.assertEqual(result.details["summary_hours"], 2)
        kwargs = cog._execute_summary_flow.await_args.kwargs
        self.assertEqual(kwargs["author_filter_id"], USER_ID)
        self.assertEqual(kwargs["author_display_name"], "I'm BD")
        self.assertIs(kwargs["target_channel"], msg.channel)
        bot.get_context.assert_awaited_once_with(msg)
        msg.reply.assert_not_awaited()

    async def test_missing_mention_or_ambiguous_author_rejected(self):
        registry, msg, cog, _ = self.setup_request(people=[])
        decision = route_locally(f"tóm tắt <@{USER_ID}> đã nhắn gì")
        await registry.execute(decision, msg)
        self.assertIn("Không xác nhận được", msg.reply.await_args.args[0])
        cog._execute_summary_flow.assert_not_awaited()
        registry2, msg2, cog2, _ = self.setup_request()
        await registry2.execute(route_locally(
            f"tóm tắt <@{USER_ID}> và <@{OTHER_ID}> đã nhắn gì"
        ), msg2)
        self.assertIn("một người", msg2.reply.await_args.args[0])
        cog2._execute_summary_flow.assert_not_awaited()

    async def test_no_channel_history_permissions_denies_summary(self):
        registry, msg, cog, _ = self.setup_request(allow=False)
        await registry.execute(route_locally(
            f"tóm tắt <@{USER_ID}> đã nhắn gì"
        ), msg)
        self.assertIn("Không đủ quyền", msg.reply.await_args.args[0])
        cog._execute_summary_flow.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
