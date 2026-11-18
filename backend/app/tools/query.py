import logging

from langchain_core.tools import tool

from app.db import readonly_engine
from app.tools.sql_guard import SQLValidationError, validate_readonly_sql

logger = logging.getLogger(__name__)

_MAX_ROWS = 50
_MAX_TEXT_LEN = 12000


def _limited_sql(sql_query: str) -> str:
    """把使用者查詢包在外層 LIMIT 內，避免一次拉回整張表。"""
    return f"SELECT * FROM ({sql_query}) AS _chat_limited LIMIT {_MAX_ROWS + 1}"


def _rows_as_dicts(cursor, limit: int) -> list[dict]:
    columns = [column[0] for column in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in cursor.fetchmany(limit)]


@tool
def query_community_database(sql_query: str) -> str:
    """
    查詢 community_envoys 資料庫的唯讀工具。
    只允許查詢 cases (案件紀錄) 與 categories (類別) 資料表。
    請傳入標準的 PostgreSQL SELECT 語法；不支援 INSERT / UPDATE / DELETE 等寫入語法。
    傳回結果中不會包含 embedding 欄位（1024 維向量對回答沒幫助）。
    """
    if readonly_engine is None:
        return "資料庫查詢功能目前未啟用。"

    try:
        guarded = validate_readonly_sql(sql_query)
    except SQLValidationError as exc:
        logger.warning("chat SQL rejected: %s", exc)
        return f"查詢被拒絕：{exc}"

    try:
        # 用 DBAPI cursor 直接執行，避免 SQLAlchemy 把 LIKE 的 % 當成參數佔位符。
        # 連線本身已由 readonly_engine 設為 default_transaction_read_only=on。
        with readonly_engine.connect() as connection:
            with connection.begin():
                cursor = connection.connection.cursor()
                try:
                    cursor.execute(_limited_sql(guarded))
                    rows = _rows_as_dicts(cursor, _MAX_ROWS + 1)
                finally:
                    cursor.close()
    except Exception:
        logger.exception("readonly database query failed")
        return "資料庫查詢失敗，請換個問法或稍後再試。"

    for row in rows:
        row.pop("embedding", None)

    if not rows:
        return "查詢成功，但沒有找到符合的資料。"

    over = len(rows) - _MAX_ROWS
    rows = rows[:_MAX_ROWS]
    text_out = "\n".join(str(row) for row in rows)
    if over > 0:
        text_out += f"\n……（其餘 {over} 筆省略）"
    if len(text_out) > _MAX_TEXT_LEN:
        text_out = text_out[: _MAX_TEXT_LEN] + "\n……（結果過長，已截斷）"
    return text_out
