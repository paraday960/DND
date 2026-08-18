# -*- coding: utf-8 -*-
"""قوانین D&D 5e — نژادها، کلاس‌ها، سلاح‌ها، توانایی‌ها، وضعیت‌ها و اکشن‌ها."""

ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
ABILITY_FA = {
    "STR": "قدرت",
    "DEX": "چابکی",
    "CON": "استقامت",
    "INT": "هوش",
    "WIS": "ادراک",
    "CHA": "جذابیت",
}

# ---------------- وضعیت‌های استاندارد D&D 5e ----------------
CONDITIONS = {
    "blinded": {"fa": "کور", "effects": ["همه رول‌های حمله و مهارت با ضعف", "حملات به تو با مزیت"]},
    "charmed": {"fa": "افسون شده", "effects": ["نمی‌توانی به افسونگر حمله کنی", "افسونگر در برابرت CHA با مزیت دارد"]},
    "deafened": {"fa": "ناشنوا", "effects": ["همه چک‌های ادراک شنوایی خودکار شکست می‌خورد"]},
    "frightened": {"fa": "ترسیده", "effects": ["همه رول‌های حمله و مهارت با ضعف وقتی منبع ترس را می‌بینی", "نمی‌توانی عمداً به سمت منبع حرکت کنی"]},
    "grappled": {"fa": "گرفتار شده", "effects": ["سرعت صفر می‌شود", "برای رهایی باید چک STR/DEX بزنی"]},
    "incapacitated": {"fa": "بی‌اقدام", "effects": ["نمی‌توانی اکشن یا بونس اکشن بگیری", "حملات به تو با مزیت"]},
    "invisible": {"fa": "نامرئی", "effects": ["حملات به تو با ضعف", "حملات تو با مزیت"]},
    "paralyzed": {"fa": "فلج", "effects": ["بی‌اقدام هستی", "همه حملات علیه تو با مزیت", "هر ضربه به تو بحرانی است"]},
    "poisoned": {"fa": "مسموم", "effects": ["همه رول‌های حمله و مهارت با ضعف"]},
    "prone": {"fa": "روی زمین افتاده", "effects": ["حملات به تو از نزدیک با مزیت", "حملات تو از دور با ضعف", "برای بلند شدن نصف سرعت می‌رود"]},
    "restrained": {"fa": "مقید شده", "effects": ["سرعت صفر", "همه حملات به تو با مزیت", "حملات تو با ضعف"]},
    "stunned": {"fa": "گیج/شکه", "effects": ["بی‌اقدام هستی", "همه حملات به تو با مزیت"]},
    "unconscious": {"fa": "بیهوش", "effects": ["بی‌اقدام، روی زمین افتاده", "همه حملات به تو با مزیت", "هر ضربه از نزدیک بحرانی است"]},
    "exhaustion": {"fa": "خستگی مفرط", "levels": {
        1: "همه چک‌های توانایی با ضعف",
        2: "همه رول‌ها با ضعف، سرعت نصف",
        3: "همه حملات و ذخیره‌ها با ضعف، ماکس HP نصف",
        4: "سرعت صفر",
        5: "ماکس HP به ۱ می‌رسد",
        6: "مرگ",
    }},
    # شرایط کوتاه‌مدت بازی ما
    "dodge": {"fa": "دفاع فعال", "effects": ["حملات به تو با ضعف تا نوبت بعد", "همه ذخیره‌های DEX با مزیت"]},
    "raging": {"fa": "خشم", "effects": ["آسیب سلاح STR +2/+3/+4 بر اساس سطح", "مقاومت در برابر آسیب کوبنده/سوراخ/برنده"]},
    "concentrating": {"fa": "در حال تمرکز طلسم", "effects": ["وقتی آسیب می‌خوری باید CON save بزنی"]},
}

