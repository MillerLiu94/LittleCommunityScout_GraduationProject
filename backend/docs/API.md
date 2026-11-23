# 社區小尖兵 — 網頁 API 文件

本文件列出目前後端已實作、可供前端或 Postman 呼叫的 API。
後端為 FastAPI，入口在 `app/server.py`。

## 共通資訊

| 項目 | 值 |
|------|-----|
| Base URL | `https://cachyos-x8664.tail3babf5.ts.net`（Tailscale 服務位址）。前端用相對路徑 `/api` |
| 格式 | request body 一律 `application/json`（上傳除外），回傳 `application/json` |
| 錯誤格式 | 一般 HTTP 錯誤為 `{ "detail": "<錯誤訊息>" }`；`/api/chat/stream` 開始串流後的錯誤則以 SSE `error` 事件回傳 |
| CORS | 同源服務時不需要；若設定 `CORS_ALLOW_ORIGINS`，會使用明確 origin 並允許 credentials |
| 啟動 | 在 `backend/` 執行 `python server.py`；若找到 Tailscale 憑證或設定 `SSL_CERTFILE`、`SSL_KEYFILE`，會使用 HTTPS，否則使用 HTTP |

## 端點總覽

| Method | Path | 說明 | 網頁來源 |
|--------|------|------|----------|
| GET | `/api/auth/line/login?role=` | 啟動 LINE Login OAuth | 登入頁「登入」按鈕 |
| GET | `/api/auth/line/callback` | LINE OAuth callback（由 LINE 導回） | — |
| GET | `/api/auth/me` | 讀取目前登入者 | 前端確認登入狀態 |
| POST | `/api/auth/logout` | 登出並清除 session | 登出按鈕 |
| GET | `/api/categories` | 讀取通報類別字典表 | 類別選單 |
| POST | `/api/ai-analyze` | AI 分析照片，回傳類別＋描述 | 「用 AI 分析並帶入表單」按鈕 |
| POST | `/api/uploads` | 上傳照片（multipart；需登入） | 照片選取後送出 |
| POST | `/api/cases` | 建立通報案件（需登入） | 表單送出 |
| GET | `/api/cases` | 查詢目前登入者的案件（需登入） | 「我的通報」清單 |
| GET | `/api/events`、`/api/events/{event_id}` | 社區通報事件列表與詳情 | 首頁最新事件、事件列表 |
| GET | `/api/welfare` | 搜尋政府／社區福利與活動（Tavily） | 首頁福利活動、福利搜尋 |
| GET | `/api/weather?lat=&lng=` | 依 GPS 座標查詢目前天氣（Open-Meteo） | 首頁位置／天氣卡 |
| GET | `/api/places?q=` | 搜尋台灣地點（Google Places API） | 申報地點搜尋 |
| GET | `/api/places/reverse?lat=&lng=` | 座標反查地址（Google Geocoding API） | GPS／地圖位置確認 |
| POST | `/api/chat` | 社區小尖兵 AI 聊天（Supervisor 多智能體，與 `main.py` 同一個 Agent） | — |
| POST | `/api/chat/stream` | 同上，但以 SSE 逐步送進度事件 | 右下角浮動對話框 |
| GET | `/api/runtime-config.js` | 提供新前端（frontend）執行期設定 | 所有頁面載入時 |
| POST | `/api/transcribe` | 瀏覽器錄音轉文字（proxy 到語音模型） | 申報回顧頁麥克風按鈕 |

登入改用 LINE Login OAuth。`/api/auth/line/login` 會以瀏覽器導向 LINE；callback 成功後由後端建立 HttpOnly session cookie，再導回前端登入頁。`POST /api/cases`、`GET /api/cases`、`POST /api/uploads` 需要有效的登入 session，未登入會回 `401`。

## Postman 與 cURL

每個端點下方的 `curl` 範例都可以直接匯入 Postman：

1. 在 Postman 選 **Import → Raw text**，貼上一個端點的完整 `curl` 指令後匯入。
2. 本機 URL 依啟動時是否載入憑證使用 `https://cachyos-x8664.tail3babf5.ts.net` 或 `https://cachyos-x8664.tail3babf5.ts.net`；目前環境使用 HTTPS。若使用其他主機，換成該主機的 Base URL。
3. 若伺服器使用 HTTPS 憑證但 Postman 顯示憑證錯誤，可在 Postman 設定中暫時關閉 **SSL certificate verification**。`curl` 範例遇到自簽憑證時則加上 `-k`。

