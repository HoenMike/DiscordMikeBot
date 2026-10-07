import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.archive import ArchiveStore
from features.assistant.cog import choose_conversation_route
from features.assistant.router import route_locally
from features.assistant.tools import CommandToolRegistry


def fake_message(
    content="@Asumi nhớ cái này",
    *,
    author_id=30,
    reply_id=None,
    resolved=None,
    attachments=None,
):
    reference = None
    if reply_id is not None:
        reference = SimpleNamespace(message_id=reply_id, resolved=resolved)
    return SimpleNamespace(
        id=100,
        content=content,
        author=SimpleNamespace(id=author_id, display_name=f"User{author_id}"),
        guild=SimpleNamespace(id=10),
        channel=SimpleNamespace(id=20),
        reference=reference,
        attachments=list(attachments or []),
    )


class ArchiveRouterTests(unittest.IsolatedAsyncioTestCase):
    def test_save_routes_deterministically(self):
        decision = route_locally("nhớ cái này")
        self.assertEqual(decision.intent, "archive_save")
        self.assertEqual(decision.tool, "archive.save")

    def test_search_routes_deterministically(self):
        decision = route_locally("tìm lại meme mèo Khai")
        self.assertEqual(decision.intent, "archive_search")
        self.assertEqual(decision.tool, "archive.search")
        self.assertIn("meme", decision.arguments["query"])

    def test_save_url_does_not_become_note(self):
        decision = route_locally("nhớ link này https://example.com/cat")
        self.assertEqual(decision.tool, "archive.save")
        self.assertEqual(decision.arguments["note"], "")

    def test_explicit_note_is_parsed(self):
        decision = route_locally("nhớ cái này ghi chú: meme hay")
        self.assertEqual(decision.tool, "archive.save")
        self.assertEqual(decision.arguments["note"], "meme hay")

    def test_kiem_lai_synonym_cleans_query(self):
        decision = route_locally("kiếm lại meme mèo Khai")
        self.assertEqual(decision.tool, "archive.search")
        self.assertEqual(decision.arguments["query"], "meme meo khai")

    def test_forget_requires_explicit_archive_id(self):
        decision = route_locally("quên #42")
        self.assertEqual(decision.intent, "archive_forget")
        self.assertEqual(decision.tool, "archive.forget")
        self.assertEqual(decision.arguments["archive_id"], 42)

    async def test_archive_action_beats_live_session_followup(self):
        previous = SimpleNamespace(intent="chat")
        decision = await choose_conversation_route(
            "nhớ cái này",
            previous_session=previous,
            is_live_continuation=True,
            has_images=False,
            cloudflare_router=None,
            min_confidence=0.55,
        )
        self.assertEqual(decision.tool, "archive.save")


class ArchiveStoreGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_bare_save_never_archives_nearby_chat(self):
        store = ArchiveStore()
        store.ensure_schema = AsyncMock()
        item, error, created = await store.save(
            30,
            fake_message("nhớ cái này"),
        )
        self.assertIsNone(item)
        self.assertFalse(created)
        self.assertIn("Reply", error)

    async def test_forget_scopes_delete_to_owner(self):
        store = ArchiveStore()
        store.ensure_schema = AsyncMock()
        fake_cursor = SimpleNamespace(rowcount=1)

        with patch(
            "features.assistant.archive.db_client.execute",
            new=AsyncMock(return_value=fake_cursor),
        ) as execute, patch(
            "features.assistant.archive.db_client.commit",
            new=AsyncMock(),
        ):
            deleted = await store.forget(30, 42)

        self.assertTrue(deleted)
        sql, params = execute.await_args.args
        self.assertIn("owner_user_id", sql)
        self.assertEqual(params, (42, 30))

    def test_search_scoring_matches_author_note_and_content(self):
        item = {
            "source_content": "meme mèo đang ngủ",
            "source_author_name": "Khai",
            "note": "meme vui",
            "source_url": "https://example.com/cat",
            "metadata": {},
        }
        self.assertGreater(ArchiveStore._score(item, "meme mèo Khai"), 0)
        self.assertEqual(ArchiveStore._score(item, "Valorant Guardian"), 0)


class ArchiveToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_tool_uses_requesting_user_as_owner(self):
        sent = SimpleNamespace(id=501)
        message = fake_message(author_id=30)
        message.reply = AsyncMock(return_value=sent)
        registry = CommandToolRegistry(SimpleNamespace())
        decision = route_locally("nhớ cái này")

        saved = {
            "id": 12,
            "source_content": "meme mèo",
            "source_jump_url": "https://discord.com/channels/10/20/77",
            "source_url": "",
            "source_author_name": "Khai",
        }

        with patch(
            "features.assistant.tools.archive_store.save",
            new=AsyncMock(return_value=(saved, "", True)),
        ) as save:
            result = await registry.execute(decision, message)

        self.assertTrue(result.handled)
        self.assertEqual(result.response_message_ids, (501,))
        self.assertEqual(save.await_args.args[0], 30)

    async def test_search_result_does_not_reping_everyone(self):
        sent = SimpleNamespace(id=502)
        message = fake_message("@Asumi tìm lại meme", author_id=30)
        message.reply = AsyncMock(return_value=sent)
        registry = CommandToolRegistry(SimpleNamespace())
        decision = route_locally("tìm lại meme")

        item = {
            "id": 8,
            "source_content": "@everyone xem meme này",
            "source_jump_url": "",
            "source_url": "",
            "source_author_name": "Khai",
        }

        with patch(
            "features.assistant.tools.archive_store.search",
            new=AsyncMock(return_value=[item]),
        ):
            result = await registry.execute(decision, message)

        self.assertTrue(result.handled)
        body = message.reply.await_args.args[0]
        self.assertNotIn("@everyone", body)
        self.assertIn("@\u200beveryone", body)


if __name__ == "__main__":
    unittest.main()
