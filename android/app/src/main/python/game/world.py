# -*- coding: utf-8 -*-
"""اکشن‌های محیطی — تعامل بازیکن با دنیا (مثل روشن کردن مشعل)."""
import re

from .dice import roll_expression, DiceError

# کلمات کلیدی برای اکشن‌های رایج
_LIGHT_PATTERNS = [
    r"مشعل\S* (روشن|آتش|افروختن|بزن|درست)",
    r"(روشن|آتش|افروز)\S* (کردن|کن|بزن|) ?(مشعل|چراغ|آتش|فانوس|شمع|مشعلی)",
    r"(مشعل|فانوس|شمع|چراغ)\S* (را )?(روشن|آتش|افروز|برافروز|بزن)",
    r"آتش (روشن|افروز|بزن|درست)",
]
_LOOK_PATTERNS = [r"نگاه", r"بررسی", r"جستجو", r"دنبال", r"دیدن", r"ببین"]
_OPEN_PATTERNS = [r"باز کن", r"در رو", r"صندوق", r"در را باز"]
_LISTEN_PATTERNS = [r"گوش", r"بشنو", r"صدا"]


def _matches(action, patterns):
    a = action.strip()
    return any(re.search(p, a) for p in patterns)


def _has_item(ch, item):
    return item in (ch.inventory or {}) and ch.inventory.get(item, 0) > 0


def _consume(ch, item):
    if item in ch.inventory and ch.inventory[item] > 0:
        ch.inventory[item] -= 1
        return True
    return False


def try_environment_action(session, ch, action: str):
    """اگر اکشن یک تعامل ساده با دنیا بود، نتیجه را برمی‌گرداند.
    در غیر این صورت None تا راوی AI آن را روایت کند."""
    if not ch:
        return None
    act = action.strip()

    # روشن کردن مشعل / چراغ
    if _matches(act, _LIGHT_PATTERNS):
        if session.world.get("light") == "torch" or session.world.get("light") == "bright":
            return ("🔥 از قبل روشنایی کافی برقرار است — مشعل روشن تو همه‌جا را به‌خوبی نشان می‌دهد. "
                    "شعله روی دیوار‌های نمدار می‌رقصد و سایه‌های بلند را عقب می‌راند.")
        if _has_item(ch, "torch"):
            _consume(ch, "torch")
            session.world["light"] = "torch"
            session.world.setdefault("flags", {})["torch_lit"] = True
            session.add_log(ch.name, "مشعل روشن کرد")
            return ("🔥 مشعل را از کوله در می‌آوری و با سنگ‌چخماق روشن می‌کنی. نور گرم و لرزان "
                    "دیوار‌های سیاهچال را روشن می‌کند. از این پس جزئیات را می‌بینی و رد پنهان "
                    "دشمنان بهتر پیدا می‌شود. (۳ مشعل باقی ماند)")
        if _has_item(ch, "potion"):
            return "🕯️ مشعل نداری! اما می‌توانی معجونت را بفروشی یا از یک همراه مشعل بگیری."
        return "🌑 مشعل نداری — فعلاً در تاریکی هستی. سایه‌ها همه‌چیز را پنهان کرده‌اند."

    # نگاه/بررسی
    if _matches(act, _LOOK_PATTERNS) and len(act) < 40:
        light = session.world.get("light", "dark")
        if light == "dark":
            return ("🌑 هوا تاریک است و چیزی نمی‌بینی. فقط صدای چکیدن آب از سقف و خرت‌وپرت "
                    "مبهمی در دوردست به گوش می‌رسد. برای دیدن، مشعل روشن کن.")
        if session.scenario and session.scenario.get("locations"):
            loc = session.world.get("location") or session.scenario["locations"][0]
            return f"👁️ نگاه می‌اندازی — در «{loc}». گرد و غبار سنگین روی سنگفرش، نشانه‌های کهنه و رد‌هایی که قبلاً نبود..."
        return "👁️ اطراف را بررسی می‌کنی اما چیز خاصی به چشم نمی‌خورد."

    return None