> 若出現 `Could not send request` / `socket hang up`，請先確認 URL 的協定與伺服器一致。目前此環境的後端使用 HTTPS，因此請用 `https://cachyos-x8664.tail3babf5.ts.net/api/...`；以 `http://` 呼叫會因協定不符而無法取得回應。

Postman 也可建立環境變數 `baseUrl`（例如 `https://cachyos-x8664.tail3babf5.ts.net`），再把各請求 URL 改成 `{{baseUrl}}/api/...`。`/api/cases` 與 `/api/uploads` 需要登入 session cookie；其餘公開 API 不需 Authorization header。`/api/uploads` 使用 `multipart/form-data`，其餘 POST 範例使用 JSON。`/api/chat/stream` 回傳 SSE 串流，測試時請保留範例中的 `Accept: text/event-stream`。

---

## 1. GET /api/categories

讀取申報類別字典表（對應資料庫 `categories` 表）。

- **網頁對應**：新前端由 `/api/ai-analyze` 帶入類別；此端點保留給其他客戶端使用
- **後端**：`app/server.py` → `app/analyze.py:list_categories()`

**回傳 200**：類別陣列

```json
[
  { "categories_id": 1, "key_name": "road_damage",     "label": "路面損壞",     "color_code": "#FFA500" },
  { "categories_id": 2, "key_name": "street_light",    "label": "路燈故障",     "color_code": "#F59E0B" },
  { "categories_id": 3, "key_name": "waterlogging",    "label": "積水",         "color_code": "#3B82F6" },
  { "categories_id": 4, "key_name": "garbage",         "label": "垃圾",         "color_code": "#10B981" },
  { "categories_id": 5, "key_name": "illegal_dump",    "label": "違規堆放",     "color_code": "#8B5CF6" },
  { "categories_id": 6, "key_name": "facility_damage", "label": "公共設施損壞", "color_code": "#EC4899" },
  { "categories_id": 7, "key_name": "fallen_tree",     "label": "樹木倒塌",     "color_code": "#84CC16" },
  { "categories_id": 8, "key_name": "other",           "label": "其他",         "color_code": "#6B7280" }
]
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `categories_id` | int | 類別主鍵（寫案件時用這個） |
| `key_name` | string | 類別英文代號（AI 分析回傳這種） |
| `label` | string | 中文標籤 |
| `color_code` | string | 前端顯示用的顏色 |

**錯誤**：`500 { "detail": "資料庫查詢失敗: ..." }`

```bash
curl -k https://cachyos-x8664.tail3babf5.ts.net/api/categories
```

---

## 2. POST /api/ai-analyze

把照片交給後端 Ollama 視覺模型，自動選類別＋寫描述。

- **網頁對應**：`apiAnalyze()`（🔌 1b）、「用 AI 分析並帶入表單」
- **後端**：`app/server.py` → `app/analyze.py:analyze_images()`

**Request**（JSON）

```json
{
  "images": [
    "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
  ]
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `images` | string[] | base64 的 data URI，至少 1 張 |

**回傳 200**：

```json
{
  "category_id": 2,
  "key_name": "street_light",
  "label": "路燈故障",
  "description": "夜間路燈燈頭未亮，疑似路燈故障",
  "location": {
    "lat": 25.0455,
    "lng": 121.509,
    "source": "exif",
    "image_index": 0
  }
}
```

`location` 是第一張含 GPS EXIF 的照片座標；`image_index` 從 0 開始。沒有 GPS metadata 時為 `null`，不會根據照片內容猜測位置。前端會把座標帶到地圖供使用者確認／調整。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `category_id` | int | 對應 `categories.categories_id` |
| `key_name` | string | 對應 `categories.key_name` |
| `label` | string | 中文類別名 |
| `description` | string | 一句話具體描述 |
| `location` | object \| null | 照片 EXIF GPS 位置；無 GPS 時為 `null` |

> 例外：若 AI 無法解析回覆，會回 **200** 但內容是 `{ "error": "AI 無法解析回覆，請再試一次。", "raw": "..." }`。

**錯誤**：
- `400 { "detail": "至少需要一張照片，AI 才能分析。" }`
- `400 { "detail": "無法讀取照片，請確認檔案是有效的圖片。" }`（照片格式錯誤或不是有效圖片）
- `500 { "detail": "AI 分析失敗: ..." }`

> 範例中的 `AAAA` 僅是佔位內容，實際呼叫時需換成照片的 base64 data URI（例如 `data:image/jpeg;base64,<照片的base64內容>`）。

```bash
curl -k -X POST https://cachyos-x8664.tail3babf5.ts.net/api/ai-analyze \
  -H 'Content-Type: application/json' \
  -d '{"images": ["data:image/png;base64,AAAA"]}'
```

---

## 3. POST /api/uploads

上傳照片，回傳物件路徑陣列（檔名由後端決定）。

- **網頁對應**：`apiUploadImages()`（🔌 2）
- **後端**：`app/server.py` → `app/storage.py:save_upload()`
- **儲存**：`.env` 的 `STORAGE_BACKEND` — `gcs` 存到 GCS bucket `my-report-image`；`local` 暫存本機 `data/uploads/`。GCS 失敗會自動退回本機。

**Request**（`multipart/form-data`，欄位名 `files`，可重複多個檔案）

```
files=@20260921路燈.jpg;type=image/jpeg
```

在 Postman 的 **Body → form-data** 將 key 設為 `files`、類型選 **File** 並選擇照片；多張照片可重複新增 `files` 欄位。不要自行填 `Content-Type`，讓 Postman 自動產生 multipart boundary。

**回傳 200**：

```json
{
  "paths": [
    "uploads/202609/4a16b777b5494731b017495e3f6b0288.png"
  ]
}
```

`paths` 為物件路徑陣列，會原封不動寫進案件的 `images` 欄位。

**錯誤**：
- `400 { "detail": "沒有收到照片。" }`
- `500 { "detail": "圖片上傳失敗: ..." }`（例如 GCS 連線失敗又無法退本機）

```bash
curl -k -X POST https://cachyos-x8664.tail3babf5.ts.net/api/uploads -F "files=@photo.jpg"
```

---

## 4. POST /api/cases

建立通報案件（需登入；`cases_id`、`created_at`、`status` 都由後端產生；`address` 未提供時寫空字串）。`author_account` 由後端 session 決定，client 傳來的值會被忽略。

- **網頁對應**：`apiCreateCase()`（🔌 3）、「送出通報」
- **後端**：`app/server.py` → `app/cases.py:create_case()`

**Request**（JSON）

```json
{
  "description": "夜間路燈燈頭未亮，疑似路燈故障",
  "category_id": 2,
  "images": ["uploads/202609/f3af886b21de4cffb36df6b44e3dba65.jpg"],
  "address": "23.57454, 119.58092"
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `description` | string | ✅ | 問題描述，至少 10 個字 |
| `category_id` | int | ✅ | 見 `/api/categories`，需 > 0 |
| `images` | string[] | 否 | `/api/uploads` 回傳的物件路徑，最多 5 張 |
| `address` | string | 否 | 地址或坐標（`23.57454, 119.58092`） |
| `author_account` | string | 否 | 已忽略；後端一律使用登入 session 的帳號 |

**回傳 200**（完整案件，`created_at` 為 13 位毫秒）：

```json
{
  "cases_id": 17899204544044,
  "description": "夜間路燈燈頭未亮，疑似路燈故障",
  "category_id": 2,
  "images": ["uploads/202609/f3af886b21de4cffb36df6b44e3dba65.jpg"],
  "status": "pending",
  "created_at": 1789920454404,
  "author_account": "U1234567890abcdef1234567890abcdef",
  "address": "23.57454, 119.58092",
  "reject_reason": "無"
}
```

> 注意：`created_at` 換算日期要用 `created_at / 1000.0`（毫秒），不是直接當秒。

**錯誤**：
- `401 { "detail": "請先登入。" }`（沒有有效 session）
- `400 描述至少要 10 個字。`
- `請選擇有效類別。`
- `最多 5 張照片。`
- `建立案件失敗: ...`（例如 FK 不存在、資料庫錯誤）

```bash
curl -k -X POST https://cachyos-x8664.tail3babf5.ts.net/api/cases \
  -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"description":"巷口路燈已三天沒亮巷口路燈已三天沒亮","category_id":2,"images":[],"address":"中正路 12 巷"}'
