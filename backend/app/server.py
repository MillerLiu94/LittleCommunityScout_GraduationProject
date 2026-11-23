import json
import secrets
import time
import uuid

import httpx
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app.agent.state import DB_EXPERT, MEMBERS, RESEARCHER
from app.analyze import analyze_images, list_categories
from app.agent.graph import build_agent
from app.auth import (
    LineLoginError,
    build_authorize_url,
    exchange_code,
    failure_redirect,
    fetch_profile,
    find_or_create_user,
    generate_pkce_pair,
    generate_state,
    get_user_by_account,
    line_login_configured,
    resolve_session_role,
    success_redirect,
)
from app.cases import create_case, list_cases_by_account
from app.config import (
    CORS_ALLOW_ORIGINS,
    FRONTEND_ALLOW_DESKTOP_REPORT_PREVIEW,
    FRONTEND_MOCK_AUTHOR_ACCOUNT,
    GOOGLE_MAPS_BROWSER_API_KEY,
    LINE_LOGIN_PATH,
    LINE_LOGIN_REDIRECT_URI,
    LINE_LOGIN_STATE_TTL,
    LOCAL_UPLOAD_DIR,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE,
    SESSION_SECRET,
    STORAGE_BACKEND,
    TRANSCRIPTION_API_URL,
)
from app.events import get_event, list_events
from app.image_location import ImageMetadataError
from app.places import PlacesProviderError, reverse_geocode, search_places
from app.storage import save_upload
from app.welfare import WelfareSearchError, search_welfare
from app.weather import WeatherProviderError, get_weather

BASE_DIR = Path(__file__).resolve().parent.parent
# 新前端是 monorepo 根目錄的 frontend/。有 build 過的 dist 就優先服務，
# 否則直接服務原始靜態檔（這個前端是原生 HTML/CSS/JS，不需要建置也能跑）。
FRONTEND_DIR = BASE_DIR.parent / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
FRONTEND_INDEX = "index.html"


def _frontend_root() -> Path | None:
    for root in (FRONTEND_DIST, FRONTEND_DIR):
        if (root / FRONTEND_INDEX).is_file():
            return root
    return None


def _frontend_file(full_path: str) -> Path | None:
    """在 dist（若有）與原始碼目錄中找靜態檔，並阻擋路徑跳脫。"""
    for root in (FRONTEND_DIST, FRONTEND_DIR):
        root_resolved = root.resolve()
        candidate = (root / full_path).resolve()
        if root_resolved != candidate and root_resolved not in candidate.parents:
            continue
        if candidate.is_file():
            return candidate
    return None


app = FastAPI(title="社區小尖兵 AI Agent")

if CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

if not SESSION_SECRET:
    _session_secret = secrets.token_urlsafe(48)
    print("[auth] SESSION_SECRET 未設定；使用暫時性密鑰，重啟後登入狀態會失效。", flush=True)
else:
    _session_secret = SESSION_SECRET

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    session_cookie=SESSION_COOKIE_NAME,
    max_age=SESSION_MAX_AGE,
    same_site=SESSION_COOKIE_SAMESITE,
    https_only=SESSION_COOKIE_SECURE,
)

if line_login_configured():
    print(f"[auth] LINE Login enabled: {LINE_LOGIN_REDIRECT_URI}", flush=True)
else:
    print(
        "[auth] LINE Login disabled: set LINE_LOGIN_CHANNEL_ID, "
        "LINE_LOGIN_CHANNEL_SECRET, LINE_LOGIN_REDIRECT_URI, and SESSION_SECRET.",
        flush=True,
    )


class AnalyzeRequest(BaseModel):
    images: list[str] = []


class CreateCaseRequest(BaseModel):
    description: str
    category_id: int
    images: list[str] | None = None
    address: str | None = None
    author_account: str | None = None


class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    # 新前端每次送出完整對話歷史（role/content）。有帶就以它為上下文，
    # 不依賴 thread_id，避免不同使用者共用伺服器端記憶。
    messages: list[ChatMessage] | None = None


_chat_agent = None


def _get_chat_agent():
    """共用同一個 Agent（MemorySaver 保留在程序中），聊天才有跨輪記憶。"""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = build_agent()
    return _chat_agent


