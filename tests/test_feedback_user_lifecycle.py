"""T23 reporter lifecycle: privacy, soft-deletion and atomic revision."""
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from features.feedback.store import (
    FeedbackStore, FeedbackStorageError, SCHEMA, LIFECYCLE_TRIGGERS,
)


class Query:
    def __init__(self, client, sql, args):
        self.client,self.sql,self.args=client,sql,args
        self.cur=None
    def __await__(self):
        async def task():
            self.cur=self.client.conn.execute(self.sql,self.args)
            return self
        return task().__await__()
    async def __aenter__(self):
        await self
        return self
    async def __aexit__(self,*args): pass
    async def fetchone(self): return self.cur.fetchone()
    async def fetchall(self): return self.cur.fetchall()
    @property
    def rowcount(self): return self.cur.rowcount


class MemoryCloud:
    is_cloud=True
    def __init__(self): self.conn=sqlite3.connect(":memory:")
    async def connect(self): pass
    def execute(self,sql,args=()): return Query(self,sql,args)


class ReporterLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db=MemoryCloud()
        self.store=FeedbackStore()
    def tearDown(self): self.db.conn.close()

    async def create(self, reporter=101,guild=15,source=500,evidence=None):
        return await self.store.create(
            guild_id=guild,channel_id=22,reporter_id=reporter,
            source_message_id=source, bot_version="3.8.4",category="bug",
            title="Tóm tắt theo người bị lỗi",description="Tóm tắt theo người bị lỗi",
            explanation="Cần lọc tác giả",design_rule="summary",
            reply_to_message_id=None,reported_bot_message_id=None,
            evidence=evidence or [],
        )

    async def test_upgrade_existing_383_table_does_not_lose_ticket(self):
        # Create legacy table with no lifecycle fields, then run migrations.
        for sql in SCHEMA:
            if "CREATE TABLE IF NOT EXISTS asumi_feedback (" in sql:
                for column in ("replaces_ticket_id TEXT,", "replaced_by_ticket_id TEXT,", "deleted_at TEXT,"):
                    sql=sql.replace("      "+column+"\n","")
            self.db.conn.execute(sql)
        self.db.conn.execute(
            "INSERT INTO asumi_feedback(ticket_id,source_message_id,guild_id,"
            "channel_id,reporter_id,bot_version,category,title,description,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("FB-OLD","100","15","22","101","3.8.3","bug","Original","Original",
             "2026-10-08T04:00:00Z","2026-10-08T04:00:00Z"),
        )
        with patch("features.feedback.store.db_client",self.db):
            self.assertTrue(await self.store.init())
            self.assertTrue(await self.store.init())
            record=await self.store.admin_detail("FB-OLD")
            self.assertEqual(record["display_id"],"#1")
            self.assertEqual(record["status"],"submitted")
            columns=[r[1] for r in self.db.conn.execute("PRAGMA table_info(asumi_feedback)")]
            self.assertIn("replaces_ticket_id",columns)
            self.assertIn("deleted_at",columns)

    async def test_replacement_is_atomic_and_marks_original_deleted(self):
        evidence=[{
            "key":"feedback/15/test.png","media_type":"image/png",
            "sha256":"deadbeef","bytes":13,
        }]
        with patch("features.feedback.store.db_client",self.db):
            self.assertTrue(await self.store.init())
            first=await self.create(evidence=evidence)
            revised=await self.store.replace_own(
                ticket_id="#1",reporter_id=101,guild_id=15,
                source_message_id=900,bot_version="3.8.4",
                description="Tóm tắt 12 giờ theo @user trả cả channel",
                explanation="Phải chỉ lấy tin người được tag",
            )
            self.assertEqual(revised.number,2)
            old=await self.store.admin_detail("#1")
            fresh=await self.store.admin_detail("#2")
            self.assertEqual(old["status"],"deleted")
            self.assertEqual(old["replaced_by_ticket_id"],revised.id)
            self.assertEqual(old["replacement_number"],2)
            self.assertEqual(fresh["replaces_ticket_id"],first.id)
            self.assertEqual(fresh["evidence"],evidence)
            self.assertEqual(old["evidence"],evidence)
            self.assertEqual(fresh["status"],"submitted")
            self.assertIsNotNone(old["deleted_at"])
            rows=self.db.conn.execute(
                "SELECT old_status,new_status,actor_id FROM asumi_feedback_events "
                "WHERE ticket_id=? ORDER BY event_id",(first.id,)
            ).fetchall()
            self.assertEqual(rows[-1],("submitted","deleted","101"))
            self.assertEqual(
                [t["number"] for t in await self.store.own_list(reporter_id=101,guild_id=15)],
                [2],
            )
            self.assertEqual(
                [t["number"] for t in await self.store.own_list(
                    reporter_id=101,guild_id=15,include_deleted=True)],
                [2,1],
            )

    async def test_reporter_revision_dismisses_stale_ai_proposal(self):
        with patch("features.feedback.store.db_client",self.db):
            await self.store.init()
            first=await self.create()
            proposal_id=await self.store.propose_review(
                ticket_id="#1",target_status="approved",
                reason="Confirmed defect in summary routing with tag.",
            )
            before=await self.store.list_proposals(ticket_id="#1")
            self.assertEqual(before[0]["state"],"pending")
            await self.store.replace_own(
                ticket_id="#1",reporter_id=101,guild_id=15,
                source_message_id=901,bot_version="3.8.4",
                description="Tôi đã sửa mô tả, hãy xem phiên bản mới",
            )
            after=await self.store.list_proposals(ticket_id="#1")
            self.assertEqual(after[0]["state"],"dismissed")
            self.assertEqual(after[0]["reviewer_id"],"101")
            self.assertEqual((await self.store.admin_detail("#2"))["status"],"submitted")

    async def test_deleted_ticket_does_not_allow_replacement_or_admin_review(self):
        with patch("features.feedback.store.db_client",self.db):
            await self.store.init()
            await self.create()
            await self.store.soft_delete_own(ticket_id="#1",reporter_id=101,guild_id=15)
            with self.assertRaises(FeedbackStorageError):
                await self.store.replace_own(
                    ticket_id="#1",reporter_id=101,guild_id=15,
                    source_message_id=901,bot_version="3.8.4",
                    description="Tôi muốn sửa report đã xóa này",
                )
            with self.assertRaises(FeedbackStorageError):
                await self.store.review(ticket_id="#1",status="approved",
                                        reason="Should be impossible",actor_id="admin")
            self.assertEqual((await self.store.admin_detail("#1"))["status"],"deleted")
            self.assertEqual(
                self.db.conn.execute("SELECT count(*) FROM asumi_feedback").fetchone()[0],1
            )

    async def test_only_reporter_same_guild_can_revise_or_delete(self):
        with patch("features.feedback.store.db_client",self.db):
            await self.store.init()
            first=await self.create()
            for uid,gid in [(999,15),(101,99)]:
                with self.subTest(uid=uid,gid=gid), self.assertRaises(FeedbackStorageError):
                    await self.store.soft_delete_own(
                        ticket_id=first.id,reporter_id=uid,guild_id=gid,
                    )
                with self.assertRaises(FeedbackStorageError):
                    await self.store.replace_own(
                        ticket_id=first.id,reporter_id=uid,guild_id=gid,
                        source_message_id=900+uid,bot_version="3.8.4",
                        description="An attempt to edit someone else's feedback",
                    )
            self.assertEqual((await self.store.admin_detail("#1"))["status"],"submitted")
            self.assertEqual(len(await self.store.own_list(reporter_id=999,guild_id=15)),0)
            self.assertEqual(len(await self.store.own_list(reporter_id=101,guild_id=99)),0)

    async def test_cannot_mark_fixed_before_deployment_and_version(self):
        with patch("features.feedback.store.db_client",self.db):
            await self.store.init()
            await self.create()
            await self.store.review(
                ticket_id="#1",status="approved",
                reason="Accepted",actor_id="owner",
            )
            with self.assertRaises(FeedbackStorageError):
                await self.store.review(
                    ticket_id="#1",status="verified",
                    reason="Fixed",actor_id="owner",verified_version="3.8.4",
                )
            self.assertEqual((await self.store.admin_detail("#1"))["status"],"approved")
            await self.store.review(
                ticket_id="#1",status="deployed",
                reason="CI and Render deployment completed",actor_id="owner",
            )
            await self.store.review(
                ticket_id="#1",status="verified",
                reason="Reporter confirmed the defect was fixed",actor_id="owner",
                verified_version="3.8.4",
            )
            self.assertEqual((await self.store.admin_detail("#1"))["status"],"verified")

    async def test_editing_approved_report_creates_fresh_submission_and_preserves_audit(self):
        with patch("features.feedback.store.db_client",self.db):
            await self.store.init()
            first=await self.create()
            await self.store.review(ticket_id="#1",status="approved",
                                    reason="Owner approved",actor_id="owner")
            fresh=await self.store.replace_own(
                ticket_id="#1",reporter_id=101,guild_id=15,
                source_message_id=901,bot_version="3.8.4",
                description="Tôi bổ sung lại báo cáo đã được duyệt, cần sửa khác",
            )
            self.assertEqual(fresh.number,2)
            self.assertEqual((await self.store.admin_detail("#2"))["status"],"submitted")
            self.assertEqual((await self.store.admin_detail("#1"))["status"],"deleted")
            events=self.db.conn.execute(
                "SELECT old_status,new_status,reason FROM asumi_feedback_events "
                "WHERE ticket_id=? ORDER BY event_id",(first.id,)
            ).fetchall()
            self.assertTrue(any(row[1]=="approved" and row[2]=="Owner approved" for row in events))
            self.assertEqual(events[-1][0:2],("approved","deleted"))

    def test_admin_ui_does_not_inject_untrusted_ticket_html(self):
        from pathlib import Path
        html=(Path(__file__).resolve().parents[1]/"web/templates/feedback.html").read_text("utf-8")
        self.assertNotIn("innerHTML",html)
        self.assertIn("Feedback Center",html)
        self.assertIn("Lịch sử và dấu vết xử lý",html)
        self.assertIn("Xác nhận đổi ticket",html)

    async def test_discord_user_views_construct_with_real_discord_ui(self):
        from features.feedback.user_views import (
            MyFeedbackView, TicketDetailView, DeleteConfirmView, ReviseModal,
        )
        example = {
            "id": "FB-OLD", "number": 1, "title": "Báo lỗi tóm tắt",
            "description": "Bot đã lấy tin nhắn cả channel",
            "status": "submitted", "category": "bug",
            "reason": "", "explanation": "",
            "replacement_number": None,
        }
        view = MyFeedbackView(
            owner_id=101, guild_id=15, tickets=[example],
            offset=0, include_deleted=False,
        )
        self.assertTrue(any(child.__class__.__name__=="TicketSelection" for child in view.children))
        self.assertTrue(view.prev_page.disabled)
        detail = TicketDetailView(owner_id=101,guild_id=15,ticket=example)
        self.assertFalse(detail.revise.disabled)
        self.assertFalse(detail.delete.disabled)
        self.assertIn("#1", detail.embed().title)
        modal = ReviseModal(detail)
        self.assertEqual(modal.description.default, example["description"])
        confirmation = DeleteConfirmView(owner_id=101,guild_id=15,ticket=example)
        self.assertIn("#1",confirmation.embed().title)

    def test_user_interface_is_ephemeral_and_owner_gated(self):
        from pathlib import Path
        text=(Path(__file__).resolve().parents[1]/"features/feedback/user_views.py").read_text("utf-8")
        cog=(Path(__file__).resolve().parents[1]/"features/feedback/cog.py").read_text("utf-8")
        self.assertIn("interaction.user.id != self.owner_id",text)
        self.assertIn("discord.ui.Modal",text)
        self.assertIn("replace_own(",text)
        self.assertIn("soft_delete_own(",text)
        self.assertIn('name="mine"',cog)
        self.assertIn("ephemeral=True",cog)


if __name__=="__main__":
    unittest.main()
