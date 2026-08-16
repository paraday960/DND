# -*- coding: utf-8 -*-
"""قوانین D&D 5e — نژادها، کلاس‌ها، سلاح‌ها، توانایی‌ها و جداول ساده‌شده."""

ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
ABILITY_FA = {
    "STR": "قدرت",
    "DEX": "چابکی",
    "CON": "استقامت",
    "INT": "هوش",
    "WIS": "ادراک",
    "CHA": "جذابیت",
}

# آرایه استاندارد امتیاز توانایی‌ها
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]

# جدول تجربه و سطح (تا سطح ۲۰)
XP_TABLE = [0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000, 85000,
            100000, 120000, 140000, 165000, 195000, 225000, 265000, 305000, 355000]


def ability_mod(score: int) -> int:
    return (score - 10) // 2


def level_from_xp(xp: int) -> int:
    level = 1
    for i, need in enumerate(XP_TABLE):
        if xp >= need:
            level = i + 1
    return level


def proficiency_bonus(level: int) -> int:
    return 2 + (level - 1) // 4


# ---------------- نژادها ----------------
RACES = {
    "human": {
        "fa": "انسان", "emoji": "🧑", "bonus": {"STR": 1, "DEX": 1, "CON": 1, "INT": 1, "WIS": 1, "CHA": 1},
        "features": ["همه‌کاره: ۱+ در همه توانایی‌ها"],
    },
    "elf": {
        "fa": "الف", "emoji": "🧝", "bonus": {"DEX": 2, "INT": 1},
        "features": ["دید در تاریکی", "مقاومت در برابر جادوی خواب", "دقت الفی"],
    },
    "dwarf": {
        "fa": "دورف", "emoji": "⛏️", "bonus": {"CON": 2, "STR": 1},
        "features": ["سخت‌جانی", "دید در تاریکی", "مقاومت در برابر زهر"],
    },
    "halfling": {
        "fa": "هالفلینگ", "emoji": "🍀", "bonus": {"DEX": 2, "CHA": 1},
        "features": ["خوش‌شانسی (تاس ۱ را دوباره می‌اندازی)", "کوچک‌جثه"],
    },
    "gnome": {
        "fa": "گنوم", "emoji": "🔧", "bonus": {"INT": 2, "DEX": 1},
        "features": ["تیزهوش", "حقه‌بازی کوچک"],
    },
    "half_orc": {
        "fa": "نیمه‌اورک", "emoji": "👹", "bonus": {"STR": 2, "CON": 1},
        "features": ["هجوم بی‌رحمانه", "پافشاری (یک بار به جای مرگ زنده می‌مانی)"],
    },
    "tiefling": {
        "fa": "تیفلینگ", "emoji": "😈", "bonus": {"CHA": 2, "INT": 1},
        "features": ["مقاومت در برابر آتش", "جادوی جهنمی"],
    },
    "dragonborn": {
        "fa": "اژدهازاده", "emoji": "🐲", "bonus": {"STR": 2, "CHA": 1},
        "features": ["نفس اژدهایی"],
    },
}

