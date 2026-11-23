# Stage 1: 準備前端靜態檔，並將 daisyUI 從 node_modules 展開成實體 CSS
FROM node:22-alpine AS frontend-builder
WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --omit=dev

COPY frontend/index.html ./dist/index.html
COPY frontend/api ./dist/api
COPY frontend/assets ./dist/assets
COPY frontend/css ./dist/css
COPY frontend/js ./dist/js
COPY frontend/pages ./dist/pages

# frontend/css/daisyui.css 原內容為 `@import "daisyui/daisyui.css";`（僅 Vite 開發環境可解析），
# 正式由 FastAPI 直接提供靜態檔時，改為複製實體 CSS 檔案。
RUN cp node_modules/daisyui/daisyui.css ./dist/css/daisyui.css


# Stage 2: Python FastAPI 後端（同源服務 /api/* 與 /app/frontend/dist）
FROM python:3.14-slim
WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    SSL_DISABLE=1 \
    UVICORN_RELOAD=0

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-builder /build/dist /app/frontend/dist

EXPOSE 8000
CMD ["python", "server.py"]
