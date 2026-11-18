import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def _env_bool(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
# 給瀏覽器地圖用的金鑰（需在 Google Cloud 限制允許網域）；與後端 Places/Geocoding 用的金鑰分開。
GOOGLE_MAPS_BROWSER_API_KEY = os.getenv("GOOGLE_MAPS_BROWSER_API_KEY", "")
FRONTEND_ALLOW_DESKTOP_REPORT_PREVIEW = os.getenv(
    "FRONTEND_ALLOW_DESKTOP_REPORT_PREVIEW", ""
).lower() in {"1", "true", "yes"}
FRONTEND_MOCK_AUTHOR_ACCOUNT = os.getenv("MOCK_AUTHOR_ACCOUNT", "test1")
DATABASE_URL = os.getenv("DATABASE_URL", "")
# AI chat／vision agent 專用的唯讀連線；未設定時聊天工具會停用，不會回退到可寫入的 DATABASE_URL。
READONLY_DATABASE_URL = os.getenv("READONLY_DATABASE_URL", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
TRANSCRIPTION_API_URL = os.getenv("TRANSCRIPTION_API_URL", "")

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
# gcs | local（gcs 優先，失敗自動退 local，方便沒有 GCS 憑證時測試）
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "gcs")
LOCAL_UPLOAD_DIR = Path(
    os.getenv("LOCAL_UPLOAD_DIR", str(Path(__file__).resolve().parent.parent / "data" / "uploads"))
)

# LINE Login（LINE Login channel，不是 Messaging API channel）
LINE_LOGIN_CHANNEL_ID = os.getenv("LINE_LOGIN_CHANNEL_ID", "").strip()
LINE_LOGIN_CHANNEL_SECRET = os.getenv("LINE_LOGIN_CHANNEL_SECRET", "").strip()
LINE_LOGIN_REDIRECT_URI = os.getenv("LINE_LOGIN_REDIRECT_URI", "").strip()
LINE_LOGIN_PATH = os.getenv("LINE_LOGIN_PATH", "/auth/line/login").strip() or "/auth/line/login"
LINE_LOGIN_SCOPE = os.getenv("LINE_LOGIN_SCOPE", "profile").strip() or "profile"
LINE_LOGIN_BOT_PROMPT = os.getenv("LINE_LOGIN_BOT_PROMPT", "").strip()
LINE_LOGIN_STATE_TTL = _env_int("LINE_LOGIN_STATE_TTL", 600)
LINE_AUTHORIZE_URL = os.getenv(
    "LINE_AUTHORIZE_URL", "https://access.line.me/oauth2/v2.1/authorize"
).strip()
LINE_TOKEN_URL = os.getenv(
    "LINE_TOKEN_URL", "https://api.line.me/oauth2/v2.1/token"
).strip()
LINE_PROFILE_URL = os.getenv(
    "LINE_PROFILE_URL", "https://api.line.me/v2/profile"
).strip()

# 登入成功／失敗後導回的前端位置。路徑相對於 FRONTEND_BASE_URL；
# 也可以直接把 *_PATH 設成完整的 http(s) URL。
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:8000").strip().rstrip("/")
LINE_LOGIN_SUCCESS_PATH = os.getenv(
    "LINE_LOGIN_SUCCESS_PATH", "/pages/login/login.html?login=success"
).strip()
LINE_LOGIN_FAILURE_PATH = os.getenv(
    "LINE_LOGIN_FAILURE_PATH", "/pages/login/login.html?login=failed"
).strip()

# 簽署 session cookie 與 OAuth state。未設定時 LINE 登入會停用（不回退到不安全預設）。
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "lcs_session").strip() or "lcs_session"
SESSION_MAX_AGE = _env_int("SESSION_MAX_AGE", 604800)
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", "false")
SESSION_COOKIE_SAMESITE = (
    os.getenv("SESSION_COOKIE_SAMESITE", "lax").strip().lower() or "lax"
)

# 前後端不同 origin 且直接連線時才需要；留空表示沿用 allow_origins=["*"]（不帶 credentials）。
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
]