# ---------------- کلاس‌ها ----------------
CLASSES = {
    "fighter": {
        "fa": "جنگجو", "emoji": "⚔️", "hit_die": 10, "primary": ["STR", "DEX"],
        "saves": ["STR", "CON"], "armor": True,
        "features": ["سبک مبارزه", "نفس دوم (Second Wind)", "Action Surge"],
        "weapons": ["longsword", "greataxe", "rapier", "longbow", "shield"],
    },
    "wizard": {
        "fa": "جادوگر", "emoji": "🔮", "hit_die": 6, "primary": ["INT"],
        "saves": ["INT", "WIS"], "armor": False,
        "features": ["طلسم‌آموزی", "بازیابی جادویی", "آرکین"],
        "weapons": ["staff", "dagger"],
    },
    "rogue": {
        "fa": "دزد", "emoji": "🗡️", "hit_die": 8, "primary": ["DEX"],
        "saves": ["DEX", "INT"], "armor": False,
        "features": ["حمله غافلگیرانه (Sneak Attack)", "Cunning Action", "زبان‌آوری"],
        "weapons": ["rapier", "dagger", "shortbow"],
    },
    "cleric": {
        "fa": "روحانی", "emoji": "⛪", "hit_die": 8, "primary": ["WIS"],
        "saves": ["WIS", "CHA"], "armor": True,
        "features": ["حوزه الهی", "Turn Undead", "شفا"],
        "weapons": ["mace", "warhammer", "staff"],
    },
    "bard": {
        "fa": "بَرد", "emoji": "🎻", "hit_die": 8, "primary": ["CHA"],
        "saves": ["DEX", "CHA"], "armor": False,
        "features": ["الهام بَرد", "جادوی آهنگین", "بسیار استاد"],
        "weapons": ["rapier", "shortbow", "dagger"],
    },
    "ranger": {
        "fa": "جنگلبان", "emoji": "🏹", "hit_die": 10, "primary": ["DEX", "WIS"],
        "saves": ["STR", "DEX"], "armor": True,
        "features": ["دشمن محبوب", "شکارچی", "همنشین جانور"],
        "weapons": ["longbow", "shortbow", "longsword"],
    },
    "paladin": {
        "fa": "پالادین", "emoji": "🛡️", "hit_die": 10, "primary": ["STR", "CHA"],
        "saves": ["WIS", "CHA"], "armor": True,
        "features": ["حس بیماری", "Divine Smite", "Lay on Hands"],
        "weapons": ["longsword", "warhammer", "shield"],
    },
    "barbarian": {
        "fa": "بربر", "emoji": "🪓", "hit_die": 12, "primary": ["STR"],
        "saves": ["STR", "CON"], "armor": False,
        "features": ["خشم (Rage)", "دفاع بدون زره", "Reckless Attack"],
        "weapons": ["greataxe", "handaxe", "longsword"],
    },
    "sorcerer": {
        "fa": "ساحر", "emoji": "✨", "hit_die": 6, "primary": ["CHA"],
        "saves": ["CON", "CHA"], "armor": False,
        "features": ["منشأ جادویی", "نقاط ساحر", "Metamagic"],
        "weapons": ["staff", "dagger"],
    },
    "monk": {
        "fa": "راهب", "emoji": "🥋", "hit_die": 8, "primary": ["DEX", "WIS"],
        "saves": ["STR", "DEX"], "armor": False,
        "features": ["هنرهای رزمی", "Ki", "دفاع بدون زره"],
        "weapons": ["staff", "dagger"],
    },
    "druid": {
        "fa": "دروید", "emoji": "🌿", "hit_die": 8, "primary": ["WIS"],
        "saves": ["INT", "WIS"], "armor": False,
        "features": ["درویدیک", "شکل‌گیری در طبیعت (Wild Shape)"],
        "weapons": ["staff", "scimitar", "shortbow"],
    },
    "warlock": {
        "fa": "جادوگر پیمان", "emoji": "🕯️", "hit_die": 8, "primary": ["CHA"],
        "saves": ["WIS", "CHA"], "armor": False,
        "features": ["ارباب ماورایی", "Eldritch Blast", "طلسم‌های پیمان"],
        "weapons": ["staff", "dagger"],
    },
}