def _last_ai_text(messages) -> str:
    for m in reversed(messages):
        if getattr(m, "type", "") != "ai":
            continue
        content = m.content
        if isinstance(content, list):
            return "".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        return str(content or "").strip()
    return ""


def _turn_reply(messages) -> str:
    """本輪 supervisor 可能派了多位專家，把他們的回報依序合併成一段回覆。"""
    reports: list[str] = []
    for m in reversed(messages):
        if getattr(m, "type", "") == "human":
            break
        if getattr(m, "type", "") == "ai" and getattr(m, "name", None):
            text = str(m.content or "").strip()
            if text:
                reports.append(text)
    reports.reverse()
    if not reports:
        return _last_ai_text(messages)
    return "\n\n---\n\n".join(reports)


def _chat_history(req: ChatRequest) -> list:
    """把前端送來的 messages 轉成 LangChain 訊息；沒有歷史時就是單題。"""
    text = req.message.strip()
    history = []
    for item in req.messages or []:
        content = (item.content or "").strip()
        if not content:
            continue
        role = (item.role or "").strip().lower()
        if role in {"assistant", "ai", "model"}:
            history.append(AIMessage(content=content))
        else:
            history.append(HumanMessage(content=content))
    # 前端已把本輪訊息放在最後；若沒有（或內容不同）才補上，避免重複問一次。
    if (
        not history
        or not isinstance(history[-1], HumanMessage)
        or history[-1].content.strip() != text
    ):
        history.append(HumanMessage(content=text))
    return history


def _chat_config(req: ChatRequest) -> dict:
    """有帶完整歷史時用一次性 thread，避免跨請求／跨使用者共用記憶。"""
    if req.thread_id:
        thread_id = req.thread_id
    elif req.messages:
        thread_id = f"web_{uuid.uuid4().hex}"
    else:
        thread_id = "web_session_01"
    return {"configurable": {"thread_id": thread_id}}


def current_user(request: Request) -> dict:
    account = request.session.get("account")
    if not account:
        raise HTTPException(status_code=401, detail="請先登入。")
    try:
        user = get_user_by_account(str(account))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="登入驗證暫時無法使用。") from exc
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="登入已失效，請重新登入。")
    role = resolve_session_role(request.session.get("role"), user.is_staff)
    return {
        "account": user.account,
        "name": user.name,
        "role": role,
        "is_staff": user.is_staff,
    }


@app.get("/api/auth/line/login")
def line_login(
    request: Request,
    role: str = Query(default="resident", pattern="^(resident|staff)$"),
):
    if not line_login_configured():
        raise HTTPException(status_code=503, detail="LINE 登入尚未設定。")
    state = generate_state()
    code_verifier, code_challenge = generate_pkce_pair()
    request.session.clear()
    request.session["oauth_state"] = state
    request.session["oauth_role"] = role
    request.session["oauth_started_at"] = int(time.time())
    request.session["oauth_code_verifier"] = code_verifier
    return RedirectResponse(
        build_authorize_url(state, code_challenge),
        status_code=302,
    )


