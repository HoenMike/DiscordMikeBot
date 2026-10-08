"""T22.1 Brave Search: explicit routing, privacy, durable budget and result UX."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiosqlite

from core.db import AsyncQueryContext, CursorWrapper
from features.assistant.cog import choose_conversation_route
from features.assistant.providers.brave import BraveHit, BraveSearchAdapter, BraveSearchResult
from features.assistant.router import route_locally
from features.assistant.tools import CommandToolRegistry


class InMemoryQuotaDB:
    """Mock Turso adapter with a real SQLite quota table."""
    def __init__(self, conn):
        self.conn = conn
        self.is_cloud = True

    async def connect(self):
        return None

    def execute(self, sql, params=()):
        async def run():
            cursor = await self.conn.execute(sql, params)
            rows = await cursor.fetchall()
            result = CursorWrapper(
                rows, last_insert_id=cursor.lastrowid,
                rows_affected=cursor.rowcount,
            )
            await cursor.close()
            return result
        return AsyncQueryContext(run())

    async def commit(self):
        await self.conn.commit()


class BraveRouterTests(unittest.IsolatedAsyncioTestCase):
    def test_explicit_vietnamese_search_preserves_accents(self):
        decision = route_locally("tìm trên web giá xe mới năm 2026")
        self.assertEqual(decision.tool, "web.search")
        self.assertEqual(decision.arguments["query"], "giá xe mới năm 2026")

    def test_general_question_does_not_spend_search_budget(self):
        self.assertIsNone(route_locally("xe điện có tốt không?").tool)

    def test_archive_search_is_still_archive(self):
        self.assertEqual(route_locally("tìm lại meme mèo").tool, "archive.search")

    async def test_explicit_web_search_beats_live_followup(self):
        result = await choose_conversation_route(
            "tìm trên web game mới",
            previous_session=SimpleNamespace(intent="tarot_daily"),
            is_live_continuation=True,
            has_images=False,
            cloudflare_router=None,
            min_confidence=0.55,
        )
        self.assertEqual(result.tool, "web.search")


class BraveQuotaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = await aiosqlite.connect(":memory:")
        self.db = InMemoryQuotaDB(self.conn)
        self.patch_db = patch("features.assistant.providers.brave.db_client", self.db)
        self.patch_db.start()
        self.patch_token = patch("features.assistant.providers.brave.config.TURSO_AUTH_TOKEN", "test")
        self.patch_token.start()
        self.patch_url = patch("features.assistant.providers.brave.config.TURSO_DATABASE_URL", "libsql://db")
        self.patch_url.start()

    async def asyncTearDown(self):
        self.patch_db.stop()
        self.patch_token.stop()
        self.patch_url.stop()
        await self.conn.close()

    async def test_monthly_limit_survives_adapter_restart(self):
        first = BraveSearchAdapter(api_key="test", enabled=True, monthly_cap=2)
        second = BraveSearchAdapter(api_key="test", enabled=True, monthly_cap=2)
        self.assertEqual(await first._reserve_request(), 1)
        self.assertEqual(await second._reserve_request(), 0)
        self.assertIsNone(await second._reserve_request())

    async def test_local_fallback_refuses_paid_request(self):
        self.db.is_cloud = False
        index = BraveSearchAdapter(api_key="test", enabled=True)
        with self.assertRaises(RuntimeError):
            await index._reserve_request()


class BraveProviderTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, **kwargs):
        return BraveSearchAdapter(
            api_key="test", enabled=True, cooldown_seconds=20,
            cache_ttl_seconds=180, **kwargs,
        )

    async def test_private_discord_mention_never_reserves_quota(self):
        provider = self.make_adapter()
        provider._reserve_request = AsyncMock(return_value=499)
        result = await provider.search("tin của <@123456789012345678>", 17)
        self.assertEqual(result.status, "private_reference")
        provider._reserve_request.assert_not_awaited()

    async def test_private_discord_link_never_reserves_quota(self):
        provider = self.make_adapter()
        provider._reserve_request = AsyncMock(return_value=499)
        result = await provider.search(
            "https://discord.com/channels/100/200/300", 17,
        )
        self.assertEqual(result.status, "private_reference")
        provider._reserve_request.assert_not_awaited()

    async def test_same_query_cache_skips_second_paid_request(self):
        provider = self.make_adapter()
        provider._reserve_request = AsyncMock(return_value=499)

        class FakeResponse:
            status = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def json(self):
                return {"web": {"results": [{
                    "title": "News", "url": "https://example.org/news",
                    "description": "Recent announcement",
                }]}}

        class FakeSession:
            def __init__(self, **kwargs):
                self.calls = 0
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            def get(self, *args, **kwargs):
                return FakeResponse()

        with patch("features.assistant.providers.brave.aiohttp.ClientSession", FakeSession):
            first = await provider.search("latest announcement", 17)
            second = await provider.search("latest announcement", 17)

        self.assertEqual(first.status, "ok")
        self.assertTrue(second.cache_hit)
        self.assertEqual(provider._reserve_request.await_count, 1)

    async def test_user_cooldown_avoids_additional_calls(self):
        provider = self.make_adapter()
        provider._last_request_by_user[17] = __import__("time").monotonic()
        provider._reserve_request = AsyncMock(return_value=499)
        result = await provider.search("something different", 17)
        self.assertEqual(result.status, "cooldown")
        provider._reserve_request.assert_not_awaited()

    def test_parser_rejects_unsafe_and_duplicate_links(self):
        provider = self.make_adapter()
        data = {"web": {"results": [
            {"title": "OK", "url": "https://example.org/a", "description": "X"},
            {"title": "dup", "url": "https://example.org/a"},
            {"title": "bad", "url": "javascript:alert(1)"},
            {"title": "unsafe", "url": "https://bad.org/x>\nBAD"},
        ]}}
        self.assertEqual(len(provider._parse_hits(data, 5)), 1)

    async def test_tool_displays_links_but_no_private_prompt_in_metrics(self):
        registry = CommandToolRegistry(SimpleNamespace())
        message = SimpleNamespace(
            author=SimpleNamespace(id=17),
            reply=AsyncMock(return_value=SimpleNamespace(id=911)),
        )
        answer = BraveSearchResult(
            status="ok", hits=(BraveHit(
                title="Official page",
                url="https://example.org/news",
                description="Hello @everyone",
            ),), elapsed_ms=50.1, remaining=499,
        )
        with patch(
            "features.assistant.tools.brave_search.search",
            new=AsyncMock(return_value=answer),
        ):
            result = await registry.execute(
                route_locally("tìm trên web tin mới"), message,
            )
        body = message.reply.await_args.args[0]
        self.assertIn("https://example.org/news", body)
        self.assertNotIn("@everyone", body)
        self.assertEqual(result.details["web_provider"], "brave")
        self.assertNotIn("query", result.details)
        self.assertNotIn("source_content", result.details)


if __name__ == "__main__":
    unittest.main()
