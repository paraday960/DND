# -*- coding: utf-8 -*-
"""مکانیک‌های ماجراجویی خارج از نبرد: مهارت، استراحت، آیتم و نجات از مرگ."""
import random
from .dice import roll_d20
from .rules import SKILLS, ability_mod, proficiency_bonus


def skill_check(session, uid: int, skill: str, dc: int = 10, mode: str = "normal") -> str:
    ch = session.get_char(uid)
    key = (skill or "").strip().lower()
    if not ch:
        return "کاراکترت را بساز."
    if key not in SKILLS:
        return "مهارت نامعتبر است: " + ", ".join(SKILLS)
    ability = SKILLS[key]["ability"]
    bonus = ability_mod(ch.abilities[ability]) + (proficiency_bonus(ch.level) if key in ch.proficiencies else 0)
    r1, r2 = roll_d20(), roll_d20()
    raw = max(r1, r2) if mode in ("adv", "advantage") else min(r1, r2) if mode in ("dis", "disadvantage") else r1
    total = raw + bonus
    success = total >= int(dc)
    text = f"🎲 آزمایش {SKILLS[key]['fa']} (DC {dc}): {raw} {bonus:+d} = **{total}** — " + ("✅ موفق" if success else "❌ ناموفق")
    if mode != "normal":
        text += f" (تاس‌ها: {r1} و {r2})"
    session.add_log(ch.name, text)
    return text


def rest(session, uid: int, kind: str = "short") -> str:
    ch = session.get_char(uid)
    if not ch:
        return "کاراکترت را بساز."
    if session.combat:
        return "در نبرد نمی‌توانی استراحت کنی."
    if kind.lower() in ("long", "طولانی"):
        before = ch.hp
        ch.hp = ch.max_hp
        ch.death_saves = {"success": 0, "fail": 0}
        ch.conditions = []
        ch.reset_spell_slots()
        return f"🌙 استراحت طولانی انجام شد: HP از {before} به {ch.hp} رسید و وضعیت‌ها پاک شد."
    heal = min(ch.max_hp - ch.hp, max(1, ch.hit_die + ability_mod(ch.abilities["CON"])))
    ch.hp += heal
    return f"🔥 استراحت کوتاه: **+{heal} HP** (اکنون {ch.hp}/{ch.max_hp})"


def use_item(session, uid: int, item: str) -> str:
    ch = session.get_char(uid)
    key = (item or "").strip().lower()
    if not ch:
        return "کاراکترت را بساز."
    # تطبیق نام (مثلاً «معجون بزرگ» یا «potion of healing»)
    if "great" in key or "بزرگ" in key or "قوی" in key:
        key = "great_potion"
    elif "potion" in key or "معجون" in key or "شربت" in key:
        key = "potion"
    elif "antidote" in key or "پادزهر" in key:
        key = "antidote"
    if key not in ch.inventory or ch.inventory.get(key, 0) <= 0:
        return f"این آیتم را نداری. موجودی: {inventory_text(ch)}"
    if key == "potion":
        before = ch.hp
        ch.hp = min(ch.max_hp, ch.hp + random.randint(2, 10) + 2)
        ch.inventory[key] -= 1
        if ch.inventory[key] <= 0:
            ch.inventory.pop(key, None)
        return f"🧪 معجون شفا نوشیدی: +{ch.hp-before} HP (اکنون {ch.hp}/{ch.max_hp})"
    if key == "great_potion":
        before = ch.hp
        ch.hp = min(ch.max_hp, ch.hp + random.randint(8, 20) + 4)
        ch.inventory[key] -= 1
        if ch.inventory[key] <= 0:
            ch.inventory.pop(key, None)
        return f"🧪 معجون بزرگ شفا نوشیدی: +{ch.hp-before} HP (اکنون {ch.hp}/{ch.max_hp})"
    if key == "antidote":
        ch.conditions = [c for c in ch.conditions if c not in ("poisoned", "poison")]
        ch.inventory[key] -= 1
        if ch.inventory[key] <= 0:
            ch.inventory.pop(key, None)
        return "💚 پادزهر خوردی؛ وضعیت مسمومیت برطرف شد."
    if key == "torch":
        session.world["light"] = "torch"
        ch.inventory[key] -= 1
        if ch.inventory[key] <= 0:
            ch.inventory.pop(key, None)
        return "🔥 مشعل روشن کردی!"
    return "این آیتم هنوز کاربردی ندارد."


def death_save(session, uid: int) -> str:
    """نجات از مرگ استاندارد: سه موفقیت یا سه شکست."""
    ch = session.get_char(uid)
    if not ch:
        return "کاراکتری برایت پیدا نشد."
    if ch.hp > 0:
        return "در وضعیت مرگ نیستی."
    participant = next((p for p in (session.combat or {}).get("participants", [])
                        if p.get("kind") == "player" and p.get("uid") == str(uid)), None)
    if not participant:
        return "در این نبرد شرکت نکردی."
    if participant.get("dead"):
        return "این کاراکتر مرده است."
    if not participant.get("downed"):
        participant["downed"] = True
        participant["hp"] = 0
    roll = roll_d20()
    if roll == 20:
        ch.hp = 1
        ch.death_saves = {"success": 0, "fail": 0}
        participant["hp"] = 1
        participant["downed"] = False
        participant["alive"] = True
        return "🌟 بیست طبیعی! با ۱ HP دوباره بلند شدی."
    if roll == 1:
        ch.death_saves["fail"] += 2
    elif roll >= 10:
        ch.death_saves["success"] += 1
    else:
        ch.death_saves["fail"] += 1
    s, f = ch.death_saves["success"], ch.death_saves["fail"]
    if s >= 3:
        ch.hp = 1
        ch.death_saves = {"success": 0, "fail": 0}
        participant["hp"] = 1
        participant["downed"] = False
        participant["alive"] = True
        return "🩹 پایدار شدی و با ۱ HP به هوش آمدی!"
    if f >= 3:
        participant["dead"] = True
        participant["alive"] = False
        participant["downed"] = False
        return "☠️ سه شکست! کاراکترت مرد. هم‌گروهی‌ها باید از Revivify یا Resurrection استفاده کنند."
    return f"💀 مرگ‌سیو: {roll} — موفقیت {s}/3، شکست {f}/3"


def inventory_text(ch) -> str:
    return "، ".join(f"{k}: {v}" for k, v in ch.inventory.items() if v > 0) or "خالی"