@app.get("/api/auth/line/callback")
def line_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    expected_state = request.session.pop("oauth_state", None)
    requested_role = request.session.pop("oauth_role", "resident")
    started_at = request.session.pop("oauth_started_at", 0)
    code_verifier = request.session.pop("oauth_code_verifier", None)

    if error:
        return RedirectResponse(failure_redirect("line_error"), status_code=302)
    if not line_login_configured():
        return RedirectResponse(failure_redirect("not_configured"), status_code=302)
    if (
        not code
        or not state
        or not expected_state
        or not secrets.compare_digest(str(state), str(expected_state))
    ):
        return RedirectResponse(failure_redirect("invalid_state"), status_code=302)

    try:
        elapsed = int(time.time()) - int(started_at or 0)
    except (TypeError, ValueError):
        elapsed = LINE_LOGIN_STATE_TTL + 1
    if elapsed < 0 or elapsed > LINE_LOGIN_STATE_TTL:
        return RedirectResponse(failure_redirect("state_expired"), status_code=302)

    if requested_role not in {"resident", "staff"}:
        requested_role = "resident"

    try:
        tokens = exchange_code(code, code_verifier)
        access_token = tokens.get("access_token")
        if not access_token:
            raise LineLoginError("missing_access_token")
        profile = fetch_profile(str(access_token))
        user = find_or_create_user(
            str(profile["userId"]),
            str(profile.get("displayName") or ""),
        )
    except (LineLoginError, SQLAlchemyError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        print(f"[auth] LINE 登入失敗: {type(exc).__name__}", flush=True)
        return RedirectResponse(failure_redirect("line_error"), status_code=302)

    if requested_role == "staff" and not user.is_staff:
        return RedirectResponse(failure_redirect("not_staff"), status_code=302)

    session_role = "staff" if requested_role == "staff" and user.is_staff else "resident"
    request.session.clear()
    request.session["account"] = user.account
    request.session["name"] = user.name
    request.session["role"] = session_role
    request.session["authenticated_at"] = int(time.time())
    return RedirectResponse(success_redirect(session_role), status_code=302)


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(current_user)):
    return {
        "account": user["account"],
        "name": user["name"],
        "role": user["role"],
        "is_staff": user["is_staff"],
    }


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return {"ok": True}


# 專家節點開始跑之前就先把進度講出來，不用等整段回覆生成完。
_EXPERT_STATUS = {
    DB_EXPERT: "正在查資料庫…",
    RESEARCHER: "正在搜尋外部資料…",
}
# 串流幀的最短間隔：一個中文字一個 SSE 事件太碎，前端重繪也划不來。
_STREAM_FLUSH_SECONDS = 0.08


def _sse(event: str, **data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/runtime-config.js", include_in_schema=False)
def runtime_config():
    """提供新前端 api/runtime-config.js 的內容。

    frontend 原本靠 PowerShell 腳本產生這個檔；由後端同源服務時直接動態回傳，
    前端不需要改程式碼，也不需要另外執行腳本。
    """
    config = {
        "apiBaseUrl": "/api",
        "mockAuthorAccount": FRONTEND_MOCK_AUTHOR_ACCOUNT,
        "lineLoginPath": LINE_LOGIN_PATH if line_login_configured() else "",
        "googleMapsApiKey": GOOGLE_MAPS_BROWSER_API_KEY,
        "allowDesktopReportPreview": FRONTEND_ALLOW_DESKTOP_REPORT_PREVIEW,
    }
    body = "window.CommunityConfig = Object.freeze(" + json.dumps(
        config, ensure_ascii=False
    ) + ");\n"
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/categories")
def get_categories():
    try:
        return list_categories()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"資料庫查詢失敗: {e}")


@app.post("/api/ai-analyze")
def ai_analyze(req: AnalyzeRequest):
    if not req.images:
        raise HTTPException(status_code=400, detail="至少需要一張照片，AI 才能分析。")
    try:
        return analyze_images(req.images)
    except ImageMetadataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 分析失敗: {e}")


