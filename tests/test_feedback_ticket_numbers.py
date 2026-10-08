"""T23 numbering contract: permanent #N IDs, chronological migration, no reruns."""
import sqlite3
import unittest
from unittest.mock import patch

from features.feedback.store import SCHEMA, FeedbackStore


class Q:
    def __init__(self,db,sql,args):
        self.db, self.sql, self.args = db,sql,args
        self.cur = None
    def __await__(self):
        async def exec_it():
            self.cur=self.db.conn.execute(self.sql,self.args)
            return self
        return exec_it().__await__()
    async def __aenter__(self):
        await self
        return self
    async def __aexit__(self,*_): pass
    @property
    def rowcount(self): return self.cur.rowcount
    async def fetchone(self): return self.cur.fetchone()
    async def fetchall(self): return self.cur.fetchall()


class MemoryCloud:
    is_cloud=True
    def __init__(self):
        self.conn=sqlite3.connect(":memory:")
    async def connect(self): pass
    def execute(self,sql,args=()): return Q(self,sql,args)


class TicketSequenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db=MemoryCloud()
        self.store=FeedbackStore()
    def tearDown(self):
        self.db.conn.close()

    async def create(self,guild=1,source=1,description="a bug"):
        return await self.store.create(
            guild_id=guild,channel_id=2,reporter_id=3,
            source_message_id=source,bot_version="3.8.3",category="bug",
            title=description,description=description,explanation="",
            design_rule="unknown",reply_to_message_id=None,
            reported_bot_message_id=None,evidence=[]
        )

    async def test_backfill_old_tickets_chronologically_without_changing_ids(self):
        for sql in SCHEMA:
            self.db.conn.execute(sql)
        # Insert old tickets *before the new mapping trigger is installed*:
        # realistic upgrade of an existing 3.8.2 DB.
        self.db.conn.execute("DROP TRIGGER feedback_allocate_number")
        for ident,created in (
            ("FB-LATER","2026-10-08T05:50:00"),
            ("FB-01401CE0D1","2026-10-08T05:33:39"),
        ):
            self.db.conn.execute(
                "INSERT INTO asumi_feedback(ticket_id,source_message_id,guild_id,"
                "channel_id,reporter_id,bot_version,category,title,description,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ident,ident,"1","2","3","3.8.0","bug","title","desc",created,created),
            )
        with patch("features.feedback.store.db_client",self.db):
            self.assertTrue(await self.store.init())
            self.assertEqual((await self.store.admin_detail("FB-01401CE0D1"))["number"],1)
            self.assertEqual((await self.store.admin_detail("#2"))["id"],"FB-LATER")
            self.assertEqual((await self.store.admin_detail("1"))["id"],"FB-01401CE0D1")
            self.assertTrue(await self.store.init())
            nums=self.db.conn.execute(
                "SELECT number,ticket_id FROM asumi_feedback_numbers ORDER BY number"
            ).fetchall()
            self.assertEqual(nums,[(1,"FB-01401CE0D1"),(2,"FB-LATER")])
            newer=await self.create(source=555)
            self.assertEqual(newer.number,3)
            self.assertTrue(await self.store.init())
            self.assertEqual((await self.store.own_ticket("#1",reporter_id=3)).label,"#1")
            self.assertEqual((await self.store.own_ticket("#3",reporter_id=999)),None)

    async def test_new_tickets_get_strictly_increasing_numbers_and_idempotency(self):
        with patch("features.feedback.store.db_client",self.db):
            self.assertTrue(await self.store.init())
            one=await self.create(source=100)
            again=await self.create(source=100)
            two=await self.create(source=101)
            self.assertEqual(one.number,1)
            self.assertEqual(again.id,one.id)
            self.assertEqual(again.number,1)
            self.assertEqual(two.number,2)
            self.assertEqual([t["number"] for t in await self.store.admin_list()], [2,1])
            self.assertEqual((await self.store.admin_detail("#1"))["display_id"],"#1")
            self.assertEqual((await self.store.admin_detail(one.id))["number"],1)

    async def test_moderation_by_number_and_notification_contains_same_number(self):
        with patch("features.feedback.store.db_client",self.db):
            self.assertTrue(await self.store.init())
            ticket=await self.create(source=7)
            await self.store.review(ticket_id="#1",status="rejected",
                                    reason="Current command behaviour was expected",
                                    actor_id="owner-dashboard")
            updated=await self.store.own_ticket("1",reporter_id=3)
            self.assertEqual(updated.status,"rejected")
            self.assertEqual(updated.number,1)
            notifications=await self.store.pending_notifications()
            self.assertEqual(len(notifications),1)
            self.assertEqual(notifications[0][6],1)
            self.assertEqual(notifications[0][4],"Current command behaviour was expected")

    async def test_invalid_or_missing_public_numbers_never_target_another_ticket(self):
        with patch("features.feedback.store.db_client",self.db):
            await self.store.init()
            one=await self.create(source=8)
            self.assertIsNone(await self.store.admin_detail("#999"))
            self.assertIsNone(await self.store.admin_detail("0"))
            self.assertIsNone(await self.store.admin_detail("#wrong"))
            self.assertEqual((await self.store.admin_detail(one.id))["number"],1)


if __name__=="__main__":
    unittest.main()