```

---

## 5. GET /api/cases

查詢目前登入者的通報案件（需登入）。

- **網頁對應**：`apiGetMyCases()`（🔌 4）、「我的通報」
- **後端**：`app/server.py` → `app/cases.py:list_cases_by_account()`
- **SQL**：`LEFT JOIN categories` 取得 `category_label`；`WHERE c.author_account = :account ORDER BY c.created_at DESC LIMIT :limit OFFSET :offset`（`:account` 來自 session）

**Query 參數**

| 名稱 | 必填 | 預設 | 說明 |
|------|------|------|------|
| `limit` | 否 | `50` | 每頁筆數，範圍 1–100 |
| `offset` | 否 | `0` | 分頁起始筆數 |

client 舊版可能仍帶 `author_account`，後端會忽略。

**回傳 200**：案件陣列（每筆結構同「建立案件」的回傳，另含 `category_label`）

```json
[
  {
    "cases_id": 17899204544044,
    "description": "夜間路燈燈頭未亮，疑似路燈故障",
    "category_id": 2,
    "category_label": "路燈",
    "images": ["uploads/202609/f3af886b21de4cffb36df6b44e3dba65.jpg"],
    "image_urls": ["/uploads/202609/f3af886b21de4cffb36df6b44e3dba65.jpg"],
    "status": "pending",
    "created_at": 1789920454404,
    "author_account": "U1234567890abcdef1234567890abcdef",
    "address": "23.57454, 119.58092",
    "reject_reason": "無"
  }
]
```

**錯誤**：`401 { "detail": "請先登入。" }` 或 `500 { "detail": "案件查詢失敗: ..." }`

```bash
curl -k -b cookies.txt 'https://cachyos-x8664.tail3babf5.ts.net/api/cases?limit=5&offset=0'
```

---

## 5.5 GET /api/runtime-config.js

新前端（`frontend/`）在每個頁面載入 `api/runtime-config.js`。由後端同源服務時，這個端點會動態產生該檔，前端不需要修改程式碼，也不必執行原本的 PowerShell 產生腳本。

- **後端**：`app/server.py:runtime_config()`
- **回傳**：`application/javascript`

```js
window.CommunityConfig = Object.freeze({
  apiBaseUrl: "/api",
  mockAuthorAccount: "test1",
  lineLoginPath: "/auth/line/login",
  googleMapsApiKey: "",
  allowDesktopReportPreview: false
});
```

| 設定 | 來源環境變數 | 說明 |
|------|--------------|------|
| `apiBaseUrl` | 固定 `/api` | 前端一律走同源 API |
| `mockAuthorAccount` | `MOCK_AUTHOR_ACCOUNT` | 舊版 mock 帳號；登入後案件一律使用 session 帳號 |
| `lineLoginPath` | `LINE_LOGIN_PATH` | 前端登入入口（前端會再加 `/api`）；LINE 未設定時為空字串 |
| `googleMapsApiKey` | `GOOGLE_MAPS_BROWSER_API_KEY` | 瀏覽器地圖金鑰；留空時地圖降級 |
| `allowDesktopReportPreview` | `FRONTEND_ALLOW_DESKTOP_REPORT_PREVIEW` | 設為 `1`／`true` 可解除桌機申報限制 |

```bash
curl -k https://cachyos-x8664.tail3babf5.ts.net/api/runtime-config.js
```

---

## 5.6 LINE Login

登入使用 LINE Login（OAuth 2.0 + PKCE）。後端在 callback 成功後建立 HttpOnly session cookie，前端不需要保存 access token。

**必要環境變數**（`backend/.env`）

| 變數 | 說明 |
|------|------|
| `LINE_LOGIN_CHANNEL_ID` | LINE Login channel 的 Channel ID |
| `LINE_LOGIN_CHANNEL_SECRET` | LINE Login channel 的 Channel secret |
| `LINE_LOGIN_REDIRECT_URI` | 必須與 LINE Developers Console 的 Callback URL 完全一致 |
| `SESSION_SECRET` | 簽署 session cookie／OAuth state；未設定時登入停用 |

其他選填：`LINE_LOGIN_PATH`、`LINE_LOGIN_SCOPE`、`LINE_LOGIN_STATE_TTL`、`LINE_LOGIN_BOT_PROMPT`、`FRONTEND_BASE_URL`、`LINE_LOGIN_SUCCESS_PATH`、`LINE_LOGIN_FAILURE_PATH`、`SESSION_COOKIE_NAME`、`SESSION_MAX_AGE`、`SESSION_COOKIE_SECURE`、`SESSION_COOKIE_SAMESITE`、`CORS_ALLOW_ORIGINS`。

### GET /api/auth/line/login

- Query：`role=resident|staff`（前端提示用，不會直接授予 staff 權限）
- 回應：`302` 導向 LINE 授權頁；若 LINE 設定不完整則回 `503`。

### GET /api/auth/line/callback

- LINE 導回後驗證 `state`、交換 token、取得 LINE profile。
- 以 LINE userId 直接對應 `users.account`；第一次登入會建立 resident 帳號。
- 成功：`302` 導回 `FRONTEND_BASE_URL + LINE_LOGIN_SUCCESS_PATH`，並附上實際 `role`。
- 失敗：`302` 導回 `LINE_LOGIN_FAILURE_PATH`，附上 `reason`。
- 選 staff 但 `is_staff=false` 會拒絕登入。

### GET /api/auth/me

- 有 session：`200 { "account": "...", "name": "...", "role": "resident|staff", "is_staff": false }`
- 沒有 session：`401 { "detail": "請先登入。" }`

### POST /api/auth/logout

- 清除 session cookie，回 `200 { "ok": true }`。

> 工作人員必須在 `users` 表預先將對應 LINE userId 的 `account` 設為 `is_staff=true`。`role=staff` 只是前端選項，不是授權依據。
>
> 請用 HTTPS 網址（例如 Tailscale 的 `https://cachyos-x8664.tail3babf5.ts.net`）登入；直接開 `http://127.0.0.1:8000` 時 `Secure` cookie 不會保存，callback 會失敗。LINE Developers Console 的 Callback URL 必須與 `LINE_LOGIN_REDIRECT_URI` 完全一致。