@app.post("/api/chat")
def chat(req: ChatRequest):
    """跟 main.py 同一個 LangGraph Agent 對話，thread_id 相同就能多輪記憶。"""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="請輸入訊息。")
    try:
        result = _get_chat_agent().invoke(
            {"messages": _chat_history(req)},
            config=_chat_config(req),
        )
        reply = _turn_reply(result["messages"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 回覆失敗: {e}")
    if not reply:
        raise HTTPException(status_code=500, detail="AI 沒有回覆內容，請再試一次。")
    return {"reply": reply}


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """跟 /api/chat 同一個 Agent，但用 SSE 送「進度 + 正文 token」。

    Supervisor 一次問題會呼叫模型多次（路由 → 專家 → 路由），整段跑完要十幾秒；
    光有進度事件不夠，因為最慢的一段（生答案的十幾秒）完全包在一個節點裡面。
    這裡同時送兩種事件：status（節點邊界）與 delta（專家正文逐字），
    token 由 app/agent/graph.py 的專家節點用 stream() 取，再用自訂事件往外轉。
    """
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="請輸入訊息。")

    agent = _get_chat_agent()
    config = _chat_config(req)
    chat_input = {"messages": _chat_history(req)}

    def events():
        yield _sse("status", text="正在思考…")
        # token 一個中文字一個事件太碎，累積到一定長度或一定時間再送一幀。
        pending, last_flush = "", time.monotonic()
        try:
            for mode, item in agent.stream(
                chat_input,
                config=config,
                stream_mode=["updates", "custom"],
            ):
                now = time.monotonic()
                if mode == "custom":
                    if item.get("status"):
                        if pending:                      # 順序不能顛倒，先把已累積的字送出去
                            yield _sse("delta", expert="", text=pending)
                            pending, last_flush = "", now
                        yield _sse("status", text=item["status"])
                    elif item.get("reset"):
                        yield _sse("reset", expert=item.get("expert", ""))
                    elif item.get("text"):
                        pending += item["text"]
                    if not pending or now - last_flush < _STREAM_FLUSH_SECONDS:
                        continue
                    yield _sse("delta", expert=item.get("expert", ""), text=pending)
                    pending, last_flush = "", now
                    continue
                for node, patch in (item or {}).items():
                    if node == "supervisor":
                        upcoming = (patch or {}).get("next")
                        if upcoming in _EXPERT_STATUS:
                            yield _sse("status", text=_EXPERT_STATUS[upcoming])
                    elif node in MEMBERS:
                        yield _sse("status", text="正在整理回覆…")
            if pending:
                yield _sse("delta", expert="", text=pending)
            messages = agent.get_state(config).values.get("messages", [])
            reply = _turn_reply(messages)
        except Exception as e:
            if pending:
                yield _sse("delta", expert="", text=pending)
            yield _sse("error", message=f"AI 回覆失敗: {e}")
            return
        if not reply:
            yield _sse("error", message="AI 沒有回覆內容，請再試一次。")
            return
        yield _sse("done", reply=reply)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # X-Accel-Buffering: nginx 預設會緩衝 SSE，沒這行就又變成一次整段送出。
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...), language: str = Form("zh")
):
    """把瀏覽器錄音轉給語音模型，避免前端直接連 HTTP 服務造成混合內容問題。"""
    if not TRANSCRIPTION_API_URL:
        raise HTTPException(status_code=503, detail="尚未設定 TRANSCRIPTION_API_URL。")
    content_type = file.content_type or ""
    allowed = content_type.startswith(("audio/", "video/")) or content_type in {"", "application/octet-stream"}
    if not allowed:
        raise HTTPException(status_code=400, detail="請上傳音訊或影片檔案。")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="錄音內容是空的，請重新錄製。")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="錄音檔超過 20 MB，請縮短錄音。")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                TRANSCRIPTION_API_URL,
                files={
                    "file": (
                        file.filename or "recording.webm",
                        data,
                        content_type or "application/octet-stream",
                    )
                },
                data={"language": language or "zh"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"語音轉文字服務無法連線: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"語音轉文字服務回傳 HTTP {response.status_code}。",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="語音轉文字服務回傳無法解析的資料。") from exc
    text = payload.get("text") if isinstance(payload, dict) else ""
    return {
        "text": text.strip() if isinstance(text, str) else "",
        "language": payload.get("language") if isinstance(payload, dict) else language,
        "segments": payload.get("segments", []) if isinstance(payload, dict) else [],
    }


@app.post("/api/uploads")
async def upload_images(
    files: list[UploadFile] = File(...),
    _user: dict = Depends(current_user),
):
    """存到 GCS（或本機模擬），回傳物件路徑陣列。檔名由後端決定。"""
    if not files:
        raise HTTPException(status_code=400, detail="沒有收到照片。")
    paths = []
    try:
        for f in files:
            data = await f.read()
            paths.append(save_upload(data, f.filename or "", f.content_type))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"圖片上傳失敗: {e}")
    return {"paths": paths}