# ---------------- اکشن‌های استاندارد نبرد ----------------
COMBAT_ACTIONS = {
    "attack": {"fa": "حمله", "type": "main", "desc": "حمله با سلاح یا طلسم"},
    "cast": {"fa": "انداختن طلسم", "type": "main", "desc": "طلسمی که نیاز به اکشن دارد"},
    "dash": {"fa": "دویدن", "type": "main", "desc": "سرعت حرکت در این نوبت دو برابر می‌شود"},
    "disengage": {"fa": "عقب‌نشینی امن", "type": "main", "desc": "حرکت در این نوبت حمله فرصت ایجاد نمی‌کند"},
    "dodge": {"fa": "دفاع", "type": "main", "desc": "حملات به تو با ضعف، DEX saves با مزیت تا نوبت بعد"},
    "help": {"fa": "کمک", "type": "main", "desc": "به هم‌گروهی در حمله بعدی علیه هدف مزیت می‌دهد"},
    "hide": {"fa": "پنهان شدن", "type": "main", "desc": "چک DEX (Stealth) برای مخفی شدن، حملات بعدی مزیت دارند"},
    "ready": {"fa": "آماده باش", "type": "main", "desc": "یک اکشن را برای وقوع تریگر خاص ذخیره کن (واکنش)"},
    "search": {"fa": "جستجو", "type": "main", "desc": "چک WIS (Perception) یا INT (Investigation) برای پیدا کردن چیزی"},
    "use_object": {"fa": "استفاده از شیء", "type": "main", "desc": "استفاده از یک آیتم یا تعامل با شیء"},
    "shove": {"fa": "هل دادن", "type": "main", "desc": "چک STR (Athletics) در مقابل هدف، می‌توانی هدف را به زمین بیندازی یا ۱.۵ متر عقب برانی"},
    "grapple": {"fa": "گلاپل/گرفتن", "type": "main", "desc": "چک STR (Athletics) برای گرفتن هدف، سرعتش صفر می‌شود"},
    "second_wind": {"fa": "نفس دوم", "type": "main", "class": "fighter", "desc": "یک بار در استراحت کوتاه: 1d10 + سطح fighter HP التیام"},
    "action_surge": {"fa": "اکشن اضافه", "type": "main", "class": "fighter", "desc": "یک بار در استراحت کوتاه/طولانی: یک اکشن اضافه در همین نوبت"},
}

# اکشن‌های بونس (Bonus Action)
BONUS_ACTIONS = {
    "healing_word": {"fa": "کلمه شفا", "type": "bonus", "class": ["cleric", "bard", "druid"], "spell": True},
    "cunning_action": {"fa": "اقدام حیله‌گر", "type": "bonus", "class": ["rogue"], "desc": "می‌توانی dash/disengage/hide به عنوان بونس اکشن بگیری"},
    "bardic_inspiration": {"fa": "الهام بَرد", "type": "bonus", "class": ["bard"], "desc": "یک دی الهام به هم‌گروهی می‌دهی که به یک رول بعدی اضافه کند"},
    "rage": {"fa": "خشم", "type": "bonus", "class": ["barbarian"], "desc": "وارد حالت خشم می‌شوی"},
    "flurry_of_blows": {"fa": "ضربات پیاپی", "type": "bonus", "class": ["monk"], "desc": "بعد از حمله، دو ضربه مشت اضافه بدون سلاح"},
    "patient_defense": {"fa": "دفاع صبورانه", "type": "bonus", "class": ["monk"], "desc": "به عنوان بونس اکشن دفاع می‌کنی با ۱ نقطه Ki"},
    "step_of_the_wind": {"fa": "گام باد", "type": "bonus", "class": ["monk"], "desc": "با ۱ Ki dash یا disengage به عنوان بونس اکشن + پرش دو برابر"},
    "smite": {"fa": "ضربه الهی", "type": "bonus", "class": ["paladin"], "spell": True, "desc": "بعد از ضربه با سلاح، یک جایگاه طلسم خرج می‌کنی تا آسیب تابشی اضافه بزنی"},
    "hunters_mark": {"fa": "نشان شکارچی", "type": "bonus", "class": ["ranger"], "spell": True},
    "hex": {"fa": "نفرین", "type": "bonus", "class": ["warlock"], "spell": True},
    "offhand_attack": {"fa": "حمله دست دوم", "type": "bonus", "desc": "حمله دوم با سلاح سبک (بدون پاداش توانایی به آسیب)"},
    "use_item_bonus": {"fa": "استفاده سریع آیتم", "type": "bonus", "desc": "نوشیدن معجون یا کشیدن سلاح به عنوان بونس اکشن"},
}

# جدول استاندارد DC (سختی) برای چک‌ها
DC_TABLE = {
    "very_easy": 5,
    "easy": 10,
    "medium": 15,
    "hard": 20,
    "very_hard": 25,
    "nearly_impossible": 30,
}