---

## 6. POST /api/chat

社區小尖兵 AI 聊天。就是 `main.py` 的那個 LangGraph Agent，搬到網頁上。同一個 `thread_id` 的多輪問題會串接對話記憶（存在伺服器程序中）。

架構是 **Supervisor 多智能體**（`app/agent/graph.py`）：`supervisor` 節點不動手查資料，只決定要喚醒哪位專家；專家做完回報，`supervisor` 再決定下一步，全部完成才 `FINISH` 結束。

| 節點 | 工具 | 負責 |
|------|------|------|
| `supervisor` | 無 | 只做路由，輸出 `plan`（本輪需要哪些專家）與 `next`（下一位） |
| `DB_Expert` | `query_community_database` | 以唯讀連線查 `cases` / `categories`（沒有 `users` 權限） |
| `Researcher` | `tavily_tool` | Tavily 聯網搜尋外部即時資訊 |

> `DB_Expert` 與 `build_vision_agent()` 的資料庫工具使用 `READONLY_DATABASE_URL`（`readonly_user`），並在連線層強制 `default_transaction_read_only=on`、`statement_timeout`；未設定 `READONLY_DATABASE_URL` 時工具會停用，不會回退到可寫入的 `DATABASE_URL`。

路由規則：派工清單由程式端排隊（`plan` 內還沒回報的專家依序執行），單輪最多派 4 次防迴圈；一輪最多回報 2 位專家。
回覆內容是本輪所有專家回報的合併（多位專家以 `---` 分隔）。
`/api/ai-analyze` 的照片辨識走另一條路徑 `build_vision_agent()`（單一 react agent，會看到圖片），不經過 supervisor。

