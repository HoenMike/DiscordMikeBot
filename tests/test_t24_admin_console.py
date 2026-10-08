"""T24 Admin Console — routes, CSRF, navigation and paginated inbox."""
import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from features.feedback.store import FeedbackStore


ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return None
    async def fetchall(self): return []


class _FakeDB:
    is_cloud = True
    def __init__(self): self.query = ""; self.args = ()
    async def connect(self): return None
    def execute(self, query, args=()):
        self.query, self.args = query, args
        return _Cursor()


class TicketSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_queue_filter_search_and_bounded_page(self):
        db = _FakeDB()
        with patch("features.feedback.store.db_client", db):
            self.assertEqual(await FeedbackStore().admin_list(
                view="pending", query="#15", limit=200, offset=21), [])
        self.assertIn("f.status IN", db.query)
        self.assertIn("CAST(n.number AS TEXT) LIKE ?", db.query)
        self.assertIn("LIMIT 100 OFFSET 21", db.query)
        self.assertEqual(db.args[-3:], ("%15%", "%15%", "%15%"))
        self.assertIn("submitted", db.args)

    async def test_query_is_never_sql_interpolated(self):
        db = _FakeDB()
        malicious = "' OR 1=1 --"
        with patch("features.feedback.store.db_client", db):
            await FeedbackStore().admin_list(query=malicious, limit=5, offset=-12)
        self.assertNotIn(malicious, db.query)
        self.assertIn("%"+malicious+"%", db.args)
        self.assertIn("OFFSET 0", db.query)


class ConsoleSourceTests(unittest.TestCase):
    def test_shared_shell_and_feedback_navigation(self):
        nav = (ROOT / "web/templates/partials/admin_nav.html").read_text("utf-8")
        for route in ("/admin/feedback", "/admin/activity", "/admin/monitoring",
                      "/admin/assistant", "/admin/tarot", "/admin/cabin",
                      "/admin/guilds", "/admin/presence", "/admin/releases"):
            self.assertIn(route, nav)
        feedback = (ROOT / "web/templates/feedback.html").read_text("utf-8")
        self.assertIn('include "partials/admin_nav.html"', feedback)
        self.assertIn('Chấp nhận đề xuất', feedback)
        self.assertIn('data-selected-ticket=', feedback)
        self.assertIn('Tải thêm ticket', feedback)
        self.assertIn('Người báo sẽ nhận DM kết quả cuối', feedback)
        self.assertIn('window.addEventListener(\'popstate\'', feedback)

    def test_page_scoped_js_without_global_three_second_poll(self):
        js = (ROOT / "web/static/admin_console.js").read_text("utf-8")
        self.assertIn("const loaders={overview,activity,monitoring,assistant,tarot,cabin,guilds,presence,releases}", js)
        self.assertIn("document.hidden", js)
        self.assertNotIn("setInterval(fetchDashboardData, 3000)", js)
        self.assertIn("'X-CSRF-Token':csrf", js)
        self.assertIn("encodeURIComponent", js)


class ConsoleFlaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import app
        cls.app = app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()

    def login(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
            session["feedback_csrf"] = "test-safe-token"

    def test_historical_dashboard_is_primary_and_feedback_kept(self):
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.login()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"tab-btn-activity", response.data)
        self.assertIn(b"tab-btn-guilds", response.data)
        self.assertIn(b"tab-btn-tarot", response.data)
        self.assertIn(b"tab-btn-logs", response.data)
        self.assertIn(b"Feedback Inbox", response.data)
        self.assertNotIn(b"asumi-sidebar", response.data)
        for path in ("/admin/feedback", "/admin/feedback/FB-TEST-15"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_newer_dashboard_bookmarks_redirect_to_old_tabs(self):
        self.login()
        expected = {
            "/admin/activity": "/admin?tab=activity",
            "/admin/monitoring": "/admin?tab=logs",
            "/admin/assistant": "/admin?tab=activity",
            "/admin/tarot": "/admin?tab=tarot",
            "/admin/cabin": "/admin?tab=cabin",
            "/admin/guilds": "/admin?tab=guilds",
            "/admin/presence": "/admin?tab=presence",
            "/admin/releases": "/admin?tab=version",
            "/admin/legacy": "/admin",
        }
        for path, target in expected.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.headers["Location"].endswith(target))
        self.assertEqual(self.client.get("/admin/unknown").status_code, 404)

    def test_destructive_legacy_routes_require_csrf(self):
        self.login()
        self.assertEqual(self.client.post("/api/guilds/leave",
                          json={"guild_id": "123"}).status_code, 403)
        self.assertEqual(self.client.post("/api/tarot/reset-all-cooldowns",
                          json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/presence",
                          json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/guilds/leave", data="x",
                          headers={"X-CSRF-Token": "test-safe-token"}).status_code, 415)

    def test_inbox_paging_api_authorized(self):
        self.login()
        from features.feedback.store import feedback_store
        with patch.object(feedback_store, "admin_list", new=AsyncMock(
            return_value=[{"id": "FB-A"}, {"id": "FB-B"}, {"id": "FB-C"}]
        )) as mock_list:
            response = self.client.get("/api/admin/feedback?limit=2&offset=10&view=pending&q=15")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["count"], 2)
        self.assertTrue(response.json["has_more"])
        self.assertEqual(mock_list.await_args.kwargs["offset"], 10)
        self.assertEqual(mock_list.await_args.kwargs["view"], "pending")
        self.assertEqual(mock_list.await_args.kwargs["query"], "15")


if __name__ == "__main__":
    unittest.main()
