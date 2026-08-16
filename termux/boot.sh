#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  📲 راه‌اندازی خودکار هنگام روشن شدن گوشی
#  نیاز: اپ Termux:Boot از F-Droid
#  فایل را در ~/.termux/boot/ کپی کن:
#     mkdir -p ~/.termux/boot
#     cp termux/boot.sh ~/.termux/boot/
# ============================================================
# محل پیش‌فرض: ~/DND (همان نام ریپازیتوری)
cd "$HOME/DND" || cd "$HOME/dnd-bot" || exit 1
mkdir -p data
termux-wake-lock 2>/dev/null || true
nohup bash ./termux/run.sh > data/bot.log 2>&1 &
