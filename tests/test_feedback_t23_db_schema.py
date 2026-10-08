"""Smoke real SQLite trigger semantics before releasing Turso feedback."""
import sqlite3
import unittest
from features.feedback.store import SCHEMA


class FeedbackSchemaTests(unittest.TestCase):
    def test_acceptance_and_review_events_are_durable(self):
        db=sqlite3.connect(":memory:")
        for sql in SCHEMA: db.execute(sql)
        db.execute(
            "INSERT INTO asumi_feedback (ticket_id,source_message_id,guild_id,"
            "channel_id,reporter_id,bot_version,category,title,description,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("FB-TEST","100","1","2","3","3.7.8","bug","Title","Body","2026-10-08T04:00:00Z","2026-10-08T04:00:00Z"),
        )
        first=db.execute("SELECT action FROM asumi_feedback_events").fetchall()
        self.assertEqual(first,[("submit",)])
        self.assertEqual(db.execute("SELECT count(*) FROM asumi_feedback_notifications").fetchone()[0],0)
        db.execute(
            "UPDATE asumi_feedback SET status='rejected',review_reason='Documented intended behavior',"
            "updated_at='2026-10-08T04:01:00Z' WHERE ticket_id='FB-TEST'"
        )
        self.assertEqual(
            db.execute("SELECT event_type FROM asumi_feedback_notifications").fetchall(),
            [("rejected",)],
        )
        self.assertEqual(
            db.execute("SELECT old_status,new_status,reason FROM asumi_feedback_events ORDER BY event_id DESC LIMIT 1").fetchone(),
            ("submitted","rejected","Documented intended behavior"),
        )
        db.execute("UPDATE asumi_feedback SET review_reason='updated' WHERE ticket_id='FB-TEST'")
        self.assertEqual(db.execute("SELECT count(*) FROM asumi_feedback_notifications").fetchone()[0],1)


if __name__=="__main__":
    unittest.main()
