# -*- coding: utf-8 -*-
"""اکشن‌های محیطی — تعامل بازیکن با دنیا (مشعل، در، صندوق، گوش دادن و...)."""
import random
import re

from .dice import roll_d20, DiceError

_LIGHT_PATTERNS = [
    r"مشعل\S* (روشن|آتش|افروختن|بزن|درست)",
    r"(روشن|آتش|افروز)\S* (کردن|کن|بزن|) ?(مشعل|چراغ|آتش|فانوس|شمع|مشعلی)",
    r"(مشعل|فانوس|شمع|چراغ)\S* (را )?(روشن|آتش|افروز|برافروز|بزن)",
    r"آتش (روشن|افروز|بزن|درست)",
]
_LOOK_PATTERNS = [r"نگاه", r"بررسی", r"جستجو", r"دنبال", r"دیدن", r"ببین"]
_LISTEN_PATTERNS = [r"گوش", r"بشنو", r"صدا"]
_OPEN_PATTERNS = [r"باز کن", r"در رو", r"در را باز", r"صندوق"]
_TAKE_PATTERNS = [r"بردار", r"برمی‌?دارم", r"بگیر", r"جمع کن", r"بردارم"]
_SNEAK_PATTERNS = [r"بی‌?صدا", r"دزدکی", r"مخفی", r"پنهان"]


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
    در غیر این صورت None برمی‌گرداند تا راوی AI آن را روایت کند."""
    if not ch:
        return None
    act = action.strip()

    # ---- روشن کردن مشعل ----
    if _matches(act, _LIGHT_PATTERNS):
        if session.world.get("light") == "torch":
            return "🔥 از قبل مشعل روشن داری."
        if _has_item(ch, "torch"):
            _consume(ch, "torch")
            session.world["light"] = "torch"
            session.world.setdefault("flags", {})["torch_lit"] = True
            session.add_log(ch.name, "مشعل روشن کرد")
            # شانس پیدا کردن آیتم در نور
            return ("🔥 مشعل را روشن می‌کنی. نور گرم و لرزان دیوارها را روشن می‌کند. "
                    "حالا می‌توانی جلوتر بروی.")
        return "🌑 مشعل نداری. در تاریکی هستی."

    # ---- گوش دادن ----
    if _matches(act, _LISTEN_PATTERNS) and len(act) < 40:
        light = session.world.get("light", "dark")
        if session.combat:
            return "👂 صدای برخورد سلاح‌ها و نعره دشمنان را می‌شنوی."
        ambient = random.choice([
            "صدای چکیدن آب از سقف و خرت‌وپرت مبهمی در دوردست.",
            "به نظر می‌رسد کسی یا چیزی در سکوت نفس می‌کشد.",
            "باد از شکافی در دیوار زوزه می‌کشد.",
            "سکوت مرگبار؛ فقط ضربان قلب خودت را می‌شنوی.",
        ])
        return f"👂 گوش می‌دهی: {ambient}"

    # ---- باز کردن در/صندوق ----
    if _matches(act, _OPEN_PATTERNS) and len(act) < 40 and not session.combat:
        flags = session.world.setdefault("flags", {})
        if "door_opened" in flags:
            return "🚪 در از قبل باز است."
        flags["door_opened"] = True
        # شانس گنج
        if random.random() < 0.6:
            loot = random.choice([
                ("potion", 1, "معجون سلامتی"),
                ("gold", random.randint(5, 25), "سکه طلا"),
                ("torch", 1, "مشعل"),
            ])
            ch.inventory[loot[0]] = ch.inventory.get(loot[0], 0) + loot[1]
            return f"🚪 در را باز می‌کنی. یک {loot[2]} پیدا کردی!"
        return "🚪 در با صدای خشکی باز می‌شود. راهرویی تاریک پیداست."

    # ---- برداشتن/جستجو ----
    if _matches(act, _TAKE_PATTERNS) and len(act) < 40 and not session.combat:
        if random.random() < 0.5:
            gold = random.randint(2, 15)
            ch.inventory["gold"] = ch.inventory.get("gold", 0) + gold
            return f"💰 {gold} سکه پیدا کردی."
        return "چیزی پیدا نکردی."

    # ---- نگاه/بررسی ----
    if _matches(act, _LOOK_PATTERNS) and len(act) < 40:
        light = session.world.get("light", "dark")
        if light == "dark" and not session.combat:
            return ("🌑 هوا تاریک است و چیزی نمی‌بینی. برای دیدن مشعل روشن کن.")
        if session.combat:
            cur = session.combat["participants"][session.combat["turn"]]
            alive = [p["name"] for p in session.combat["participants"]
                     if p.get("kind") == "monster" and p.get("alive")]
            return f"👁️ در نبرد: نوبت {cur['name']}. دشمنان زنده: {', '.join(alive)}."
        if session.scenario and session.scenario.get("locations"):
            loc = session.world.get("location") or session.scenario["locations"][0]
            return f"👁️ در «{loc}». سنگفرش غبارآلود، دیوارهای نمدار..."
        return "👁️ چیز خاصی به چشم نمی‌خورد."

    return None
