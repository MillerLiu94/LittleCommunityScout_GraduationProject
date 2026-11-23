#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="lcs-app:latest"
CONTAINER_NAME="lcs-app"
ENV_FILE="$ROOT_DIR/backend/.env"
UPLOAD_DIR="$ROOT_DIR/backend/data/uploads"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "錯誤：找不到 $ENV_FILE，請先從 backend/.env.example 複製並設定。" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "錯誤：無法連線到 Docker daemon。請確認已啟動 docker.service（sudo systemctl enable --now docker），且目前帳號有權限執行 docker（或改用 sudo ./deploy.sh）。" >&2
  exit 1
fi

mkdir -p "$UPLOAD_DIR"

# 偵測本機 GCS service account 金鑰（若有就掛進容器並覆寫容器內路徑）
GCS_KEY_FILE=""
for candidate in "$ROOT_DIR"/backend/gcs-api-*.json "$ROOT_DIR"/backend/service-account*.json; do
  if [[ -f "$candidate" ]]; then
    GCS_KEY_FILE="$candidate"
    break
  fi
done

echo "[1/3] 建置 Docker 映像檔 ($IMAGE_NAME)..."
docker build -t "$IMAGE_NAME" "$ROOT_DIR"

echo "[2/3] 重啟容器 ($CONTAINER_NAME)..."
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

RUN_ARGS=(
  -d
  --name "$CONTAINER_NAME"
  --restart unless-stopped
  -p 127.0.0.1:8000:8000
  --env-file "$ENV_FILE"
  -e SSL_DISABLE=1
  -e UVICORN_RELOAD=0
  -v "$UPLOAD_DIR:/app/backend/data/uploads"
)

if [[ -n "$GCS_KEY_FILE" ]]; then
  echo "      掛載 GCS 金鑰：$(basename "$GCS_KEY_FILE") -> /app/gcs-key.json"
  RUN_ARGS+=(
    -v "$GCS_KEY_FILE:/app/gcs-key.json:ro"
    -e GOOGLE_APPLICATION_CREDENTIALS=/app/gcs-key.json
  )
fi

docker run "${RUN_ARGS[@]}" "$IMAGE_NAME" >/dev/null

echo "[3/3] 等待服務啟動並驗證..."
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/api/runtime-config.js >/dev/null 2>&1; then
    echo "服務已就緒："
    echo "  本機：http://127.0.0.1:8000"
    echo "  Tailscale HTTPS：https://cachyos-x8664.tail3babf5.ts.net/"
    exit 0
  fi
  sleep 1
done

echo "警告：服務在 20 秒內未回應，以下為容器日誌：" >&2
docker logs --tail 50 "$CONTAINER_NAME" >&2
exit 1
