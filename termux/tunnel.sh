#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  🌐 تونل امن رایگان Cloudflare برای مینی‌گیم تلگرام
#  اجرا:  bash termux/tunnel.sh
#  یک آدرس https://xxx.trycloudflare.com می‌گیرد و در
#  data/tunnel_url.txt ذخیره می‌کند؛ ربات خودکار از آن استفاده می‌کند.
# ============================================================
cd "$(dirname "$0")/.."
mkdir -p data

if ! command -v cloudflared &>/dev/null; then
  echo "📦 نصب cloudflared..."
  pkg install -y cloudflared
fi

if pgrep -f "cloudflared tunnel" &>/dev/null; then
  echo "✅ تونل از قبل در حال اجراست."
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" data/tunnel.log 2>/dev/null | head -1)
else
  echo "🌐 شروع تونل امن (رایگان)..."
  nohup cloudflared tunnel --url http://127.0.0.1:${PORT:-8080} > data/tunnel.log 2>&1 &
  echo "⏳ چند لحظه صبر کن..."
  for i in $(seq 1 25); do
    URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" data/tunnel.log 2>/dev/null | head -1)
    [ -n "$URL" ] && break
    sleep 1
  done
fi

if [ -n "$URL" ]; then
  echo "$URL" > data/tunnel_url.txt
  echo ""
  echo "✅ آدرس مینی‌گیم: $URL"
  echo "🎮 حالا در تلگرام /start بزن و دکمه «ورود به مینی‌گیم» را لمس کن!"
else
  echo "❌ تونل باز نشد — لاگ را ببین: data/tunnel.log"
fi
