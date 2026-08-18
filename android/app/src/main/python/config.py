# -*- coding: utf-8 -*-
"""تنظیمات ربات — همه‌چیز از فایل .env خوانده می‌شود."""
import os


def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

# ---------- تلگرام ----------
# strip() تا فاصله/خط جدیدی که موقع کپی توکن اضافه می‌شود، اعتبارسنجی را خراب نکند
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# ---------- هوش مصنوعی (همه رایگان) ----------
# انتخاب فراهم‌کننده: gemini | groq | openrouter | mistral | none
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

# ---------- پایگاه داده ----------
DB_PATH = os.environ.get(
    "DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dnd_bot.db")
)

# ---------- قوانین بازی ----------
MAX_PLAYERS = int(os.environ.get("MAX_PLAYERS", "8"))
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "fa")

# ---------- مینی‌گیم (Telegram Mini App) ----------
# آدرس HTTPS مینی‌گیم (از termux/tunnel.sh گرفته می‌شود یا دستی وارد کن)
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").strip()
# حالت آزمایشی: بدون تلگرام هم با کاربر آزمایشی کار می‌کند (برای پیش‌نمایش/تست)
WEBAPP_DEV = os.environ.get("WEBAPP_DEV", "0") == "1"
# پورت وب‌سرور مینی‌گیم
PORT = int(os.environ.get("PORT", "8080"))


def webapp_url() -> str:
    """آدرس مینی‌گیم: اول از .env، بعد از فایل تونل Termux."""
    if WEBAPP_URL:
        return WEBAPP_URL
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tunnel_url.txt")
    try:
        with open(p, encoding="utf-8") as f:
            u = f.read().strip()
        return u if u.startswith("https://") else ""
    except Exception:
        return ""
