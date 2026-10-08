"""T22.2 Discord history recall: date parsing, native API and ACL fail-closed."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from zoneinfo import ZoneInfo

from features.assistant.cog import choose_conversation_route
from features.assistant.providers.discord_history import (
    DiscordHistorySearcher, HistoryHit, HistorySearchResult,
    _date_filter, _snowflake, _terms,
)
from features.assistant.router import route_locally
from features.assistant.tools import CommandToolRegistry


class HistoryFilterTests(unittest.TestCase):
    def test_early_year_resolves_first_quarter_in_vietnam(self):
        start, end = _date_filter(
            "đầu năm @Theo có nhắn gì về mua xe",
            now=datetime(2026, 10, 8, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        )
        self.assertEqual(start.date().isoformat(), "2026-01-01")
        self.assertEqual(end.date().isoformat(), "2026-04-01")
        self.assertLess(_snowflake(start), _snowflake(end))

    def test_month_and_last_year_filters(self):
        now = datetime(2026, 10, 8, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        start, end = _date_filter("tháng 2 năm 2025", now=now)
        self.assertEqual(start.date().isoformat(), "2025-02-01")
        self.assertEqual(end.date().isoformat(), "2025-03-01")
        start2, end2 = _date_filter("năm ngoái", now=now)
        self.assertEqual(start2.year, 2025)
        self.assertEqual(end2.year, 2026)

    def test_vehicle_synonyms_are_bounded(self):
        self.assertEqual(
            _terms("đầu năm người này nói về mua xe"),
            ("mua xe", "đổi xe", "xe mới"),
        )

    def test_local_route_is_history_not_archive(self):
        self.assertEqual(
            route_locally("hãy tìm xem đầu năm @Theo có nhắn gì về mua xe").tool,
            "discord_history.search",
        )
        self.assertEqual(
            route_locally("tìm lại meme mèo").tool,
            "archive.search",
        )


class HistoryPermissionsTests(unittest.TestCase):
    @staticmethod
    def make_guild(can_view=True, is_private_thread=False, parent_can_view=True):
        requester = SimpleNamespace(id=10)
        bot = SimpleNamespace(id=99)
        def perms(member):
            visible = can_view if member.id == 10 else True
            return SimpleNamespace(
                view_channel=visible, read_message_history=visible,
            )
        async def fetch_live(mid):
            return SimpleNamespace(
                id=mid, content="đang định mua xe mới",
                author=SimpleNamespace(id=44, display_name="Theo"),
            )
        channel = SimpleNamespace(
            type="private_thread" if is_private_thread else "text",
            permissions_for=perms,
            fetch_message=AsyncMock(side_effect=fetch_live),
            parent=SimpleNamespace(
                permissions_for=lambda member: SimpleNamespace(
                    view_channel=parent_can_view,
                    read_message_history=parent_can_view,
                )
            ),
        )
        guild = SimpleNamespace(
            id=777, me=bot,
            get_channel_or_thread=lambda channel_id: channel if channel_id == 55 else None,
            get_member=lambda user_id: requester if user_id == 10 else None,
        )
        return guild, requester

    def test_requester_without_view_history_cannot_see_message(self):
        guild, requester = self.make_guild(can_view=False)
        self.assertFalse(DiscordHistorySearcher._can_show(guild, requester, 55))

    def test_uncached_channels_and_private_threads_fail_closed(self):
        guild, requester = self.make_guild()
        self.assertFalse(DiscordHistorySearcher._can_show(guild, requester, 999))
        guild2, requester2 = self.make_guild(is_private_thread=True)
        self.assertFalse(DiscordHistorySearcher._can_show(guild2, requester2, 55))

    def test_parent_channel_access_is_required(self):
        guild, requester = self.make_guild(parent_can_view=False)
        self.assertFalse(DiscordHistorySearcher._can_show(guild, requester, 55))

    def test_visible_channel_passes(self):
        guild, requester = self.make_guild()
        self.assertTrue(DiscordHistorySearcher._can_show(guild, requester, 55))


class HistoryApiTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self, *, can_view=True):
        guild, requester = HistoryPermissionsTests.make_guild(can_view=can_view)
        requested_author = SimpleNamespace(id=44)
        msg = SimpleNamespace(
            id=200,
            author=requester,
            guild=guild,
            mentions=[guild.me, requested_author],
        )
        bot = SimpleNamespace(http=SimpleNamespace(token="fake-token"))
        provider = DiscordHistorySearcher(bot, enabled=True, max_calls=1)
        return provider, msg

    async def call_with_response(self, response_status, payload, *, can_view=True):
        provider, message = self.make_context(can_view=can_view)

        class FakeResponse:
            status = response_status
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def json(self):
                return payload

        class FakeSession:
            def __init__(self, **kwargs):
                self.query_params = None
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            def get(self, url, *, headers, params):
                assert headers["Authorization"] == "Bot fake-token"
                assert params["author_id"] == "44"
                return FakeResponse()

        with patch(
            "features.assistant.providers.discord_history.aiohttp.ClientSession",
            FakeSession,
        ):
            return await provider.search(
                message, "đầu năm @Theo có nhắn gì về mua xe?"
            )

    async def test_real_message_is_returned_with_exact_jump_url(self):
        payload = {"messages": [[{
            "id": "124", "channel_id": "55",
            "content": "đang định mua xe mới",
            "author": {"id": "44", "username": "Theo"},
            "timestamp": "2026-02-15T10:00:00+00:00",
        }]]}
        result = await self.call_with_response(200, payload)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.hits[0].author_id, 44)
        self.assertTrue(bool(result.start_date))
        self.assertEqual(result.hits[0].content, "đang định mua xe mới")
        self.assertEqual(result.hits[0].jump_url, "https://discord.com/channels/777/55/124")

    async def test_private_channel_result_is_not_leaked(self):
        payload = {"messages": [[{
            "id": "124", "channel_id": "55",
            "content": "private car purchase plan",
            "author": {"id": "44", "username": "Theo"},
        }]]}
        result = await self.call_with_response(200, payload, can_view=False)
        self.assertEqual(result.status, "no_results")
        self.assertEqual(result.hits, ())
        self.assertEqual(result.rejected_for_permissions, 1)

    async def test_index_not_ready_is_not_reported_as_no_results(self):
        result = await self.call_with_response(202, {"retry_after": 2})
        self.assertEqual(result.status, "indexing")

    async def test_429_is_safe(self):
        result = await self.call_with_response(429, {})
        self.assertEqual(result.status, "rate_limited")

    async def test_disabled_search_is_noop(self):
        provider, msg = self.make_context()
        provider.enabled = False
        result = await provider.search(msg, "mua xe")
        self.assertEqual(result.status, "disabled")


class HistoryToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_history_search_beats_session_followup(self):
        route = await choose_conversation_route(
            "tìm tin nhắn hồi đầu năm về mua xe",
            previous_session=SimpleNamespace(intent="chat"),
            is_live_continuation=True,
            has_images=False,
            cloudflare_router=None,
            min_confidence=0.55,
        )
        self.assertEqual(route.tool, "discord_history.search")

    async def test_history_tool_returns_jump_and_no_raw_data_in_telemetry(self):
        bot = SimpleNamespace()
        registry = CommandToolRegistry(bot)
        message = SimpleNamespace(
            author=SimpleNamespace(id=10),
            reply=AsyncMock(return_value=SimpleNamespace(id=913)),
        )
        report = HistorySearchResult(
            status="ok",
            hits=(HistoryHit(
                message_id=124, channel_id=55, author_id=44,
                author_name="Theo", content="Tôi đang mua xe @everyone",
                date="2026-02-15",
                jump_url="https://discord.com/channels/777/55/124",
            ),),
            start_date="2026-01-01", end_date="2026-03-31",
            api_calls=1,
        )
        registry.history.search = AsyncMock(return_value=report)
        result = await registry.execute(
            route_locally("tìm tin nhắn về mua xe"),
            message,
        )
        rendered = message.reply.await_args.args[0]
        self.assertIn("https://discord.com/channels/777/55/124", rendered)
        self.assertNotIn("@everyone", rendered)
        self.assertNotIn("source_content", result.details)
        self.assertNotIn("query", result.details)
        self.assertEqual(result.details["history_result_count"], 1)


if __name__ == "__main__":
    unittest.main()
