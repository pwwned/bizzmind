#!/bin/zsh
# Стартира Bizzmind + публичен тунел (за Gamma да тегли графики/лого).
# Употреба: ./start.sh        (Ctrl+C спира и двете)
cd "$(dirname "$0")"
pkill -f "uvicorn app:app" 2>/dev/null; pkill -f "cloudflared tunnel" 2>/dev/null; sleep 1
cloudflared tunnel --url http://127.0.0.1:8000 > data/tunnel.log 2>&1 &
TUN=$!
for i in {1..30}; do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/tunnel.log | head -1)
  [ -n "$URL" ] && break; sleep 1
done
if [ -n "$URL" ]; then
  if grep -q '^PUBLIC_BASE_URL=' .env; then sed -i '' "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$URL|" .env
  else echo "PUBLIC_BASE_URL=$URL" >> .env; fi
  echo "Публичен адрес: $URL"
else
  echo "Тунелът не тръгна — Gamma ще работи без картинки."
fi
trap "kill $TUN 2>/dev/null" EXIT
echo "Приложение: http://127.0.0.1:8000"
exec .venv/bin/uvicorn app:app --port 8000
