# -*- coding: utf-8 -*-
"""اکشن‌های محیطی — تعامل بازیکن با دنیا (مشعل، در، صندوق، گوش دادن، تله، جستجو و...)."""
import random
import re

from .dice import roll_d20, roll_dice, DiceError, parse_dice

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

    # ---- بررسی و فعال‌سازی تله‌ها ----
    trap_msg = _check_trap_trigger(session, ch, action)
    if trap_msg:
        return trap_msg

    return None


def _lead_character(session):
    """اولین کاراکتر زنده در گروه را برمی‌گرداند (برای اعلان‌های عمومی)."""
    for p in (session.players or {}).values():
        ch = p.get("char")
        if ch and ch.hp > 0:
            return ch
    return None


def _check_trap_trigger(session, ch, action: str, here_override: str = None) -> str:
    """اگر اکشن بازیکن باعث فعال شدن تله این مکان شد، نتیجه را برمی‌گرداند.
    در غیر این صورت None برمی‌گرداند تا AI روایت کند."""
    if not session.scenario:
        return None
    traps = session.scenario.get("traps") or []
    here = here_override or session.world.get("location", "")
    if ch is None:
        ch = _lead_character(session)
    if ch is None:
        return None
    for t in traps:
        if t.get("triggered") or t.get("disarmed"):
            continue
        t_loc = t.get("location", "")
        trigger = str(t.get("trigger", ""))
        # تطابق مکان
        if t_loc and here:
            if t_loc not in here and here not in t_loc:
                continue
        # بررسی اکشن‌های خطرناک (عمومی + کلمات تریگر خود تله)
        danger_actions = ["باز", "جلو", "ورود", "قدم", "حرکت", "برو", "رد", "فشار",
                          "در رو", "صندوق", "پا", "پیش", "باز کردن"]
        trigger_words = [w for w in trigger.split() if len(w) > 2]
        triggered = (any(w in action for w in danger_actions) or
                     any(w in action for w in trigger_words))
        if not triggered:
            continue
        # شانس تشخیص با perception
        roll = roll_d20()
        mod = ability_mod_for(ch, "WIS")
        if ch.cls in ("ranger", "rogue", "monk"):
            mod += 2  # مهارت
        detect_roll = roll + mod
        if detect_roll >= t.get("detect_dc", 13):
            # تله را دید اما هنوز فعال نشده
            return (f"👁️ هشدار! متوجه تله‌ای شدی — «{t['name']}»! "
                    f"عاملش «{t.get('trigger','؟')}» است. "
                    f"برای خنثی کردنش (DC {t.get('disarm_dc',12)}) از مهارت استفاده کن "
                    f"یا با `/check sleight {t.get('disarm_dc',12)}` اقدام کن. "
                    f"اگر رد شوی: {t.get('damage','1d6')} آسیب — {t.get('effect','')}.")
        else:
            # فعال شد! — آسیب به کاراکتر پیشگام
            t["triggered"] = True
            try:
                cnt, sides, dmod = parse_dice(t.get("damage", "1d6"))
                dmg = sum(roll_dice(cnt, sides)) + dmod
            except DiceError:
                dmg = random.randint(1, 6)
            ch.hp = max(0, ch.hp - dmg)
            msg = (f"🪤 **تله!** {t['name']} فعال شد — {t.get('effect','')}! "
                   f"🎲 {ch.name} {dmg} آسیب خورد. (HP: {ch.hp}/{ch.max_hp})")
            if ch.hp <= 0:
                msg += f"\n💀 {ch.name} از پا درآمد!"
            session.add_log(ch.name, f"در تله {t['name']} افتاد و {dmg} آسیب خورد")
            return msg
    return None


def try_disarm_trap(session, ch, trap_name: str = "", dc_override: int = None) -> str:
    """تلاش برای خنثی‌سازی تله در مکان فعلی."""
    if not session.scenario:
        return "اینجا تله‌ای نیست."
    here = session.world.get("location", "")
    for t in (session.scenario.get("traps") or []):
        if t.get("triggered") or t.get("disarmed"):
            continue
        t_loc = t.get("location", "")
        if t_loc and here and t_loc not in here and here not in t_loc:
            continue
        if trap_name and trap_name not in t.get("name", "") and t.get("name", "") not in trap_name:
            continue
        # تلاش خنثی‌سازی
        dc = dc_override or t.get("disarm_dc", 12)
        roll = roll_d20()
        mod = ability_mod_for(ch, "DEX")
        if ch.cls in ("rogue", "ranger", "monk", "fighter"):
            mod += 2  # مهارت Slight of Man / Tools
        total = roll + mod
        if total >= dc:
            t["disarmed"] = True
            session.add_log(ch.name, f"تله {t['name']} را خنثی کرد")
            return (f"🔧 {ch.name} با ظرافت تله «{t['name']}» را خنثی کرد! "
                    f"(🎲 {roll}+{mod}={total} ≥ DC {dc})")
        else:
            # شکست — تله فعال می‌شود
            t["triggered"] = True
            try:
                cnt, sides, dmod = parse_dice(t.get("damage", "1d6"))
                dmg = sum(roll_dice(cnt, sides)) + dmod
            except DiceError:
                dmg = random.randint(1, 6)
            ch.hp = max(0, ch.hp - dmg)
            msg = (f"💥 تلاش ناموفق! تله «{t['name']}» فعال شد! "
                   f"{ch.name} {dmg} آسیب خورد (🎲 {roll}+{mod}={total} < DC {dc}). "
                   f"HP: {ch.hp}/{ch.max_hp}")
            session.add_log(ch.name, f"در خنثی‌سازی تله {t['name']} شکست خورد و {dmg} آسیب خورد")
            return msg
    return "اینجا تله‌ای برای خنثی‌سازی پیدا نکردی."


def ability_mod_for(ch, ability: str) -> int:
    """پاداش توانایی را برمی‌گرداند (برای چک تله/ادراک)."""
    from .rules import ability_mod
    return ability_mod(ch.abilities.get(ability, 10))