# برد سلاح‌ها (متر)
WEAPON_RANGES = {
    # نزدیک
    "longsword": {"type": "melee", "reach": 1.5},
    "greataxe": {"type": "melee", "reach": 1.5},
    "rapier": {"type": "melee", "reach": 1.5},
    "dagger": {"type": "melee", "reach": 1.5, "ranged": 6, "ranged_max": 18, "light": True, "thrown": True},
    "mace": {"type": "melee", "reach": 1.5},
    "warhammer": {"type": "melee", "reach": 1.5},
    "handaxe": {"type": "melee", "reach": 1.5, "ranged": 6, "ranged_max": 18, "light": True, "thrown": True},
    "scimitar": {"type": "melee", "reach": 1.5, "light": True},
    "staff": {"type": "melee", "reach": 1.5},
    "shield": {"type": "melee", "reach": 1.5},
    # دور
    "shortbow": {"type": "ranged", "ranged": 24, "ranged_max": 96},
    "longbow": {"type": "ranged", "ranged": 45, "ranged_max": 180},
}

# آسیب‌پذیری/مقاومت/ایمنی بر اساس نژاد
RACE_DAMAGE_RESISTANCES = {
    "tiefling": {"resist": ["fire"]},
    "dwarf": {"resist": ["poison"]},
    "dragonborn": {"breath": True},
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

# ---------------- طلسم‌ها (ساده‌شده D&D 5e) ----------------
SPELLS = {
    # Cantrips (سطح ۰، بدون نیاز به slot)
    "firebolt": {"fa": "تیر آتش", "level": 0, "dmg": "1d10", "kind": "attack_ranged", "damage_type": "fire", "emoji": "🔥"},
    "eldritchblast": {"fa": "انفجار باستانی", "level": 0, "dmg": "1d10", "kind": "attack_ranged", "damage_type": "force", "emoji": "🌑"},
    "sacredflame": {"fa": "شعله مقدس", "level": 0, "dmg": "1d8", "kind": "save_dex", "damage_type": "radiant", "emoji": "🕯️", "save_dc_stat": "DEX"},
    "rayoffrost": {"fa": "اشعه یخبندان", "level": 0, "dmg": "1d8", "kind": "attack_ranged", "damage_type": "cold", "emoji": "❄️"},
    "poisonspray": {"fa": "اسپری سم", "level": 0, "dmg": "1d12", "kind": "save_con", "damage_type": "poison", "emoji": "☠️", "range": 3},
    "minorillusion": {"fa": "توهم کوچک", "level": 0, "kind": "utility", "emoji": "🎭"},
    "prestidigitation": {"fa": "دست حقه", "level": 0, "kind": "utility", "emoji": "✨"},
    # طلسم سطح ۱
    "magicmissile": {"fa": "موشک جادویی", "level": 1, "dmg": "3d4+3", "kind": "auto", "damage_type": "force", "emoji": "💫"},
    "curewounds": {"fa": "مرهم زخم", "level": 1, "heal": "1d8", "kind": "heal_touch", "emoji": "💚", "action": "main"},
    "healingword": {"fa": "کلمه شفا", "level": 1, "heal": "1d4+mod", "kind": "heal_ranged", "emoji": "💚", "action": "bonus", "range": 18},
    "guidingbolt": {"fa": "تیر هدایت‌گر", "level": 1, "dmg": "4d6", "kind": "attack_ranged", "damage_type": "radiant", "emoji": "🌟"},
    "shield": {"fa": "سپر جادویی", "level": 1, "kind": "defense_bonus", "emoji": "🛡️", "action": "reaction", "effect": "+5 AC تا شروع نوبت بعد"},
    "magearmor": {"fa": "زره جادویی", "level": 1, "kind": "buff_long", "emoji": "🧙", "effect": "پایه AC 13 + DEX به مدت ۸ ساعت"},
    "sleep": {"fa": "خواب", "level": 1, "kind": "save_wis_aoe", "emoji": "💤", "hp_total": "5d8", "effect": "بیهوش کردن تا بیدار شدن/آسیب"},
    "holdperson": {"fa": "نگه داشتن شخص", "level": 2, "kind": "save_wis", "emoji": "🫵", "effect": "فلج کردن هدف به مدت تمرکز"},
    "fireball": {"fa": "گوی آتش", "level": 3, "dmg": "8d6", "kind": "save_dex_aoe", "damage_type": "fire", "emoji": "💥", "range": 45, "aoe_radius": 6},
    "invisibility": {"fa": "نامرئی شدن", "level": 2, "kind": "buff_concentration", "emoji": "👻", "effect": "نامرئی تا حمله/طلسم یا تمرکز شکست"},
    "mistystep": {"fa": "گام مه", "level": 2, "kind": "teleport_bonus", "emoji": "💨", "action": "bonus", "range": 9},
    "spiritualweapon": {"fa": "سلاح روحانی", "level": 2, "dmg": "1d8+mod", "kind": "bonus_attack", "emoji": "🔨", "action": "bonus", "damage_type": "force"},
    "huntersmark": {"fa": "نشان شکارچی", "level": 1, "kind": "buff_mark", "emoji": "🏹", "action": "bonus", "effect": "+1d6 آسیب به هدف علامت‌گذاری شده"},
    "hex": {"fa": "نفرین", "level": 1, "kind": "buff_mark", "emoji": "👁️", "action": "bonus", "effect": "+1d6 نکروز به هدف، یک توانایی با ضعف"},
    "curewounds_mass": {"fa": "مرهم زخم گروهی", "level": 3, "heal": "3d8+mod", "kind": "heal_aoe", "emoji": "💚", "range": 18, "aoe": 6},
    "inflictwounds": {"fa": "ایجاد زخم", "level": 1, "dmg": "3d10", "kind": "attack_melee", "damage_type": "necrotic", "emoji": "💔"},
    "burninghands": {"fa": "دستان سوزان", "level": 1, "dmg": "3d6", "kind": "save_dex_cone", "damage_type": "fire", "emoji": "🔥", "cone": 4.5},
    "faeriefire": {"fa": "آتش پری", "level": 1, "kind": "save_dex_aoe", "emoji": "🌈", "effect": "همه در منطقه قابل دیدن، حملات به آن‌ها مزیت دارد"},
    "entangle": {"fa": "گیر انداختن", "level": 1, "kind": "save_str_aoe", "emoji": "🌿", "effect": "مقید شدن توسط گیاهان"},
    # تنفس اژدها (Dragonborn)
    "dragonbreath": {"fa": "نفس اژدها", "level": 0, "kind": "save_dex_cone", "damage_type": "fire", "dmg": "2d6", "emoji": "🐲", "cone": 4.5, "race": "dragonborn", "per_rest": "long"},
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

# ---------------- مهارت‌ها و آیتم‌ها ----------------
SKILLS = {
    "athletics": {"fa": "ورزش", "ability": "STR"},
    "acrobatics": {"fa": "آکروباتیک", "ability": "DEX"},
    "stealth": {"fa": "مخفی‌کاری", "ability": "DEX"},
    "sleight": {"fa": "دستی‌کاری", "ability": "DEX"},
    "arcana": {"fa": "دانش جادو", "ability": "INT"},
    "history": {"fa": "تاریخ", "ability": "INT"},
    "investigation": {"fa": "تحقیق", "ability": "INT"},
    "nature": {"fa": "طبیعت", "ability": "INT"},
    "religion": {"fa": "مذهب", "ability": "INT"},
    "animal": {"fa": "مراقبت از حیوانات", "ability": "WIS"},
    "insight": {"fa": "درک نیت", "ability": "WIS"},
    "medicine": {"fa": "پزشکی", "ability": "WIS"},
    "perception": {"fa": "ادراک", "ability": "WIS"},
    "survival": {"fa": "بقا", "ability": "WIS"},
    "deception": {"fa": "فریب", "ability": "CHA"},
    "intimidation": {"fa": "ترساندن", "ability": "CHA"},
    "performance": {"fa": "اجرا", "ability": "CHA"},
    "persuasion": {"fa": "متقاعدسازی", "ability": "CHA"},
}

DEFAULT_PROFICIENCIES = {
    "fighter": ["athletics", "intimidation"], "rogue": ["stealth", "sleight", "investigation"],
    "wizard": ["arcana", "history"], "cleric": ["medicine", "religion"],
    "bard": ["performance", "persuasion"], "ranger": ["nature", "survival"],
    "paladin": ["athletics", "persuasion"], "barbarian": ["athletics", "survival"],
    "sorcerer": ["arcana", "deception"], "monk": ["acrobatics", "insight"],
    "druid": ["animal", "nature"], "warlock": ["arcana", "deception"],
}

DEFAULT_WEAPON = "dagger"