@app.post("/api/cases")
def create_case_endpoint(req: CreateCaseRequest, user: dict = Depends(current_user)):
    if not req.description.strip() or len(req.description.strip()) < 10:
        raise HTTPException(status_code=400, detail="描述至少要 10 個字。")
    if req.category_id <= 0:
        raise HTTPException(status_code=400, detail="請選擇有效類別。")
    if req.images and len(req.images) > 5:
        raise HTTPException(status_code=400, detail="最多 5 張照片。")
    try:
        return create_case(
            description=req.description.strip(),
            category_id=req.category_id,
            images=req.images,
            address=req.address.strip() if req.address else None,
            author_account=user["account"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"建立案件失敗: {e}")


@app.get("/api/cases")
def get_my_cases(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(current_user),
):
    try:
        return list_cases_by_account(user["account"], limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"案件查詢失敗: {e}")


@app.get("/api/events")
def get_events(
    time: str = Query(default="month", pattern="^(today|week|month|all)$"),
    event_type: str | None = Query(default=None, alias="type"),
    status: str | None = None,
    region: str | None = None,
    filter_region: str | None = Query(default=None, alias="filterRegion"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """列出社區通報事件，回傳前端 Event 清單格式。"""
    try:
        return list_events(
            time_filter=time,
            event_type=event_type,
            status=status,
            region=region,
            filter_region=filter_region,
            limit=limit,
            offset=offset,
        )
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"事件查詢失敗: {e}")


@app.get("/api/places")
def get_places(q: str = Query(default="")):
    """以文字搜尋台灣地點，供申報位置挑選使用。"""
    if len(q) > 200:
        raise HTTPException(status_code=422, detail="地點搜尋文字不可超過 200 個字。")
    try:
        return search_places(q)
    except PlacesProviderError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@app.get("/api/places/reverse")
def get_place_address(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
):
    """將地圖座標轉成地址文字。"""
    try:
        return {"address": reverse_geocode(lat, lng)}
    except PlacesProviderError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/events/{event_id}")
def get_event_detail(event_id: str):
    """取得一筆社區事件；未知或已拒絕案件回傳 null。"""
    try:
        return get_event(event_id)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"事件查詢失敗: {e}")


@app.get("/api/welfare")
def get_welfare(
    event_type: str | None = Query(default=None, alias="type"),
    target: str | None = None,
    time: str | None = Query(default=None, pattern="^(today|week|month|all)$"),
    region: str | None = None,
):
    """搜尋中央／地方政府及社區發布的福利與活動資訊。"""
    try:
        return search_welfare(
            event_type=event_type,
            target=target,
            time=time,
            region=region,
        )
    except WelfareSearchError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@app.get("/api/weather")
def get_current_weather(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
):
    """依瀏覽器提供的 GPS 座標查詢 Open-Meteo 目前天氣。"""
    try:
        return get_weather(lat, lng)
    except WeatherProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))


LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=LOCAL_UPLOAD_DIR), name="uploads")


@app.get("/")
def index():
    """根路徑直接服務 frontend 新前端。"""
    root = _frontend_root()
    if root is not None:
        return FileResponse(root / FRONTEND_INDEX)
    return JSONResponse(
        {"detail": "前端尚未設定：找不到 frontend/index.html。"},
        status_code=404,
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """前端路由 fallback：認得的靜態檔直接回，其餘回 index.html。

    註冊在所有 route / mount 之後（/api、/uploads），才不會蓋掉後端路由。
    frontend 不在時回 404，後端仍可單獨啟動。
    """
    if full_path == "api" or full_path.startswith("api/"):
        # frontend 的 api/community-api.js 等前端檔案也掛在 /api 底下；
        # 先讓實際存在的靜態檔通過，其餘才當成不存在的 API。
        shared = _frontend_file(full_path)
        if shared is not None:
            return FileResponse(shared)
        return JSONResponse({"detail": "API endpoint not found"}, status_code=404)
    root = _frontend_root()
    if root is None:
        return JSONResponse(
            {"detail": "前端尚未設定：找不到 frontend/index.html。"},
            status_code=404,
        )

    candidate = _frontend_file(full_path)
    if candidate is not None:
        return FileResponse(candidate)

    # 有副檔名的資源（js/css/圖片）找不到就回 404，不要拿 index.html 冒充，
    # 否則瀏覽器會把 HTML 當成 JS/CSS 載入。
    if Path(full_path).suffix:
        return JSONResponse({"detail": "找不到檔案。"}, status_code=404)
    return FileResponse(root / FRONTEND_INDEX)
