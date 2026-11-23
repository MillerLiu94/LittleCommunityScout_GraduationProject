import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.auth import AuthUser
from app import server


RESIDENT = AuthUser("Uresident", "住戶", "resident", False)
STAFF = AuthUser("Ustaff", "工作人員", "staff", True)


def make_client() -> TestClient:
    return TestClient(server.app, base_url="https://testserver")


def start_login(client: TestClient, role: str = "resident"):
    with (
        patch.object(server, "line_login_configured", return_value=True),
        patch.object(server, "generate_state", return_value="state-value"),
        patch.object(server, "generate_pkce_pair", return_value=("verifier", "challenge")),
        patch.object(
            server,
            "build_authorize_url",
            return_value="https://access.line.me/oauth2/v2.1/authorize?state=state-value",
        ),
    ):
        return client.get(
            f"/api/auth/line/login?role={role}",
            follow_redirects=False,
        )


class LineLoginFlowTests(unittest.TestCase):
    def test_callback_sets_session_and_me(self):
        client = make_client()
        response = start_login(client)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "https://access.line.me/oauth2/v2.1/authorize?state=state-value")

        with (
            patch.object(server, "line_login_configured", return_value=True),
            patch.object(server, "exchange_code", return_value={"access_token": "token"}),
            patch.object(
                server,
                "fetch_profile",
                return_value={"userId": "Uresident", "displayName": "住戶"},
            ),
            patch.object(server, "find_or_create_user", return_value=RESIDENT),
        ):
            callback = client.get(
                "/api/auth/line/callback?code=code&state=state-value",
                follow_redirects=False,
            )

        self.assertEqual(callback.status_code, 302)
        query = parse_qs(urlsplit(callback.headers["location"]).query)
        self.assertEqual(query["login"], ["success"])
        self.assertEqual(query["role"], ["resident"])

        with patch.object(server, "get_user_by_account", return_value=RESIDENT):
            me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["account"], "Uresident")
        self.assertEqual(me.json()["role"], "resident")

        self.assertEqual(client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(client.get("/api/auth/me").status_code, 401)

    def test_staff_login_grants_staff_role(self):
        client = make_client()
        start_login(client, role="staff")

        with (
            patch.object(server, "line_login_configured", return_value=True),
            patch.object(server, "exchange_code", return_value={"access_token": "token"}),
            patch.object(
                server,
                "fetch_profile",
                return_value={"userId": "Ustaff", "displayName": "工作人員"},
            ),
            patch.object(server, "find_or_create_user", return_value=STAFF),
        ):
            callback = client.get(
                "/api/auth/line/callback?code=code&state=state-value",
                follow_redirects=False,
            )

        query = parse_qs(urlsplit(callback.headers["location"]).query)
        self.assertEqual(query["role"], ["staff"])

        with patch.object(server, "get_user_by_account", return_value=STAFF):
            me = client.get("/api/auth/me")
        self.assertEqual(me.json()["role"], "staff")

    def test_staff_login_rejects_resident_account(self):
        client = make_client()
        start_login(client, role="staff")

        with (
            patch.object(server, "line_login_configured", return_value=True),
            patch.object(server, "exchange_code", return_value={"access_token": "token"}),
            patch.object(
                server,
                "fetch_profile",
                return_value={"userId": "Uresident", "displayName": "住戶"},
            ),
            patch.object(server, "find_or_create_user", return_value=RESIDENT),
        ):
            callback = client.get(
                "/api/auth/line/callback?code=code&state=state-value",
                follow_redirects=False,
            )

        query = parse_qs(urlsplit(callback.headers["location"]).query)
        self.assertEqual(query["login"], ["failed"])
        self.assertEqual(query["reason"], ["not_staff"])
        self.assertEqual(client.get("/api/auth/me").status_code, 401)

    def test_callback_rejects_invalid_state(self):
        client = make_client()
        start_login(client)

        with patch.object(server, "line_login_configured", return_value=True):
            callback = client.get(
                "/api/auth/line/callback?code=code&state=wrong",
                follow_redirects=False,
            )

        query = parse_qs(urlsplit(callback.headers["location"]).query)
        self.assertEqual(query["login"], ["failed"])
        self.assertEqual(query["reason"], ["invalid_state"])


class ProtectedEndpointTests(unittest.TestCase):
    def test_cases_and_uploads_require_login(self):
        client = make_client()
        self.assertEqual(client.get("/api/cases").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/cases",
                json={"description": "這是一段足夠長的測試描述", "category_id": 1},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                "/api/uploads",
                files={"files": ("photo.jpg", b"not-an-image", "image/jpeg")},
            ).status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
