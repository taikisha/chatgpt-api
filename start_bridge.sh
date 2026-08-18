#!/usr/bin/env bash
# start_bridge.sh — บูต ChatGPT Web Bridge สำหรับโรงงานคลิป (พอร์ต 8001)
# โรงงานเรียกผ่าน scripts/start_lan.sh หรือรันตรง ๆ ก็ได้ — กันรันซ้ำด้วย lsof
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

set -a
source .env
set +a

PORT="${CHATGPT_API_PORT:-8001}"
pid="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
if [[ -n "$pid" ]]; then
  echo "bridge already running on port ${PORT} as PID ${pid}"
  exit 0
fi

nohup ./.venv/bin/python -m chatgpt_api server start \
  --host "${CHATGPT_API_HOST:-127.0.0.1}" \
  --port "$PORT" \
  --api-key "$CHATGPT_API_KEY" \
  --accounts-dir "${CHATGPT_ACCOUNTS_DIR:-./secrets/accounts}" \
  --account-strategy "${CHATGPT_ACCOUNT_STRATEGY:-failover}" \
  --image-output-dir "${CHATGPT_IMAGE_OUTPUT_DIR:-./outputs/chatgpt-images}" \
  --research-output-dir "${CHATGPT_RESEARCH_OUTPUT_DIR:-./outputs/chatgpt-research}" \
  --admin-db-path "${CHATGPT_ADMIN_DB_PATH:-./outputs/chatgpt-admin.sqlite}" \
  --public-base-url "${CHATGPT_PUBLIC_BASE_URL:-http://127.0.0.1:${PORT}/v1}" \
  > bridge.log 2>&1 &
echo $! > .bridge.pid
echo "started bridge on port ${PORT} as PID $(cat .bridge.pid) (log: bridge.log)"
