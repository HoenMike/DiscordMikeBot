"""Asumi T23 owner-only OAuth 2.1 MCP handshake, PKCE and consent safety."""
import base64
import hashlib
import unittest
from unittest.mock import AsyncMock, patch

from features.feedback.oauth import (
    RESOURCE, SCOPE, OAuthError, authorize_bearer, exchange_code,
    refresh_access_token, issue_code, register_chatgpt_client,
    valid_redirect, validate_auth_request, _digest, _pkce_challenge
)

CLIENT = "chatgpt-client-test"
REDIRECT = "https://chatgpt.com/connector/oauth/abcdefghijklmnopqrstuvwxyz"
VERIFIER = "correct-horse-battery-staple-oauth-pkce-verifier-43"
CHALLENGE = _pkce_challenge(VERIFIER)


class OAuthShapeTests(unittest.TestCase):
    def test_only_official_callback(self):
        self.assertTrue(valid_redirect(REDIRECT))
        self.assertTrue(valid_redirect("https://chatgpt.com/connector_platform_oauth_redirect"))
        for value in (
            "https://chatgpt.com.evil.org/connector/oauth/abcdefghijklmnop",
            "http://chatgpt.com/connector/oauth/abcdefghijklmnop",
            "https://attacker.dev/callback",
            "https://chatgpt.com/connector/oauth/a?redirect=https://evil.com",
        ):
            with self.subTest(value=value):
                self.assertFalse(valid_redirect(value))

    def test_pkce_challenge(self):
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(VERIFIER.encode()).digest()
        ).rstrip(b"=").decode()
        self.assertEqual(CHALLENGE, expected)


class OAuthDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_dynamic_registration_scoped_to_chatgpt(self):
        with patch("features.feedback.oauth._change", new=AsyncMock(return_value=1)) as insert:
            result = await register_chatgpt_client([REDIRECT])
        self.assertEqual(result["redirect_uris"], [REDIRECT])
        self.assertEqual(result["token_endpoint_auth_method"], "none")
        self.assertEqual(insert.await_args.args[1][1], REDIRECT)
        with self.assertRaises(OAuthError):
            await register_chatgpt_client(["https://example.com/callback"])

    async def test_authorization_checks_redirect_resource_scope_and_pkce(self):
        params = {
            "client_id": CLIENT, "redirect_uri": REDIRECT,
            "response_type": "code", "code_challenge": CHALLENGE,
            "code_challenge_method": "S256", "resource": RESOURCE,
            "scope": SCOPE, "state": "abcdefghij123456",
        }
        with patch("features.feedback.oauth._query", new=AsyncMock(return_value=[(REDIRECT,)])):
            result = await validate_auth_request(params)
            self.assertEqual(result["challenge"], CHALLENGE)
            with self.assertRaises(OAuthError):
                await validate_auth_request({**params, "scope": "all"})
            with self.assertRaises(OAuthError):
                await validate_auth_request({**params, "redirect_uri": "https://evil.com/"})
            with self.assertRaises(OAuthError):
                await validate_auth_request({**params, "code_challenge_method": "plain"})

    async def test_code_exchange_rejects_wrong_verifier_or_replay(self):
        import time
        expected = (CLIENT, REDIRECT, CHALLENGE, RESOURCE, SCOPE, int(time.time())+300, 0)
        args = {
            "code": "the-one-time-code", "client_id": CLIENT,
            "redirect_uri": REDIRECT, "resource": RESOURCE, "code_verifier": VERIFIER
        }
        with patch("features.feedback.oauth._query", new=AsyncMock(return_value=[expected])), patch(
            "features.feedback.oauth._change", new=AsyncMock(return_value=1)
        ), patch("features.feedback.oauth._issue_pair", new=AsyncMock(return_value={"token_type":"Bearer"})):
            result = await exchange_code(args)
            self.assertEqual(result["token_type"], "Bearer")
            with self.assertRaises(OAuthError):
                await exchange_code({**args, "code_verifier": "bad"})
        with patch("features.feedback.oauth._query", new=AsyncMock(return_value=[expected])), patch(
            "features.feedback.oauth._change", new=AsyncMock(return_value=0)
        ), self.assertRaises(OAuthError):
            await exchange_code(args)

    async def test_expired_code_fails(self):
        import time
        expired = (CLIENT, REDIRECT, CHALLENGE, RESOURCE, SCOPE, int(time.time())-1, 0)
        with patch("features.feedback.oauth._query", new=AsyncMock(return_value=[expired])), self.assertRaises(OAuthError):
            await exchange_code({
                "code":"code","client_id":CLIENT,"redirect_uri":REDIRECT,
                "resource":RESOURCE,"code_verifier":VERIFIER,
            })

    async def test_access_token_resource_scope_and_expiry(self):
        import time
        token = "test_" + "a"*60
        with patch("features.feedback.oauth._query", new=AsyncMock(
            return_value=[(RESOURCE, SCOPE, int(time.time())+100, 0)]
        )):
            self.assertTrue(await authorize_bearer("Bearer " + token))
        with patch("features.feedback.oauth._query", new=AsyncMock(
            return_value=[(RESOURCE, SCOPE, int(time.time())-100, 0)]
        )):
            self.assertFalse(await authorize_bearer("Bearer " + token))
        with patch("features.feedback.oauth._query", new=AsyncMock(
            return_value=[("https://evil.com", SCOPE, int(time.time())+100, 0)]
        )):
            self.assertFalse(await authorize_bearer("Bearer " + token))
        self.assertFalse(await authorize_bearer(""))

    async def test_refresh_token_is_rotated(self):
        import time
        with patch("features.feedback.oauth._query", new=AsyncMock(return_value=[
            (CLIENT, RESOURCE, SCOPE, int(time.time())+300, 0)
        ])), patch("features.feedback.oauth._change", new=AsyncMock(return_value=1)) as change, patch(
            "features.feedback.oauth._issue_pair", new=AsyncMock(return_value={"token_type":"Bearer"})
        ):
            token = await refresh_access_token({
                "client_id": CLIENT, "resource": RESOURCE, "refresh_token": "x"*60
            })
            self.assertEqual(token["token_type"], "Bearer")
            self.assertIn("SET revoked=1", change.await_args.args[0])


class OAuthRoutesTests(unittest.TestCase):
    def test_flask_registration_and_auth_not_public_mcp(self):
        from pathlib import Path
        app = (Path(__file__).resolve().parents[1] / "web/app.py").read_text("utf-8")
        for route in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server",
                      "/oauth/register", "/oauth/authorize", "/oauth/token"):
            self.assertIn(route, app)
        self.assertIn("if not session.get(\"logged_in\")", app)
        self.assertIn("hmac.compare_digest", app)
        self.assertIn("@feedback_mcp_oauth_required", app)
        self.assertIn("WWW-Authenticate", app)
        self.assertIn("scope=\"feedback:read feedback:propose\"", app)


if __name__ == "__main__":
    unittest.main()
