import base64
import hashlib
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app import auth


class LineLoginConfigTests(unittest.TestCase):
    def test_requires_channel_redirect_and_session_secret(self):
        values = {
            "LINE_LOGIN_CHANNEL_ID": "channel",
            "LINE_LOGIN_CHANNEL_SECRET": "secret",
            "LINE_LOGIN_REDIRECT_URI": "https://example.test/api/auth/line/callback",
            "SESSION_SECRET": "session-secret",
        }
        for name, value in values.items():
            with self.subTest(missing=name):
                patched = dict(values)
                patched[name] = ""
                with (
                    patch.object(auth, "LINE_LOGIN_CHANNEL_ID", patched["LINE_LOGIN_CHANNEL_ID"]),
                    patch.object(auth, "LINE_LOGIN_CHANNEL_SECRET", patched["LINE_LOGIN_CHANNEL_SECRET"]),
                    patch.object(auth, "LINE_LOGIN_REDIRECT_URI", patched["LINE_LOGIN_REDIRECT_URI"]),
                    patch.object(auth, "SESSION_SECRET", patched["SESSION_SECRET"]),
                ):
                    self.assertFalse(auth.line_login_configured())
        with (
            patch.object(auth, "LINE_LOGIN_CHANNEL_ID", values["LINE_LOGIN_CHANNEL_ID"]),
            patch.object(auth, "LINE_LOGIN_CHANNEL_SECRET", values["LINE_LOGIN_CHANNEL_SECRET"]),
            patch.object(auth, "LINE_LOGIN_REDIRECT_URI", values["LINE_LOGIN_REDIRECT_URI"]),
            patch.object(auth, "SESSION_SECRET", values["SESSION_SECRET"]),
        ):
            self.assertTrue(auth.line_login_configured())


class PkceTests(unittest.TestCase):
    def test_challenge_matches_verifier(self):
        verifier, challenge = auth.generate_pkce_pair()
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        self.assertEqual(challenge, expected)
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)


class RedirectTests(unittest.TestCase):
    def test_success_redirect_appends_role(self):
        with (
            patch.object(auth, "FRONTEND_BASE_URL", "https://example.test"),
            patch.object(
                auth, "LINE_LOGIN_SUCCESS_PATH", "/pages/login/login.html?login=success"
            ),
        ):
            url = auth.success_redirect("staff")
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "example.test")
        self.assertEqual(parsed.path, "/pages/login/login.html")
        self.assertEqual(parse_qs(parsed.query), {"login": ["success"], "role": ["staff"]})

    def test_failure_redirect_adds_reason(self):
        with (
            patch.object(auth, "FRONTEND_BASE_URL", "https://example.test"),
            patch.object(
                auth, "LINE_LOGIN_FAILURE_PATH", "/pages/login/login.html?login=failed"
            ),
        ):
            url = auth.failure_redirect("not_staff")
        self.assertIn("login=failed", url)
        self.assertIn("reason=not_staff", url)


class AuthorizeUrlTests(unittest.TestCase):
    def test_authorize_url_contains_oauth_parameters(self):
        with (
            patch.object(auth, "LINE_AUTHORIZE_URL", "https://access.line.me/oauth2/v2.1/authorize"),
            patch.object(auth, "LINE_LOGIN_CHANNEL_ID", "1234567890"),
            patch.object(
                auth, "LINE_LOGIN_REDIRECT_URI", "https://example.test/api/auth/line/callback"
            ),
            patch.object(auth, "LINE_LOGIN_SCOPE", "profile"),
            patch.object(auth, "LINE_LOGIN_BOT_PROMPT", ""),
        ):
            url = auth.build_authorize_url("state-value", "challenge-value")
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "access.line.me")
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["1234567890"])
        self.assertEqual(query["state"], ["state-value"])
        self.assertEqual(query["scope"], ["profile"])
        self.assertEqual(query["code_challenge"], ["challenge-value"])
        self.assertEqual(query["code_challenge_method"], ["S256"])


class SessionRoleTests(unittest.TestCase):
    def test_staff_can_view_as_resident(self):
        self.assertEqual(auth.resolve_session_role("resident", True), "resident")

    def test_staff_request_requires_staff_account(self):
        self.assertEqual(auth.resolve_session_role("staff", False), "resident")

    def test_missing_session_role_falls_back_to_account_role(self):
        self.assertEqual(auth.resolve_session_role(None, True), "staff")
        self.assertEqual(auth.resolve_session_role(None, False), "resident")


if __name__ == "__main__":
    unittest.main()
