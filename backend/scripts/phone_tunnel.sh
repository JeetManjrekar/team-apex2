#!/bin/sh
# Public HTTPS link for the phone page (phones only allow the microphone and GPS on HTTPS).
# Starts a temporary Cloudflare quick tunnel to the local server, writes the link to data/public_url.txt
# (the laptop shows it as a QR code: ⋯ menu -> "Phone app (QR)"), and removes it again on Ctrl+C.
# Anyone with the link can use the app while this runs - stop it after the demo.
cd "$(dirname "$0")/.." || exit 1
PORT="${PORT:-8000}"
OUT="data/public_url.txt"
LOG="$(mktemp -t baubuddy_tunnel)"
command -v cloudflared >/dev/null || { echo "Install first: brew install cloudflared"; exit 1; }
curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null || { echo "Start the server first (uvicorn app:app --port $PORT)"; exit 1; }
cleanup() { rm -f "$OUT"; kill "$PID" 2>/dev/null; echo; echo "Tunnel closed."; }
trap cleanup INT TERM EXIT
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$LOG" 2>&1 &
PID=$!
echo "Opening tunnel…"
for _ in $(seq 1 40); do
  URL=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "$URL" ] && break
  sleep 0.5
done
[ -z "$URL" ] && { echo "No tunnel URL. Log:"; cat "$LOG"; exit 1; }
printf "Waiting for the link to go live"
for _ in $(seq 1 30); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/health")" = "200" ] && break
  printf "."; sleep 2
done
echo
echo "$URL" > "$OUT"
echo ""
echo "  Phone page:  $URL/m.html"
echo "  QR code:     laptop -> ⋯ menu -> Phone app (QR)"
echo ""
echo "Press Ctrl+C to stop."
wait "$PID"
