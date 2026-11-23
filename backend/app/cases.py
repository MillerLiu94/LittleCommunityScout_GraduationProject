import json
import random
import time

from sqlalchemy import text

from app.db import engine
from app.storage import object_url

_CASE_COLUMNS = (
    "cases_id, description, category_id, images, status, created_at, "
    "author_account, address, reject_reason"
)


def _ensure_user(connection, account: str) -> None:
    """帳號第一次通報時自動建立 resident 身份，避免 cases 外鍵失敗。

    依現有 users 表結構（account 為 PK，另有 name / is_staff 非空欄位）；
    注意 users.chk_account_alphanumeric 只允許 [A-Za-z0-9]+。
    """
    connection.execute(
        text(
            "INSERT INTO users (account, name, is_staff) "
            "VALUES (:account, :account, false) "
            "ON CONFLICT (account) DO NOTHING"
        ),
        {"account": account},
    )


def create_case(
    description: str,
    category_id: int,
    images: list[str] | None,
    address: str | None,
    author_account: str,
) -> dict:
    """依 cases 表欄位建立新案件。address NOT NULL，未提供時寫空字串。"""
    created_at = int(time.time() * 1000)
    # 與 13 位數毫秒時間戳同級的流水號 (例: 1717000000011)
    cases_id = int(created_at * 10 + random.randint(0, 9))

    with engine.begin() as connection:
        _ensure_user(connection, author_account)
        row = connection.execute(
            text(
                "INSERT INTO cases "
                "(cases_id, description, category_id, images, "
                " status, created_at, author_account, address) "
                "VALUES "
                "(:cases_id, :description, :category_id, "
                " CAST(:images AS jsonb), 'pending', :created_at, :author_account, :address) "
                "RETURNING " + _CASE_COLUMNS
            ),
            {
                "cases_id": cases_id,
                "description": description,
                "category_id": category_id,
                "images": json.dumps(images, ensure_ascii=False) if images else None,
                "created_at": created_at,
                "author_account": author_account,
                "address": (address or "").strip(),
            },
        ).mappings().first()
    return dict(row)


def list_cases_by_account(
    author_account: str, *, limit: int = 50, offset: int = 0
) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT c.cases_id, c.description, c.category_id, c.images, "
                "c.status, c.created_at, c.author_account, c.address, "
                "c.reject_reason, categories.label AS category_label "
                "FROM cases AS c "
                "LEFT JOIN categories ON categories.categories_id = c.category_id "
                "WHERE c.author_account = :account "
                "ORDER BY c.created_at DESC LIMIT :limit OFFSET :offset"
            ),
            {"account": author_account, "limit": limit, "offset": offset},
        ).mappings().all()
    cases = [dict(r) for r in rows]
    for case in cases:
        case["image_urls"] = [object_url(path) for path in (case.get("images") or [])]
    return cases