#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  🚀 اجرای ربات D&D روی گوشی — با ری‌استارت خودکار
# ============================================================
cd "$(dirname "$0")/.."

# جلوگیری از خواب گوشی
termux-wake-lock 2>/dev/null || true

# اگر تونل مینی‌گیم باز نیست، بازش کن
if [ ! -f data/tunnel_url.txt ] && command -v cloudflared &>/dev/null; then
  echo "🌐 راه‌اندازی تونل مینی‌گیم..."
  bash termux/tunnel.sh
fi

echo "🚀 شروع ربات D&D..."
while true; do
  python main.py
  echo "⚠️ ربات متوقف شد — ۵ ثانیه بعد دوباره شروع می‌شود..."
  sleep 5
done