- **網頁對應**：右下角浮動「AI」按鈕 → `sendChat()`
- **後端**：`app/server.py`（網頁聊天實際走的是 `POST /api/chat/stream`，見第 7 節）

**Request**（JSON）

```json
{
  "message": "那要準備什麼資料？",
  "thread_id": "web_1789920981_a1b2c3",
  "messages": [
    { "role": "user", "content": "路燈壞了要怎麼通報？" },
    { "role": "assistant", "content": "可以從首頁的申報社區事件開始…" },
    { "role": "user", "content": "那要準備什麼資料？" }
  ]
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `message` | string | ✅ | 要問的問題（前後空白會被去除） |
| `thread_id` | string | 否 | 對話 id；相同就共用記憶，預設 `web_session_01` |
| `messages` | object[] | 否 | 完整對話歷史（`role`／`content`）。新前端每次都會帶；有帶時後端用它當上下文，並改用一次性 thread，不與其他使用者共用記憶 |

**回傳 200**：

```json
{
  "reply": "查到了！`test1` 帳號目前共有 3 件通報案件…"
}
```

**錯誤**：
- `400 { "detail": "請輸入訊息。" }`
- `500 { "detail": "AI 回覆失敗: ..." }`（Ollama/工具呼叫錯誤）
- `500 { "detail": "AI 沒有回覆內容，請再試一次。" }`

```bash
curl -k -X POST https://cachyos-x8664.tail3babf5.ts.net/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"路燈壞了要怎麼通報？","thread_id":"my_thread"}'
```

> 首次呼叫需載入 Ollama 模型，可能等幾秒到十幾秒。多輪對話務必沿用同一個 `thread_id`。

---

## 7. POST /api/chat/stream

跟 `/api/chat` 是同一個 Agent、同一組參數，差別在回應格式：**Server-Sent Events**，先送進度事件，再逐字送專家正文，最後補一次完整回覆。

Supervisor 一次問題會呼叫模型多次（路由 → 專家 → 路由），整段跑完常要 20 秒以上。若等到最後才回應，畫面就是一個「思考中」停住；只送節點進度也不夠，因為最慢的一段（生答案）完全包在單一節點裡面，所以正文也一起串流。

- **網頁對應**：`sendChat()` → `parseChatFrame()` / `chatHttpError()`
- **後端**：`app/server.py`

**Request**（JSON）：同 `/api/chat`

**回應**：`text/event-stream`，每個事件形如 `event: <名稱>\ndata: <JSON>\n\n`

| event | data | 觸發時機 |
|-------|------|----------|
| `status` | `{"text": "正在思考…"}` | 請求剛進來 |
| `status` | `{"text": "正在查資料庫…"}` / `"正在搜尋外部資料…"` | supervisor 決定派給哪位專家（依 `next` 欄位判斷） |
| `status` | 同上 | 專家決定要去呼叫工具（ReAct 決策期沒有任何可顯示的字） |
| `delta` | `{"expert": "Researcher", "text": "以下是路"}` | 專家正文逐字，每幀約 0.08 秒／10～15 字 |
| `status` | `{"text": "正在整理回覆…"}` | 專家回報完成，supervisor 收尾中 |
| `reset` | `{"expert": "DB_Expert"}` | 該專家第一輪回空字、準備重試，叫前端清掉已送出的半截 |
| `done` | `{"reply": "…markdown…"}` | 全部完成，回覆已合併（多位專家以 `---` 分隔） |
| `error` | `{"message": "AI 回覆失敗: …"}` | 節點或工具例外 |

`reply` 是權威答案，前端在 `done` 時用它覆蓋串流中已顯示的內容，因此中途過濾或重送都不會殘留錯字。

空白 `message` 仍在串流開始前就回 `400 { "detail": "請輸入訊息。" }`（非 SSE）。

回應頭另帶 `Cache-Control: no-cache` 與 `X-Accel-Buffering: no`：nginx 預設會緩衝 SSE，沒有後者會讓事件又變回一次整段送出。

```bash
curl -k -N -X POST https://cachyos-x8664.tail3babf5.ts.net/api/chat/stream \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{"message":"路燈壞了要怎麼通報？","thread_id":"my_thread"}'
```

前端因是 POST，不能用 `EventSource`，改用 `fetch` + `response.body.getReader()` 讀 `ReadableStream`，再以空行切 frame（frame 可能被切成兩次 chunk 讀到，要保留殘段）。收到 `delta` 就 append 文字，用 `requestAnimationFrame` 節流後重跑 `marked.parse`（每個字重解析一次會卡）。

### 為什麼要改專家節點

`app/agent/graph.py` 的專家節點原本呼叫 `agent.invoke()`。**同步 `invoke()` 不會向 Ollama 要求串流**，token 只會在整段跑完後一次湧出（實測 5 個 chunk 同時抵達）；改成 `agent.stream(..., stream_mode=["messages", "values"])` 才會逐字送出。`values` 用來取得 sub-graph 的最終 state，寫進記憶體的仍是權威訊息，串流只供前端顯示。

過濾規則：sub-graph 內部只有 `agent`（模型）與 `tools`（工具）兩種節點，只送 `agent` 的文字，工具的 JSON 回傳與 ReAct 決策期不顯示。

沒有串流監聽時（`main.py`、`/api/chat`）writer 會丟棄事件，行為與改動前相同。

---

## 8. GET /api/events 與 GET /api/events/{event_id}

首頁「最新社區事件」及事件列表使用此 API。資料取自通報案件資料表，回傳前端 `Event` 格式；不回傳通報者帳號。依需求，`pending`（待處理）案件也會顯示；已拒絕／撤回的案件不會列出。

**列表 query 參數**

| 名稱 | 必填 | 預設 | 說明 |
|------|------|------|------|
| `time` | 否 | `month` | `today`、`week`、`month`、`all` |
| `type` | 否 | — | 類別名稱，例如 `路燈` |
| `status` | 否 | — | `reported`、`in-progress`、`resolved` |
| `region` | 否 | — | 將地區相符的結果排前面，不剪除其他地區 |
| `filterRegion` | 否 | — | 僅保留地點／標題／類別包含此文字的結果 |
| `limit` | 否 | `50` | 每頁筆數，範圍 1–100；首頁可設為 5 |
| `offset` | 否 | `0` | 分頁起始筆數 |

列表以新到舊排序（如有 `region`，相符項目優先）；資料庫最多取最新 500 筆來源案件供篩選。

**回傳 200**：`Event[]`，單筆包含 `id`、`type`、`title`、`placeText`、`coordinates`、`timeText`、`status`、`description`、`photo`、`reportedAt` 等欄位。座標只會從案件地址中的 `lat, lng` 解析；一般文字地址的 `coordinates` 為 `null`。

```bash
curl -k 'https://cachyos-x8664.tail3babf5.ts.net/api/events?time=all&limit=5'
curl -k 'https://cachyos-x8664.tail3babf5.ts.net/api/events?time=month&region=%E4%B8%AD%E8%8F%AF%E8%B7%AF'
curl -k 'https://cachyos-x8664.tail3babf5.ts.net/api/events/17899204544044'
```

未知或已拒絕的 `event_id` 回傳 `200 null`；資料庫錯誤回傳 `500 { "detail": "事件查詢失敗: ..." }`。

---

## 9. GET /api/welfare

依地區與搜尋條件，透過 Tavily 搜尋政府（`gov.tw`）及社區組織（`org.tw`）公布的福利／活動資訊。

**Query 參數**

| 名稱 | 必填 | 說明 |
|------|------|------|
| `region` | 否 | 地區，例如 `臺北市中正區` |
| `type` | 否 | 活動或福利類型，例如 `課程`、`補助` |
| `target` | 否 | 對象，例如 `長者`、`親子` |
| `time` | 否 | `today`、`week`、`month`、`all` |

**回傳 200**：

```json
{
  "answer": "Tavily 產生的整體搜尋摘要",
  "results": [
    {
      "id": "以來源網址產生的識別碼",
      "title": "活動或福利標題",
      "headline": "從內容擷取、較直觀的摘要標題",
      "conditions": "主要申請條件（可能為空字串）",
      "benefits": "可獲得的補助或服務（可能為空字串）",
      "source": "example.gov.tw",
      "snippet": "補助對象、申請資格與申請方式摘要…",
      "publishedAt": "2026-10-01",
      "eventDate": "2026-10-20",
      "url": "https://example.gov.tw/activity"
    }
  ],
  "partial": false,
  "failedSources": []
}
```

`answer` 是 Tavily 依搜尋結果產生的整體摘要，可能為空字串。只回傳具備標題與來源網址的搜尋結果；`headline`、`conditions`、`benefits` 由頁面內容規則擷取，找不到時為空字串，前端會改用 `title`／`snippet`。`snippet` 是內容摘要，`publishedAt`、`eventDate` 若來源未提供則為 `null`，不會自行補造日期。沒有符合條件的資料時 `results` 為空陣列。需要在後端 `.env` 設定 `TAVILY_API_KEY`。未設定回 `503`；上游搜尋失敗回 `502`。

```bash
curl -k 'https://cachyos-x8664.tail3babf5.ts.net/api/welfare?region=%E8%87%BA%E5%8C%97%E5%B8%82%E4%B8%AD%E6%AD%A3%E5%8D%80&type=%E6%B4%BB%E5%8B%95&target=%E9%95%B7%E8%80%85&time=month'
```

---

## 10. GET /api/weather

首頁位置／天氣卡使用。瀏覽器取得 GPS 座標後傳給後端，後端向 Open-Meteo 查詢目前天氣；此 API 不需要 API key，也不儲存座標。

**Query 參數**

| 名稱 | 必填 | 限制 |
|------|------|------|
| `lat` | ✅ | 緯度，`-90` 至 `90` |
| `lng` | ✅ | 經度，`-180` 至 `180` |

**回傳 200**：包含 `temperatureC`、`apparentTemperatureC`、`humidityPercent`、`precipitationMm`、`windSpeedKmh`、`isDay`、`condition`、`time` 與 `timezone`。

```bash
curl -k 'https://cachyos-x8664.tail3babf5.ts.net/api/weather?lat=25.0455&lng=121.509'
```

缺少或超出範圍的座標回傳 `422`；天氣上游服務無法使用時回 `502`。

---

## 11. GET /api/places 與 GET /api/places/reverse

申報地點搜尋及位置確認使用 Google Maps。需在 `backend/.env` 設定 `GOOGLE_MAPS_API_KEY`，並在 Google Cloud 專案啟用 **Places API (New)** 與 **Geocoding API**。建議限制此 key 僅能呼叫這兩項 API，且只供後端伺服器使用。

### GET /api/places

文字搜尋台灣地點，最多回傳 5 個候選。空白 `q` 回傳 `[]`。

| Query 參數 | 必填 | 限制 |
|------|------|------|
| `q` | 否 | 最多 200 字 |

**回傳 200**：

```json
[
  {
    "id": "Google Place ID",
    "name": "中正紀念堂",
    "address": "100台灣臺北市中正區中山南路21號",
    "lat": 25.034,
    "lng": 121.521
  }
]
```

```bash
curl -k 'https://cachyos-x8664.tail3babf5.ts.net/api/places?q=%E4%B8%AD%E6%AD%A3%E7%B4%80%E5%BF%B5%E5%A0%82'
```

### GET /api/places/reverse

將 GPS／地圖座標反查成地址；無可用地址時回傳空字串。

| Query 參數 | 必填 | 限制 |
|------|------|------|
| `lat` | ✅ | 緯度 `-90` 至 `90` |
| `lng` | ✅ | 經度 `-180` 至 `180` |

**回傳 200**：

```json
{ "address": "100台灣臺北市中正區中山南路21號" }
```

```bash
curl -k 'https://cachyos-x8664.tail3babf5.ts.net/api/places/reverse?lat=25.034&lng=121.521'
```

缺少 API key 回傳 `503`；Google Maps 上游錯誤回傳 `502`；座標格式錯誤或超出範圍回傳 `422`。

---

### 已知延遲

模型是遠端 Ollama 的 `qwen3.8-16k`（約 17GB VRAM），實測一次「路燈壞了要怎麼通報？」：

| 階段 | 耗時 |
|------|------|
| supervisor 路由 | 2.9s |
| 專家決定要搜尋 | 2.6s |
| 首次關鍵詞延遲 | 7.2s |
| 輸出 826 字（打字機） | 8.3s |

首字前無法再壓低（模型要先 decide 要不要搜、prefill 長 prompt）；首字之後幾乎沒有停頓。要縮短首字時間只能換小模型，見 `OLLAMA_MODEL`。

---


## 12. POST /api/transcribe

瀏覽器錄音送到後端 proxy，再轉給 `TRANSCRIPTION_API_URL`（目前預設 `http://100.109.236.89:8002/transcribe`），避免 HTTPS 頁面直接呼叫 HTTP 服務（mixed content）。前端 `report-review` 的案件描述與地點搜尋麥克風按鈕都使用此端點。

