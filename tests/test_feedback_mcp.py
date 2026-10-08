"""T23.3 MCP: private scoped read-and-propose surface, never auto approve."""
import unittest
from unittest.mock import AsyncMock, patch

from features.feedback.mcp_bridge import handle_mcp


def rpc(method, params=None, request_id=1):
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


class MCPBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_handshake(self):
        result = await handle_mcp(rpc("initialize", {"protocolVersion": "2025-06-18"}))
        self.assertEqual(result["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools",result["result"]["capabilities"])
        self.assertIsNone(await handle_mcp({"jsonrpc":"2.0","method":"notifications/initialized"}))

    async def test_only_read_and_propose_tools_exposed(self):
        result = await handle_mcp(rpc("tools/list"))
        names={t["name"] for t in result["result"]["tools"]}
        self.assertEqual(names, {
            "list_feedback_tickets", "get_feedback_ticket", "get_feedback_evidence", "propose_feedback_review",
        })
        self.assertFalse(any("approve" in name or "reject" in name for name in names))

    async def test_list_does_not_disclose_r2_key(self):
        row = {"id":"FB-EXAMPLE","evidence":[{"key":"feedback/secret.png"}], "status":"submitted"}
        with patch("features.feedback.mcp_bridge.feedback_store.admin_list", new=AsyncMock(return_value=[row])):
            result=await handle_mcp(rpc("tools/call",{
                "name":"list_feedback_tickets","arguments":{"limit":5}
            }))
        output=result["result"]["structuredContent"]
        self.assertEqual(output["tickets"][0]["evidence_count"],1)
        self.assertNotIn("evidence",output["tickets"][0])
        self.assertNotIn("feedback/secret.png",result["result"]["content"][0]["text"])

    async def test_get_ticket_is_read_only(self):
        with patch("features.feedback.mcp_bridge.feedback_store.admin_detail", new=AsyncMock(return_value={
            "id":"FB-0001","description":"user-written evidence","evidence":[{"key":"secret"}],
        })):
            result=await handle_mcp(rpc("tools/call",{
                "name":"get_feedback_ticket","arguments":{"ticket_id":"FB-0001"}
            }))
        self.assertEqual(result["result"]["structuredContent"]["ticket"]["evidence_count"],1)
        self.assertNotIn("evidence",result["result"]["structuredContent"]["ticket"])

    async def test_proposal_only_creates_pending_nonbinding_record(self):
        with patch("features.feedback.mcp_bridge.feedback_store.propose_review", new=AsyncMock(return_value="FP-123")) as propose:
            result=await handle_mcp(rpc("tools/call",{
                "name":"propose_feedback_review",
                "arguments":{"ticket_id":"FB-0001","status":"approved",
                             "reason":"It is a reproducible bug with evidence"}
            }))
        body=result["result"]["structuredContent"]
        self.assertFalse(body["ticket_changed"])
        self.assertEqual(body["state"],"pending_owner_review")
        self.assertEqual(propose.await_args.kwargs["source"],"chatgpt-mcp")

    async def test_unknown_action_or_bad_args_cannot_modify_ticket(self):
        for name in ("review_feedback", "auto_approve", "delete_ticket"):
            output=await handle_mcp(rpc("tools/call",{"name":name,"arguments":{}}))
            self.assertEqual(output["error"]["code"],-32602)
        for args in ({"limit":0}, {"limit":"500"}, {"limit":True}):
            output=await handle_mcp(rpc("tools/call",{"name":"list_feedback_tickets","arguments":args}))
            self.assertTrue(output["result"]["isError"])

    def test_http_route_is_bearer_protected(self):
        from pathlib import Path
        src=(Path(__file__).resolve().parents[1] / "web/app.py").read_text("utf-8")
        self.assertIn("def feedback_mcp_http(",src)
        self.assertIn("@feedback_mcp_oauth_required\ndef feedback_mcp_http()",src)
        self.assertIn("request.content_length > 16384",src)


if __name__=="__main__":
    unittest.main()
