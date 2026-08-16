#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  📱 نصب ربات D&D روی گوشی اندروید (Termux) — یک‌دستوری
#  اجرا:  bash termux/setup.sh
# ============================================================
set -e

echo "📦 به‌روزرسانی پکیج‌های Termux..."
pkg update -y && pkg upgrade -y

echo "🐍 نصب پایتون و ابزارها..."
pkg install -y python git termux-api cloudflared

echo "📚 نصب کتابخانه‌های ربات..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🔋 فعال‌سازی Wake Lock (جلوگیری از خواب گوشی)..."
termux-wake-lock || true

echo ""
echo "✅ نصب کامل شد!"
echo ""
echo "قدم بعدی: فایل .env را بساز:"
echo "   cp .env.example .env"
echo "   nano .env     ← توکن ربات و کلید AI را وارد کن"
echo ""
echo "سپس اجرا کن:"
echo "   bash termux/run.sh"