# ---------------- سلاح‌ها ----------------
WEAPONS = {
    "longsword": {"fa": "شمشیر بلند", "dmg": "1d8", "stat": "STR", "emoji": "⚔️"},
    "greataxe": {"fa": "تبر بزرگ", "dmg": "1d12", "stat": "STR", "emoji": "🪓"},
    "rapier": {"fa": "رپیر", "dmg": "1d8", "stat": "DEX", "emoji": "🗡️"},
    "dagger": {"fa": "خنجر", "dmg": "1d4", "stat": "DEX", "emoji": "🔪"},
    "shortbow": {"fa": "کمان کوتاه", "dmg": "1d6", "stat": "DEX", "emoji": "🏹"},
    "longbow": {"fa": "کمان بلند", "dmg": "1d8", "stat": "DEX", "emoji": "🏹"},
    "staff": {"fa": "چوب دستی", "dmg": "1d6", "stat": "STR", "emoji": "🪄"},
    "mace": {"fa": "گرز", "dmg": "1d6", "stat": "STR", "emoji": "🔨"},
    "warhammer": {"fa": "چکش جنگی", "dmg": "1d8", "stat": "STR", "emoji": "🔨"},
    "handaxe": {"fa": "تبر دستی", "dmg": "1d6", "stat": "STR", "emoji": "🪓"},
    "scimitar": {"fa": "شمشیر خمیده", "dmg": "1d6", "stat": "DEX", "emoji": "⚔️"},
    "shield": {"fa": "سپر", "dmg": "1d4", "stat": "STR", "emoji": "🛡️"},
}

# ---------------- طلسم‌ها (ساده‌شده) ----------------
SPELLS = {
    "firebolt": {"fa": "تیر آتش", "dmg": "1d10", "kind": "attack", "emoji": "🔥"},
    "magicmissile": {"fa": "موشک جادویی", "dmg": "3d4+3", "kind": "auto", "emoji": "💫"},
    "curewounds": {"fa": "مرهم زخم", "dmg": "1d8", "kind": "heal", "emoji": "💚"},
    "guidingbolt": {"fa": "تیر هدایت‌گر", "dmg": "4d6", "kind": "attack", "emoji": "🌟"},
    "eldritchblast": {"fa": "انفجار باستانی", "dmg": "1d10", "kind": "attack", "emoji": "🌑"},
    "sacredflame": {"fa": "شعله مقدس", "dmg": "1d8", "kind": "auto", "emoji": "🕯️"},
}

# ---------------- دشمنان (ساده‌شده) ----------------
MONSTERS = {
    "goblin": {"fa": "گابلین", "ac": 15, "hp": 7, "dmg": "1d6+2", "xp": 50, "cr": 0.25, "emoji": "👺"},
    "orc": {"fa": "اورک", "ac": 13, "hp": 15, "dmg": "1d12+3", "xp": 100, "cr": 0.5, "emoji": "👹"},
    "skeleton": {"fa": "اسکلت", "ac": 13, "hp": 13, "dmg": "1d6+2", "xp": 50, "cr": 0.25, "emoji": "💀"},
    "zombie": {"fa": "زامبی", "ac": 8, "hp": 22, "dmg": "1d6+1", "xp": 50, "cr": 0.25, "emoji": "🧟"},
    "wolf": {"fa": "گرگ", "ac": 13, "hp": 11, "dmg": "1d6+2", "xp": 50, "cr": 0.25, "emoji": "🐺"},
    "bandit": {"fa": "راهزن", "ac": 12, "hp": 11, "dmg": "1d8+1", "xp": 25, "cr": 0.125, "emoji": "🥷"},
    "harpy": {"fa": "هارپی", "ac": 11, "hp": 38, "dmg": "1d6+2", "xp": 200, "cr": 1, "emoji": "🦅"},
    "troll": {"fa": "ترول", "ac": 15, "hp": 84, "dmg": "2d6+4", "xp": 1800, "cr": 5, "emoji": "🧌"},
    "dragon_young": {"fa": "اژدهای جوان", "ac": 18, "hp": 110, "dmg": "2d10+4", "xp": 2900, "cr": 6, "emoji": "🐉"},
    "giant_spider": {"fa": "عنکبوت غول‌پیکر", "ac": 14, "hp": 26, "dmg": "1d8+3", "xp": 200, "cr": 1, "emoji": "🕷️"},
}

DEFAULT_WEAPON = "dagger"
