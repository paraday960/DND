# -*- coding: utf-8 -*-
"""سیستم تجهیزات — تعویض سلاح/زره/سپر در جریان بازی."""
from .rules import WEAPONS, CLASSES

# زره‌های ساده
ARMORS = {
    "none": {"fa": "بدون زره", "ac_bonus": 0, "emoji": "👕"},
    "light": {"fa": "زره سبک", "ac_bonus": 2, "emoji": "🦺"},
    "medium": {"fa": "زره متوسط", "ac_bonus": 4, "emoji": "🛡️"},
    "heavy": {"fa": "زره سنگین", "ac_bonus": 6, "emoji": "⚔️"},
    "robe": {"fa": "ردای جادویی", "ac_bonus": 1, "emoji": "🧥"},
}

# زره مجاز هر کلاس
CLASS_ARMOR = {
    "fighter": ["light", "medium", "heavy"],
    "rogue": ["light"],
    "wizard": ["none", "robe"],
    "cleric": ["light", "medium"],
    "ranger": ["light", "medium"],
    "bard": ["light"],
    "barbarian": ["medium", "heavy"],
    "paladin": ["medium", "heavy"],
    "druid": ["light", "medium"],
    "monk": ["none"],
    "sorcerer": ["none", "robe"],
    "warlock": ["none", "robe"],
}


def equip_weapon(ch, weapon_key: str) -> str:
    """سلاح جدید را تجهیز می‌کند. باید در موجودی باشد."""
    if weapon_key not in WEAPONS:
        return f"چنین سلاحی وجود ندارد: {weapon_key}"
    if weapon_key not in ch.inventory or ch.inventory.get(weapon_key, 0) <= 0:
        return f"{WEAPONS[weapon_key]['fa']} را در موجودی نداری."
    # سلاح قبلی به موجودی برمی‌گردد (اگر غیر از مشت بود)
    old = ch.weapon
    if old and old != weapon_key and old not in ("fist", "unarmed"):
        ch.inventory[old] = ch.inventory.get(old, 0) + 1
    ch.inventory[weapon_key] -= 1
    if ch.inventory[weapon_key] <= 0:
        ch.inventory.pop(weapon_key, None)
    ch.weapon = weapon_key
    return f"🗡️ سلاح به {WEAPONS[weapon_key]['fa']} تغییر کرد."


def equip_armor(ch, armor_key: str) -> str:
    if armor_key not in ARMORS:
        return "چنین زرهی وجود ندارد."
    allowed = CLASS_ARMOR.get(ch.cls, ["none"])
    if armor_key not in allowed:
        return f"کلاس {CLASSES[ch.cls]['fa']} نمی‌تواند {ARMORS[armor_key]['fa']} بپوشد."
    old_ac = ch.ac
    ch.armor = armor_key
    from .rules import ability_mod
    dex_bonus = max(2, ability_mod(ch.abilities["DEX"])) if armor_key in ("light", "medium") else ability_mod(ch.abilities["DEX"]) if armor_key == "none" else 0
    base = 10
    if armor_key == "heavy":
        base = 16  # plate-like
    elif armor_key == "medium":
        base = 14 + min(2, ability_mod(ch.abilities["DEX"]))
    elif armor_key == "light":
        base = 11 + ability_mod(ch.abilities["DEX"])
    elif armor_key == "robe":
        base = 10 + ability_mod(ch.abilities["DEX"])
    ch.ac = base + (2 if ch.inventory.get("shield", 0) > 0 else 0)
    return f"🛡️ زره به {ARMORS[armor_key]['fa']} تغییر کرد (AC: {old_ac} → {ch.ac})."


def give_starting_equipment(ch):
    """تجهیزات آغازین کلاس."""
    # سلاح اصلی که هنگام ساخت انتخاب شده در inventory قرار می‌گیرد
    # (الان ch.weapon ست شده و یک نسخه از آن در دست است)
    ch.inventory.setdefault("potion", 2)
    ch.inventory.setdefault("torch", 3)
    ch.inventory.setdefault("rope", 1)
    # زره شروع
    if ch.cls in ("fighter", "paladin", "barbarian"):
        ch.armor = "medium"
    elif ch.cls in ("rogue", "ranger", "bard"):
        ch.armor = "light"
    else:
        ch.armor = "none"
    # محاسبه AC
    equip_armor(ch, ch.armor)