**Request**（`multipart/form-data`）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `file` | file | ✅ | 音訊或影片檔案（`.webm`/`.m4a`/`.ogg`/`.mp4` 等） |
| `language` | string | 否 | 語言代碼，預設 `zh` |

**限制**
- 僅接受 `audio/*`、`video/*` 或 `application/octet-stream`（瀏覽器可能只送 `Content-Type`）
- 檔案上限 **20 MB**
- 需設定 `backend/.env` 的 `TRANSCRIPTION_API_URL`

**回傳 200**

```json
{
  "text": "今天台北天氣很好,我想去公園散步",
  "language": "zh",
  "segments": []
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `text` | string | 轉錄結果，已去除前後空白 |
| `language` | string | 模型回傳的語言 |
| `segments` | array | 分段資訊（若模型有回傳） |

**錯誤**
- `400 { "detail": "請上傳音訊或影片檔案。" }`
- `400 { "detail": "錄音內容是空的，請重新錄製。" }`
- `413 { "detail": "錄音檔超過 20 MB，請縮短錄音。" }`
- `503 { "detail": "尚未設定 TRANSCRIPTION_API_URL。" }`
- `502 { "detail": "語音轉文字服務無法連線: ..." }`
- `502 { "detail": "語音轉文字服務回傳 HTTP ..." }`
- `502 { "detail": "語音轉文字服務回傳無法解析的資料。" }`

```bash
curl -k -X POST https://cachyos-x8664.tail3babf5.ts.net/api/transcribe   -F "file=@/path/to/recording.webm"   -F "language=zh"
```

---

## 附錄 A：前端使用的靜態路徑

| Path | 說明 |
|------|------|
| `GET /` | 回傳 `frontend/index.html`；找不到前端時回 `404` |
| `GET /uploads/{object_path}` | `STORAGE_BACKEND=local` 時，回傳上傳的圖片本體 |
| `https://storage.googleapis.com/my-report-image/{object_path}` | `STORAGE_BACKEND=gcs` 時的圖片公開網址 |

## 附錄 B：已移除的舊 API

| Method | Path | 狀態 |
|--------|------|------|
| `POST` | `/api/login` | 已由 LINE Login（`/api/auth/line/*`）取代，不再提供 |

---

*以 `app/server.py` 現況為準；改後端要同步更新這裡。*