#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  📲 راه‌اندازی خودکار هنگام روشن شدن گوشی
#  نیاز: اپ Termux:Boot از F-Droid
#  فایل را در ~/.termux/boot/ کپی کن:
#     mkdir -p ~/.termux/boot
#     cp termux/boot.sh ~/.termux/boot/
# ============================================================
cd "$HOME/dnd-bot" || exit 1
termux-wake-lock 2>/dev/null || true
nohup ./termux/run.sh > data/bot.log 2>&1 &
