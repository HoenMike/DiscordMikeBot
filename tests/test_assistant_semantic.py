import unittest
from unittest.mock import AsyncMock, patch

from features.assistant.providers.vectorize import (
    ArchiveSemanticIndex,
    SemanticMatch,
)


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

        raw = index._json_request.await_args.kwargs["data"].decode("utf-8")
        self.assertIn('"id": "12"', raw)
        self.assertIn('"namespace": "u99"', raw)

    async def test_permission_failure_circuit_breaks_semantic_mode(self):
        index = self.make_index()
        index._index_ready = False
        index._json_request = AsyncMock(
            side_effect=__import__(
                "features.assistant.providers.vectorize",
                fromlist=["SemanticUnavailable"],
            ).SemanticUnavailable("permission")
        )

        matches = await index.query(99, "anything")

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
