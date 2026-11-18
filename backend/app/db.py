from sqlalchemy import create_engine

from app.config import DATABASE_URL, READONLY_DATABASE_URL


def _normalize_url(url: str) -> str:
    """URL 以 postgresql:// 開頭時，明確指定 psycopg3 驅動。"""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(_normalize_url(DATABASE_URL), pool_pre_ping=True)

# 給 LLM 查詢工具專用。除了使用 readonly_user，還在連線層強制每個交易唯讀並
# 設定 statement_timeout；即使 DB 角色權限設定有誤，這一層仍能擋住寫入。
_READONLY_OPTIONS = (
    "-c default_transaction_read_only=on "
    "-c statement_timeout=5000 "
    "-c idle_in_transaction_session_timeout=10000"
)

readonly_engine = (
    create_engine(
        _normalize_url(READONLY_DATABASE_URL),
        pool_pre_ping=True,
        connect_args={
            "options": _READONLY_OPTIONS,
            "connect_timeout": 5,
            "application_name": "lcs-chat-readonly",
        },
    )
    if READONLY_DATABASE_URL
    else None
)