"""T22.4a chronological historical message queries (no passive indexing)."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.providers.discord_history import (
    DiscordHistorySearcher,
    _temporal_request,
    _temporal_terms,
)
from features.assistant.router import route_locally


class TemporalParsingTests(unittest.TestCase):
    def test_first_and_last_without_topic(self):
        self.assertEqual(
            _temporal_request("tìm lại tin nhắn đầu tiên của <@44> trong server"),
            ("oldest", 1),
        )
        self.assertEqual(
            _temporal_request("tìm 5 tin nhắn đầu tiên của <@44>"),
            ("oldest", 5),
        )
        self.assertEqual(
            _temporal_request("tìm tin nhắn gần nhất của <@44>"),
            ("newest", 1),
        )
        self.assertIsNone(_temporal_request("đầu năm <@44> nói về xe"))
        self.assertEqual(_temporal_terms("tin nhắn đầu tiên của <@44> trong server"), ("",))

    def test_topic_extraction_and_routing(self):
        self.assertEqual(
            _temporal_terms("lần đầu <@44> nhắc tới Minecraft là khi nào?"),
            ("minecraft",),
        )
        self.assertEqual(
            _temporal_terms("tin nhắn đầu tiên của <@44> về Minecraft"),
            ("minecraft",),
        )
        self.assertEqual(
            route_locally("lần đầu <@44> nhắc tới Minecraft là khi nào?").tool,
            "discord_history.search",
        )
        self.assertEqual(
            route_locally("tìm lại tin nhắn đầu tiên của <@44> trong server").tool,
            "discord_history.search",
        )


class TemporalApiTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self, *, mention=True, can_view=True):
        member = SimpleNamespace(id=10)
        bot_member = SimpleNamespace(id=99)
        def perms(target):
            visible = can_view if target.id == 10 else True
            return SimpleNamespace(
                view_channel=visible, read_message_history=visible
            )
        async def fetch(mid):
            return SimpleNamespace(
                id=mid, content=f"Original message {mid}",
                author=SimpleNamespace(id=44, display_name="Test User"),
            )
        channel = SimpleNamespace(
            type="text",
            permissions_for=perms,
            fetch_message=AsyncMock(side_effect=fetch),
            parent=None,
        )
        guild = SimpleNamespace(
            id=777, me=bot_member,
            get_member=lambda uid: member if uid == 10 else None,
            get_channel_or_thread=lambda cid: channel if cid == 55 else None,
        )
        message = SimpleNamespace(
            author=member, guild=guild, mentions=(
                [bot_member, SimpleNamespace(id=44)] if mention else [bot_member]
            ),
        )
        return DiscordHistorySearcher(
            SimpleNamespace(http=SimpleNamespace(token="test-token")),
            enabled=True, max_calls=3, max_results=5,
        ), message, channel

    async def search_with_payloads(self, query, payloads, *, mention=True, can_view=True):
        provider, message, channel = self.make_context(mention=mention, can_view=can_view)
        calls = []
        class FakeResponse:
            status = 200
            def __init__(self, payload):
                self.payload = payload
            async def __aenter__(self):
                return self
            async def __aexit__(self, *_):
                return False
            async def json(self):
                return self.payload
        class FakeSession:
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *_):
                return False
            def get(self, url, *, headers, params):
                self_url = url
                assert self_url.endswith("/guilds/777/messages/search")
                assert headers["Authorization"] == "Bot test-token"
                calls.append(dict(params))
                key = params.get("content", "")
                ids = payloads.get(key, ())
                return FakeResponse({
                    "messages": [[{
                        "id": str(mid), "channel_id": "55",
                        "author": {"id": "44", "username": "Test User"},
                        "timestamp": "2026-01-01T00:00:00Z",
                    }] for mid in ids]
                })
        with patch(
            "features.assistant.providers.discord_history.aiohttp.ClientSession",
            FakeSession,
        ):
            result = await provider.search(message, query)
        return result, calls, channel

    async def test_first_author_only_uses_timestamp_ascending_without_content(self):
        result, calls, channel = await self.search_with_payloads(
            "tìm lại tin nhắn đầu tiên của <@44> trong server",
            {"": [100, 101, 102]},
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.sort_mode, "oldest")
        self.assertEqual([h.message_id for h in result.hits], [100])
        self.assertEqual(calls[0]["author_id"], "44")
        self.assertEqual(calls[0]["sort_by"], "timestamp")
        self.assertEqual(calls[0]["sort_order"], "asc")
        self.assertNotIn("content", calls[0])
        self.assertEqual(result.hits[0].jump_url, "https://discord.com/channels/777/55/100")

    async def test_multiple_oldest_and_latest_limit(self):
        result, calls, _ = await self.search_with_payloads(
            "tìm 5 tin nhắn đầu tiên của <@44>", {"": [102, 100, 101, 104, 103, 105]}
        )
        self.assertEqual([h.message_id for h in result.hits], [100, 101, 102, 103, 104])
        newest, latest_calls, _ = await self.search_with_payloads(
            "tìm tin nhắn gần nhất của <@44>", {"": [105, 104, 103]}
        )
        self.assertEqual(newest.sort_mode, "newest")
        self.assertEqual([h.message_id for h in newest.hits], [105])
        self.assertEqual(latest_calls[0]["sort_order"], "desc")

    async def test_first_topic_and_synonyms_merged_in_time_order(self):
        result, calls, _ = await self.search_with_payloads(
            "lần đầu <@44> nhắc tới Minecraft là khi nào?",
            {"minecraft": [123, 121, 122]},
        )
        self.assertEqual([h.message_id for h in result.hits], [121])
        self.assertEqual(calls[0]["content"], "minecraft")

        result2, calls2, _ = await self.search_with_payloads(
            "lần đầu <@44> nói về mua xe?",
            {"mua xe": [160], "đổi xe": [110], "xe mới": [140]},
        )
        self.assertEqual([h.message_id for h in result2.hits], [110])
        self.assertEqual(len(calls2), 3)
        self.assertLessEqual(result2.api_calls, 3)

    async def test_explicit_author_required_and_permission_safe(self):
        missing, calls, _ = await self.search_with_payloads(
            "tìm tin nhắn đầu tiên trong server", {}, mention=False
        )
        self.assertEqual(missing.status, "missing_author")
        self.assertEqual(calls, [])
        hidden, calls2, channel = await self.search_with_payloads(
            "tìm tin nhắn đầu tiên của <@44>", {"": [100]}, can_view=False
        )
        self.assertEqual(hidden.status, "no_results")
        self.assertEqual(hidden.hits, ())
        channel.fetch_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
