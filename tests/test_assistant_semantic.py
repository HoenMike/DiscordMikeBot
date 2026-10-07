import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.providers.vectorize import (
    ArchiveSemanticIndex,
    SemanticMatch,
    SemanticUnavailable,
)
from features.assistant.router import RouteDecision
from features.assistant.tools import CommandToolRegistry


class ArchiveSemanticConfigTests(unittest.TestCase):
    def test_disabled_without_explicit_flag(self):
        with patch.dict(
            "os.environ",
            {
                "CLOUDFLARE_ACCOUNT_ID": "account",
                "CLOUDFLARE_API_TOKEN": "ai-token",
                "CLOUDFLARE_VECTORIZE_TOKEN": "vec-token",
            },
            clear=True,
        ):
            index = ArchiveSemanticIndex.from_env()
        self.assertFalse(index.enabled)

    def test_separate_vectorize_token_is_supported(self):
        with patch.dict(
            "os.environ",
            {
                "CF_ARCHIVE_SEMANTIC_ENABLED": "true",
                "CLOUDFLARE_ACCOUNT_ID": "account",
                "CLOUDFLARE_API_TOKEN": "ai-token",
                "CLOUDFLARE_VECTORIZE_TOKEN": "vec-token",
            },
            clear=True,
        ):
            index = ArchiveSemanticIndex.from_env()
        self.assertTrue(index.enabled)
        self.assertEqual(index.ai_token, "ai-token")
        self.assertEqual(index.vectorize_token, "vec-token")
        self.assertEqual(index.dimensions, 1024)

    def test_namespace_is_owner_scoped(self):
        self.assertEqual(ArchiveSemanticIndex.namespace(123), "u123")

    def test_document_text_contains_archive_context(self):
        item = {
            "source_content": "meme mèo đang ngủ",
            "source_author_name": "Khai",
            "note": "meme vui",
            "source_url": "https://example.com/cat",
            "metadata": {
                "embeds": [{"title": "Cat", "description": "sleepy cat"}],
                "attachments": [{"filename": "cat.png"}],
            },
        }
        text = ArchiveSemanticIndex.document_text(item)
        self.assertIn("meme mèo", text)
        self.assertIn("Khai", text)
        self.assertIn("sleepy cat", text)
        self.assertIn("cat.png", text)


class ArchiveSemanticApiTests(unittest.IsolatedAsyncioTestCase):
    def make_index(self):
        index = ArchiveSemanticIndex(
            account_id="account",
            ai_token="ai",
            vectorize_token="vec",
            enabled=True,
            min_score=0.45,
        )
        index._index_ready = True
        return index

    async def test_query_filters_low_scores_and_uses_owner_namespace(self):
        index = self.make_index()
        index._embed = AsyncMock(return_value=[0.0] * 1024)
        index._json_request = AsyncMock(return_value=(
            200,
            {
                "result": {
                    "matches": [
                        {"id": "12", "score": 0.81},
                        {"id": "13", "score": 0.20},
                    ]
                }
            },
        ))

        matches = await index.query(99, "meme mèo", top_k=8)

        self.assertEqual(matches, [SemanticMatch(archive_id=12, score=0.81)])
        payload = index._json_request.await_args.kwargs["json_body"]
        self.assertEqual(payload["namespace"], "u99")
        self.assertEqual(payload["topK"], 8)
        self.assertFalse(payload["returnValues"])

    async def test_upsert_uses_archive_id_and_owner_namespace(self):
        index = self.make_index()
        index._embed = AsyncMock(return_value=[0.0] * 1024)
        index._json_request = AsyncMock(return_value=(200, {"success": True}))
        item = {
            "id": 12,
            "owner_user_id": 99,
            "source_kind": "message",
            "source_content": "meme mèo",
            "source_author_name": "Khai",
            "note": "",
            "source_url": "",
            "metadata": {},
        }

        self.assertTrue(await index.upsert_item(item))

        raw = index._json_request.await_args.kwargs["file_body"].decode("utf-8")
        self.assertIn('"id": "12"', raw)
        self.assertIn('"namespace": "u99"', raw)

    async def test_permission_failure_circuit_breaks_semantic_mode(self):
        index = self.make_index()
        index._index_ready = False
        index._json_request = AsyncMock(
            side_effect=SemanticUnavailable("permission")
        )

        matches = await index.query(99, "anything")

        self.assertEqual(matches, [])


class ArchiveHybridSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_matches_precede_lexical_and_dedupe(self):
        registry = CommandToolRegistry(SimpleNamespace())
        sent = SimpleNamespace(id=900)
        message = SimpleNamespace(
            author=SimpleNamespace(id=99),
            reply=AsyncMock(return_value=sent),
        )
        decision = RouteDecision(
            intent="archive_search",
            tool="archive.search",
            arguments={"query": "con vật nằm ngủ"},
        )
        semantic_item = {
            "id": 2,
            "source_content": "meme mèo đang ngủ",
            "source_author_name": "Khai",
            "source_jump_url": "",
            "source_url": "",
        }
        lexical_duplicate = {
            "id": 2,
            "source_content": "meme mèo đang ngủ",
            "source_author_name": "Khai",
            "source_jump_url": "",
            "source_url": "",
        }
        lexical_other = {
            "id": 1,
            "source_content": "ảnh chó đang nằm",
            "source_author_name": "Theo",
            "source_jump_url": "",
            "source_url": "",
        }

        with patch(
            "features.assistant.tools.archive_store.search",
            new=AsyncMock(return_value=[lexical_duplicate, lexical_other]),
        ), patch(
            "features.assistant.tools.archive_store.get_by_ids",
            new=AsyncMock(return_value=[semantic_item]),
        ) as get_by_ids, patch(
            "features.assistant.tools.archive_semantic.query",
            new=AsyncMock(return_value=[SemanticMatch(archive_id=2, score=0.82)]),
        ), patch(
            "features.assistant.tools.archive_semantic.upsert_item",
            new=AsyncMock(return_value=True),
        ), patch.object(
            __import__(
                "features.assistant.tools",
                fromlist=["archive_semantic"],
            ).archive_semantic,
            "configured",
            True,
        ), patch.object(
            __import__(
                "features.assistant.tools",
                fromlist=["archive_semantic"],
            ).archive_semantic,
            "_blocked_reason",
            "",
        ):
            result = await registry.execute(decision, message)
            await asyncio.sleep(0)

        self.assertTrue(result.handled)
        get_by_ids.assert_awaited_once_with(99, [2])
        body = message.reply.await_args.args[0]
        self.assertLess(body.index("**#2**"), body.index("**#1**"))
        self.assertEqual(body.count("**#2**"), 1)

    async def test_semantic_empty_result_keeps_lexical_search(self):
        registry = CommandToolRegistry(SimpleNamespace())
        sent = SimpleNamespace(id=901)
        message = SimpleNamespace(
            author=SimpleNamespace(id=99),
            reply=AsyncMock(return_value=sent),
        )
        decision = RouteDecision(
            intent="archive_search",
            tool="archive.search",
            arguments={"query": "meme"},
        )
        lexical = {
            "id": 7,
            "source_content": "meme mèo",
            "source_author_name": "Khai",
            "source_jump_url": "",
            "source_url": "",
        }

        semantic = __import__(
            "features.assistant.tools",
            fromlist=["archive_semantic"],
        ).archive_semantic
        with patch(
            "features.assistant.tools.archive_store.search",
            new=AsyncMock(return_value=[lexical]),
        ), patch(
            "features.assistant.tools.archive_semantic.query",
            new=AsyncMock(return_value=[]),
        ), patch(
            "features.assistant.tools.archive_semantic.upsert_item",
            new=AsyncMock(return_value=True),
        ), patch.object(semantic, "configured", True), patch.object(
            semantic, "_blocked_reason", ""
        ):
            result = await registry.execute(decision, message)
            await asyncio.sleep(0)

        self.assertTrue(result.handled)
        self.assertIn("**#7**", message.reply.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
