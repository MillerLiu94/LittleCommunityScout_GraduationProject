import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import text

from app.config import (
    FRONTEND_BASE_URL,
    LINE_AUTHORIZE_URL,
    LINE_LOGIN_BOT_PROMPT,
    LINE_LOGIN_CHANNEL_ID,
    LINE_LOGIN_CHANNEL_SECRET,
    LINE_LOGIN_FAILURE_PATH,
    LINE_LOGIN_REDIRECT_URI,
    LINE_LOGIN_SCOPE,
    LINE_LOGIN_SUCCESS_PATH,
    LINE_PROFILE_URL,
    LINE_TOKEN_URL,
    SESSION_SECRET,
)
from app.db import engine

_USER_COLUMNS = "account, name, is_staff, is_suspended, line_user_id"


class LineLoginError(Exception):
    """LINE OAuth／使用者對應失敗；訊息只放錯誤代碼，不放 token 或 secret。"""


@dataclass(frozen=True)
class AuthUser:
    account: str
    name: str
    role: str
    is_staff: bool
    is_suspended: bool


def line_login_configured() -> bool:
    """四個必要設定都齊全才啟用，避免用不安全的預設值啟動登入。"""
    return bool(
        LINE_LOGIN_CHANNEL_ID
        and LINE_LOGIN_CHANNEL_SECRET
        and LINE_LOGIN_REDIRECT_URI
        and SESSION_SECRET
    )


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(state: str, code_challenge: str | None = None) -> str:
    params = {
        "response_type": "code",
        "client_id": LINE_LOGIN_CHANNEL_ID,
        "redirect_uri": LINE_LOGIN_REDIRECT_URI,
        "state": state,
        "scope": LINE_LOGIN_SCOPE,
    }
    if LINE_LOGIN_BOT_PROMPT:
        params["bot_prompt"] = LINE_LOGIN_BOT_PROMPT
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    separator = "&" if "?" in LINE_AUTHORIZE_URL else "?"
    return LINE_AUTHORIZE_URL + separator + urlencode(params)


def exchange_code(code: str, code_verifier: str | None = None) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": LINE_LOGIN_REDIRECT_URI,
        "client_id": LINE_LOGIN_CHANNEL_ID,
        "client_secret": LINE_LOGIN_CHANNEL_SECRET,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier
    try:
        response = httpx.post(LINE_TOKEN_URL, data=data, timeout=10.0)
    except httpx.HTTPError as exc:
        raise LineLoginError("token_request_failed") from exc
    if response.status_code >= 400:
        raise LineLoginError(f"token_exchange_failed_{response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise LineLoginError("token_response_invalid") from exc
    if not isinstance(payload, dict):
        raise LineLoginError("token_response_invalid")
    return payload


def fetch_profile(access_token: str) -> dict:
    try:
        response = httpx.get(
            LINE_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise LineLoginError("profile_request_failed") from exc
    if response.status_code >= 400:
        raise LineLoginError(f"profile_fetch_failed_{response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise LineLoginError("profile_response_invalid") from exc
    if not isinstance(payload, dict) or not payload.get("userId"):
        raise LineLoginError("profile_response_invalid")
    return payload


def _select_user(connection, *, line_user_id: str | None = None, account: str | None = None):
    if line_user_id is not None:
        sql = f"SELECT {_USER_COLUMNS} FROM users WHERE line_user_id = :line_user_id"
        params = {"line_user_id": line_user_id}
    elif account is not None:
        sql = f"SELECT {_USER_COLUMNS} FROM users WHERE account = :account"
        params = {"account": account}
    else:
        return None
    return connection.execute(text(sql), params).mappings().first()


def find_or_create_user(line_user_id: str, display_name: str) -> AuthUser:
    """以 LINE userId 對應 users.line_user_id；第一次登入自動建立 resident。"""
    uid = (line_user_id or "").strip()
    if not uid:
        raise LineLoginError("missing_line_user_id")

    name = (display_name or "").strip() or "LINE使用者"
    name = name[:100]

    with engine.begin() as connection:
        row = _select_user(connection, line_user_id=uid)
        if row is None:
            row = _select_user(connection, account=uid)

        if row is None:
            # account 必須符合 users.chk_account_alphanumeric；LINE userId 是 U + 32 hex。
            row = connection.execute(
                text(
                    "INSERT INTO users "
                    "(account, name, is_suspended, is_staff, line_user_id) "
                    "VALUES (:account, :name, false, false, :line_user_id) "
                    "ON CONFLICT DO NOTHING "
                    f"RETURNING {_USER_COLUMNS}"
                ),
                {"account": uid, "name": name, "line_user_id": uid},
            ).mappings().first()
            if row is None:
                # 併發登入或 account 已存在；重新查一次，避免交易被 unique violation 中止。
                row = _select_user(connection, line_user_id=uid) or _select_user(
                    connection, account=uid
                )
                if row is None:
                    raise LineLoginError("user_create_failed")

        if row["line_user_id"] is None:
            connection.execute(
                text(
                    "UPDATE users SET line_user_id = :line_user_id "
                    "WHERE account = :account"
                ),
                {"line_user_id": uid, "account": row["account"]},
            )
            row = dict(row)
            row["line_user_id"] = uid
        elif row["line_user_id"] != uid:
            raise LineLoginError("account_already_linked")

        if row["name"] != name:
            connection.execute(
                text("UPDATE users SET name = :name WHERE account = :account"),
                {"name": name, "account": row["account"]},
            )
            row = dict(row)
            row["name"] = name

    return AuthUser(
        account=row["account"],
        name=row["name"],
        role="staff" if row["is_staff"] else "resident",
        is_staff=bool(row["is_staff"]),
        is_suspended=bool(row["is_suspended"]),
    )


def get_user_by_account(account: str) -> AuthUser | None:
    account = (account or "").strip()
    if not account:
        return None
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT account, name, is_staff, is_suspended "
                "FROM users WHERE account = :account"
            ),
            {"account": account},
        ).mappings().first()
    if row is None:
        return None
    return AuthUser(
        account=row["account"],
        name=row["name"],
        role="staff" if row["is_staff"] else "resident",
        is_staff=bool(row["is_staff"]),
        is_suspended=bool(row["is_suspended"]),
    )


def resolve_session_role(session_role: str | None, is_staff: bool) -> str:
    if session_role not in {"resident", "staff"}:
        return "staff" if is_staff else "resident"
    if session_role == "staff" and not is_staff:
        return "resident"
    return session_role


def _frontend_url(path: str) -> str:
    path = (path or "").strip()
    if path.startswith(("http://", "https://")):
        return path
    if not path:
        path = "/"
    return FRONTEND_BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def build_redirect_url(path: str, **params: str) -> str:
    url = _frontend_url(path)
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value is not None and value != "":
            query[key] = value
    return urlunsplit(parts._replace(query=urlencode(query)))


def success_redirect(role: str) -> str:
    return build_redirect_url(LINE_LOGIN_SUCCESS_PATH, role=role)


def failure_redirect(reason: str | None = None) -> str:
    params = {"reason": reason} if reason else {}
    return build_redirect_url(LINE_LOGIN_FAILURE_PATH, **params)
