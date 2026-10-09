"""T23.1 regression: explicit feedback, override, private images and cloud-only tickets."""
import io
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
from features.feedback.policy import detect_feedback, clarification_text
from features.feedback.evidence import EvidenceError, PrivateEvidenceStore, _clean_image
from features.feedback.store import FeedbackStore, FeedbackStorageError
from features.feedback.cog import FeedbackCog, FeedbackDraft


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (40, 25), "white").save(buffer, "PNG")
    return buffer.getvalue()


class PolicyTests(unittest.TestCase):
    def test_real_bug_intents(self):
        self.assertEqual(detect_feedback("báo lỗi tóm tắt @người không đúng").category, "bug")
        self.assertEqual(detect_feedback("góp ý: thêm chức năng lọc").category, "feature")
        self.assertIsNotNone(detect_feedback("kết quả sai", replying_to_bot=True))
        self.assertIsNone(detect_feedback("kết quả sai"))
        self.assertIsNone(detect_feedback("Asumi ngu quá"))
        self.assertIsNone(detect_feedback("tóm tắt 1h qua"))

    def test_current_design_hint_never_rejects(self):
        normal, rule = clarification_text("báo lỗi /tomtat tóm tắt cả nhóm", "3.7.8")
        self.assertIn("cả channel", normal)
        self.assertEqual(rule, "summary-channel-default")
        targeted, rule2 = clarification_text(
            "báo lỗi @Asumi tóm tắt tin nhắn 12h qua của <@123456789012345678>",
            "3.7.8",
        )
        self.assertEqual(rule2, "summary-author-scoped")
        self.assertIn("lọc đúng tác giả", targeted)
        unknown, rule3 = clarification_text("báo lỗi UI không hiện", "3.7.8")
        self.assertIn("vẫn có thể gửi", unknown)
        self.assertEqual(rule3, "unknown")


class PrivateImageTests(unittest.IsolatedAsyncioTestCase):
    def test_actual_signature_not_extension(self):
        with self.assertRaises(EvidenceError):
            _clean_image(b"not a PNG")
        clean, mime = _clean_image(png())
        self.assertTrue(clean.startswith(b"\x89PNG"))
        self.assertEqual(mime, "image/png")

    async def test_private_r2_upload_and_checksum(self):
        s3 = MagicMock()
        with patch.dict("os.environ", {"ASUMI_FEEDBACK_R2_BUCKET": "private-evidence"}, clear=False):
            store = PrivateEvidenceStore(client=s3)
            attachment = SimpleNamespace(size=len(png()), content_type="image/png",
                                         read=AsyncMock(return_value=png()))
            uploaded = await store.put_attachment(
                attachment, guild_id=100, source_message_id=200,
            )
            self.assertTrue(uploaded.key.startswith("feedback/100/"))
            self.assertEqual(uploaded.source_message_id, 200)
            kwargs = s3.put_object.call_args.kwargs
            self.assertEqual(kwargs["Bucket"], "private-evidence")
            self.assertEqual(kwargs["ContentType"], "image/png")
            self.assertNotIn("ACL", kwargs)
            await store.delete(uploaded.key)
            s3.delete_object.assert_called_once()

    async def test_disguised_non_image_refused_before_upload(self):
        s3 = MagicMock()
        with patch.dict("os.environ", {"ASUMI_FEEDBACK_R2_BUCKET": "private"}, clear=False):
            store = PrivateEvidenceStore(client=s3)
            a = SimpleNamespace(size=120, content_type="image/png", read=AsyncMock(return_value=b"bad"))
            with self.assertRaises(EvidenceError):
                await store.put_attachment(a, guild_id=1, source_message_id=2)
            s3.put_object.assert_not_called()


class FakeCursor:
    def __init__(self, row):
        self.row = row
    async def fetchone(self):
        return self.row


class FakeQuery:
    def __init__(self, db, sql, args):
        self.db, self.sql, self.args = db, sql, args
    def __await__(self):
        async def operation():
            self.db.apply(self.sql, self.args)
            return FakeCursor(None)
        return operation().__await__()
    async def __aenter__(self):
        return FakeCursor(self.db.lookup(self.sql, self.args))
    async def __aexit__(self, *_):
        pass


class FakeCloud:
    is_cloud = True
    def __init__(self):
        self.rows = {}
    async def connect(self): pass
    def execute(self, sql, args=()):
        return FakeQuery(self, sql, args)
    def apply(self, sql, args):
        if "INSERT INTO asumi_feedback (" in sql:
            ticket_id, source_id, guild_id, _, reporter_id = args[:5]
            key = (guild_id, source_id)
            self.rows.setdefault(key, (ticket_id, "submitted", args[9], args[8], args[14], ""))
    def lookup(self, sql, args):
        if "WHERE guild_id=?" in sql or "WHERE f.guild_id=?" in sql:
            return self.rows.get((args[0], args[1]))
        return None


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_ephemeral_sqlite_write(self):
        fake = FakeCloud()
        fake.is_cloud = False
        with patch("features.feedback.store.db_client", fake):
            with self.assertRaises(FeedbackStorageError):
                await FeedbackStore().create(
                    guild_id=1, channel_id=2, reporter_id=3,
                    source_message_id=4, bot_version="3.7", category="bug",
                    title="bug", description="broken", explanation="",
                    design_rule="unknown", reply_to_message_id=None,
                    reported_bot_message_id=None, evidence=[],
                )
            self.assertFalse(fake.rows)

    async def test_cloud_insert_idempotency(self):
        fake = FakeCloud()
        kwargs = dict(
            guild_id=1, channel_id=2, reporter_id=3,
            source_message_id=4, bot_version="3.7", category="bug",
            title="bug", description="broken", explanation="",
            design_rule="unknown", reply_to_message_id=None,
            reported_bot_message_id=None, evidence=[{"key": "feedback/1/test.png"}],
        )
        with patch("features.feedback.store.db_client", fake):
            first = await FeedbackStore().create(**kwargs)
            second = await FeedbackStore().create(**kwargs)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(fake.rows), 1)


