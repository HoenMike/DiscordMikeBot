"""Private screenshot retrieval via MCP; no public URLs or cross-ticket reads."""
import base64
import hashlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
from features.feedback.evidence import PrivateEvidenceStore, EvidenceError
from features.feedback.mcp_bridge import handle_mcp


def image_bytes():
    output=io.BytesIO()
    Image.new("RGB",(250,160),"white").save(output,"PNG")
    return output.getvalue()


class EvidenceReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_private_screenshot_validates_hash_and_reencodes(self):
        payload=image_bytes()
        client=MagicMock()
        client.get_object.return_value={"Body":io.BytesIO(payload)}
        with patch.dict("os.environ",{"ASUMI_FEEDBACK_R2_BUCKET":"private-evidence"}):
            store=PrivateEvidenceStore(client=client)
            result=await store.read_preview(
                key="feedback/77/asset.png",guild_id="77",
                sha256=hashlib.sha256(payload).hexdigest()
            )
        self.assertTrue(result.startswith(b"\xff\xd8"))
        self.assertLess(len(result),len(payload)*20)
        client.get_object.assert_called_once_with(
            Bucket="private-evidence",Key="feedback/77/asset.png"
        )

    async def test_cross_guild_or_tampered_image_never_leaks(self):
        payload=image_bytes()
        client=MagicMock()
        with patch.dict("os.environ",{"ASUMI_FEEDBACK_R2_BUCKET":"private-evidence"}):
            store=PrivateEvidenceStore(client=client)
            with self.assertRaises(EvidenceError):
                await store.read_preview(
                    key="feedback/999/private.png",guild_id="77",sha256="x"
                )
            client.get_object.assert_not_called()
            client.get_object.return_value={"Body":io.BytesIO(payload)}
            with self.assertRaises(EvidenceError):
                await store.read_preview(
                    key="feedback/77/private.png",guild_id="77",
                    sha256="deadbeef"
                )

    async def test_mcp_image_tool_returns_private_inline_image_no_bucket_key(self):
        ticket={
            "id":"FB-OLD","display_id":"#1","number":1,
            "guild_id":"77",
            "evidence":[{"key":"feedback/77/private.png","sha256":"abcd"}]
        }
        rpc={"jsonrpc":"2.0","id":1,"method":"tools/call",
             "params":{"name":"get_feedback_evidence",
                       "arguments":{"ticket_id":"#1","index":0}}}
        with patch("features.feedback.mcp_bridge.feedback_store.admin_detail",
                   new=AsyncMock(return_value=ticket)), patch(
            "features.feedback.mcp_bridge.evidence_store.read_preview",
            new=AsyncMock(return_value=b"\xff\xd8test")
        ) as reader:
            result=await handle_mcp(rpc)
        body=result["result"]
        self.assertFalse(body["isError"])
        self.assertEqual(body["content"][0]["type"],"image")
        self.assertEqual(base64.b64decode(body["content"][0]["data"]),b"\xff\xd8test")
        self.assertEqual(body["structuredContent"]["display_id"],"#1")
        self.assertNotIn("feedback/77",str(body["structuredContent"]))
        reader.assert_awaited_once_with(
            key="feedback/77/private.png",guild_id="77",sha256="abcd"
        )

    async def test_mcp_bad_index_or_unknown_ticket_rejected(self):
        rpc={"jsonrpc":"2.0","id":1,"method":"tools/call",
             "params":{"name":"get_feedback_evidence",
                       "arguments":{"ticket_id":"#1","index":3}}}
        result=await handle_mcp(rpc)
        self.assertTrue(result["result"]["isError"])
        rpc["params"]["arguments"]["index"]=0
        with patch("features.feedback.mcp_bridge.feedback_store.admin_detail",
                   new=AsyncMock(return_value=None)):
            result=await handle_mcp(rpc)
        self.assertTrue(result["result"]["isError"])


if __name__=="__main__":
    unittest.main()