class DiscordWizardTests(unittest.IsolatedAsyncioTestCase):
    def bot(self):
        return SimpleNamespace(user=SimpleNamespace(id=999), get_cog=MagicMock())

    async def test_explicit_mention_creates_draft_not_ticket(self):
        bot = self.bot()
        cog = FeedbackCog(bot)
        msg = SimpleNamespace(
            guild=SimpleNamespace(id=5), channel=SimpleNamespace(id=10),
            author=SimpleNamespace(id=20), id=30,
            content="<@999> báo lỗi: tóm tắt sai tác giả",
            reference=None, attachments=[], reply=AsyncMock(return_value=SimpleNamespace(id=31)),
        )
        with patch("features.feedback.cog.feedback_store.create", new=AsyncMock()) as create:
            handled = await cog.handle_message(msg)
        self.assertTrue(handled)
        self.assertEqual(cog._active(5, 20).source_message_id, 30)
        create.assert_not_awaited()

    async def test_new_report_offers_replace_keep_cancel_instead_of_deadlock(self):
        cog = FeedbackCog(self.bot())
        def make_message(mid, text):
            return SimpleNamespace(
                guild=SimpleNamespace(id=5), channel=SimpleNamespace(id=10),
                author=SimpleNamespace(id=20), id=mid, content=text,
                reference=None, attachments=[],
                reply=AsyncMock(return_value=SimpleNamespace(id=mid + 100)),
            )
        first = make_message(30, "báo lỗi: không lấy được history")
        second = make_message(40, "feedback lỗi tìm CKTG")
        await cog.start_from_message(first, detect_feedback(first.content))
        old = cog._active(5, 20)
        old_view = first.reply.await_args.kwargs["view"]

        await cog.start_from_message(second, detect_feedback(second.content))
        self.assertIs(cog._active(5, 20), old)
        conflict = second.reply.await_args.kwargs["view"]
        self.assertEqual(
            {button.label for button in conflict.children},
            {"Dùng báo cáo mới", "Giữ bản cũ", "Hủy bản cũ"},
        )
        response = SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock())
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=20), response=response,
        )
        await next(button for button in conflict.children
                   if button.label == "Dùng báo cáo mới").callback(interaction)
        self.assertIs(cog._active(5, 20), conflict.incoming)
        self.assertEqual(cog._active(5, 20).source_message_id, 40)
        self.assertFalse(await old_view.interaction_check(interaction))
        response.send_message.assert_awaited_once()

        third = make_message(50, "báo lỗi phần feedback")
        await cog.start_from_message(third, detect_feedback(third.content))
        cancel = third.reply.await_args.kwargs["view"]
        await next(button for button in cancel.children
                   if button.label == "Hủy bản cũ").callback(interaction)
        self.assertIsNone(cog._active(5, 20))

    async def test_followup_images_are_collected_not_submitted(self):
        bot = self.bot()
        cog = FeedbackCog(bot)
        draft = FeedbackDraft(20,5,10,30,"bug","báo lỗi")
        draft.prompt_message_id = 31
        cog.drafts[(5,20)] = draft
        item = SimpleNamespace(size=100, content_type="image/png", url="https://cdn.discordapp.com/x.png")
        msg = SimpleNamespace(
            guild=SimpleNamespace(id=5), channel=SimpleNamespace(id=10),
            author=SimpleNamespace(id=20), id=33,
            content="đây là ảnh", attachments=[item],
            reference=SimpleNamespace(message_id=31),
            reply=AsyncMock(return_value=SimpleNamespace(id=34)),
        )
        self.assertTrue(await cog.handle_message(msg))
        self.assertEqual(len(draft.attachments), 1)

    async def test_r2_partial_failure_cleans_previous_files(self):
        cog=FeedbackCog(self.bot())
        draft=FeedbackDraft(20,5,10,30,"bug","báo lỗi")
        draft.attachments=[(SimpleNamespace(),30),(SimpleNamespace(),31)]
        cog.drafts[(5,20)]=draft
        successful=SimpleNamespace(key="feedback/5/first.png", media_type="image/png",
                                   bytes_count=1, sha256="s",source_message_id=30)
        with patch("features.feedback.cog.feedback_store._require_cloud", new=AsyncMock()), patch(
            "features.feedback.cog.feedback_store.init", new=AsyncMock(return_value=True)
        ), patch("features.feedback.cog.feedback_store.find_source", new=AsyncMock(return_value=None)
        ), patch("features.feedback.cog.evidence_store.put_attachment", new=AsyncMock(
            side_effect=[successful, EvidenceError("bad second")]
        )), patch("features.feedback.cog.evidence_store.delete", new=AsyncMock()) as delete:
            with self.assertRaises(EvidenceError):
                await cog.submit_draft(draft)
            delete.assert_awaited_once_with("feedback/5/first.png")

if __name__ == "__main__":
    unittest.main()
