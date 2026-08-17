# -*- coding: utf-8 -*-
"""پارسر دستورات زبان طبیعی فارسی — جملات را به اکشن بازی تبدیل می‌کند.

مثال‌ها:
  «حمله می‌کنم به گابلین»  → attack
  «با تیر به گرگ بزن»      → attack گرگ
  «مشعل روشن کن»            → env:torch
  «اسکلت رو آتیش بزن»      → cast firebolt اسکلت
  «دفاع می‌کنم»            → dodge
  «مرگ‌سیو»                 → deathsave
  "نگاه کن"                 → look
"""
import re

# حروف اضافه و پیشوند/پسوند که باید از نام هدف حذف شوند
_STOP = {
    "به", "با", "را", "رو", "روی", "بر", "برای", "از", "که", "این", "اون", "آن",
    "من", "تو", "او", "ما", "شما", "ها", "هام", "هامون",
}

# افعال و کلیدواژه‌ها
ATTACK_WORDS = ["حمله", "بزن", "بکوب", "بکش", "کشت", "ضربت", "شمشیر", "تبر", "کمان",
               "تیر", "خنجر", "حمله‌ور", "هجوم", "شلیک", "بنداز", "درگیری", "بجنگ",
               "غافلگیر", "می‌زنم", "میزنم", "حمله‌کن", "حمله می‌کنم", "بزنمش",
               "بکشمش", "بکشم", "می‌کشم", "نابود", "از پای دربیار", "از پا در بیار",
               "حمله‌ور شو"]
DODGE_WORDS = ["دفاع", "محافظت", "سنگر", "جاخالی", "جا خالی", "سپر", "بلاک", "دفاع‌کن",
               "دفاع می‌کنم", "جاخالی بده"]
CAST_WORDS = ["طلسم", "جادو", "شعله", "آتیش", "آتش", "آذرخش", "شفا", "مداوا", "درمان",
              "موشک", "انفجار", "یخ", "نور", "جادوگری", "آتش بزن", "آتیش بزن",
              "یخ بزن", "بسوزون", "بسوزان"]
SKIP_WORDS = ["رد", "عبور", "نوبت", "ردشو", "رد می‌شم", "صرف‌نظر", "بگذر",
              "رد کن", "نوبت بعدی"]
DEATH_WORDS = ["مرگ‌سیو", "مرگ سیو", "مرگ سیو", "نجات", "پایدار", "deathsave",
               "نجاتم بده", "نجات بده"]
LOOK_WORDS = ["نگاه", "بررسی", "جستجو", "ببین", "بنگر", "تماشا", "دقت", "یافت",
              "پیدا", "گوش", "بشنو", "صدا", "بو", "لمس"]
TORCH_WORDS = ["مشعل", "چراغ", "فانوس", "روشن", "افروز", "آتش روشن", "آتیش روشن",
               "مشعل روشن", "نور انداز", "نور بنداز"]
MOVE_WORDS = ["برو", "حرکت", "ادامه", "پیش", "جلو", "وارد", "خروج", "فرار",
              "بیا بریم", "راه بیفت", "بریم"]
REST_WORDS = ["استراحت", "کمپ", "استراحت‌کن", "چادر", "بخواب", "نفس", "استراحت کن",
              "کمپ بزن"]
SCENARIO_WORDS = ["سناریو", "ماجرا بساز", "شروع ماجرا", "سناریو بساز",
                  "ماجرای جدید", "ماجرای تازه"]
COMBAT_WORDS = ["نبرد", "نبرد شروع", "بجنگ", "درگیری", "شروع جنگ", "حمله کن",
                "بکششون", "حمله‌کن", "حمله ور"]
HELP_WORDS = ["راهنما", "کمک", "چی‌کار", "دستور", "چیکار کنم", "کمکم کن"]
SHEET_WORDS = ["وضعیتم", "کاراکترم", "مشخصاتم", "شیت", "برگه", "خودم",
               "چی دارم", "وضعیت من"]
PARTY_WORDS = ["گروه", "تیم", "پارتی", "دیگه کیه", "بازیکنا", "همه",
               "گروه ما", "تیم ما"]


def _normalize(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    # نیم‌فاصله را به فاصله تبدیل کن
    t = t.replace("\u200c", " ")
    # یک‌دست کردن اعداد فارسی
    mapping = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    t = t.translate(mapping)
    # حذف علائم
    t = re.sub(r"[!.,?؟!:;\"'()\[\]{}«»]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _contains_any(text: str, words) -> bool:
    # کلمات را هم نیم‌فاصله‌زدایی کن تا با متن نرمال‌شده تطبیق داشته باشند
    return any(_normalize(w) in text for w in words)


def _extract_target(text: str, valid_monsters=None) -> str:
    """نام هدف را از جمله استخراج می‌کند — نام را قبل از فعل/حرف اضافه پیدا می‌کند."""
    if not text:
        return ""
    # اگر نام هیولا مستقیم در متن هست، همان را برگردان
    if valid_monsters:
        for m in valid_monsters:
            if m in text:
                return m
        # تطابق فازی
        for token in text.split():
            for m in valid_monsters:
                if token and len(token) >= 3 and (token in m or m in token):
                    return m
    # استخراج بر اساس الگو: «... رو/را ...» یا «به ...»
    patterns = [
        r"(.+?)\s*(?:را|رو|روی)\s*(?:با\s+\S+\s+)?(?:می\s*زن|بزن|بکوب|بکش|شلیک|آتیش|حمله|بنداز)",
        r"(?:به|با)\s+(.+?)\s*(?:می\s*زن|بزن|بکوب|بکش|شلیک|آتیش|حمله|بنداز)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            cand = m.group(1).strip()
            tokens = [t for t in cand.split() if t not in _STOP]
            cand = " ".join(tokens)
            if cand:
                return cand
    # اگر ضمیر «مش/ش/اونو» دیده شد، آخرین هدف سناریو
    if re.search(r"\b(مش|ش|اونو|اون|همون|این)\b", text):
        return ""
    # آخر اسم قبل از فعل
    tokens = text.split()
    while tokens and tokens[-1] in ("بزن", "بکوب", "بکش", "می‌زنم", "میزنم",
                                     "کنم", "کن", "بنداز", "شلیک", "بده", "هستم",
                                     "می‌کنم", "میکنم", "برم"):
        tokens.pop()
    if tokens:
        cand = " ".join(t for t in tokens if t not in _STOP)
        return cand
    return ""


def parse_action(text: str, in_combat: bool = False, has_char: bool = True,
                valid_monsters=None, is_dm: bool = False, downed: bool = False):
    """یک دستور طبیعی را به (action, target, extra) تبدیل می‌کند.
    خروجی: dict با کلید action و در صورت نیاز target
      action ∈ attack, cast, dodge, skip, deathsave, torch, look, rest,
              scenario, sheet, party, help, move, narrate
    """
    if not text:
        return {"action": "narrate"}
    t = _normalize(text)

    # دستورات کوتاه با اسلش (مستقیم)
    if t.startswith("/"):
        return {"action": "command", "text": text}

    # ۱) مرگ‌سیو (اولویت بالا)
    if _contains_any(t, DEATH_WORDS):
        return {"action": "deathsave"}

    # ۲) کمک و وضعیت
    if _contains_any(t, HELP_WORDS) and len(t) < 30:
        return {"action": "help"}
    if _contains_any(t, SHEET_WORDS) and len(t) < 30:
        return {"action": "sheet"}
    if _contains_any(t, PARTY_WORDS) and len(t) < 30:
        return {"action": "party"}

    # ۳) ساخت سناریو توسط DM
    if is_dm and (_contains_any(t, SCENARIO_WORDS) or
                  ("سناریو" in t and ("بساز" in t or "جدید" in t or "می‌خوام" in t))):
        return {"action": "scenario"}

    # ۴) در نبرد
    if in_combat:
        if _contains_any(t, DODGE_WORDS) and len(t) < 40:
            return {"action": "dodge"}
        if _contains_any(t, SKIP_WORDS) and len(t) < 25:
            return {"action": "skip"}
        if _contains_any(t, CAST_WORDS):
            spell = _detect_spell(t)
            target = _extract_target(t, valid_monsters)
            return {"action": "cast", "spell": spell, "target": target}
        if _contains_any(t, ATTACK_WORDS):
            target = _extract_target(t, valid_monsters)
            return {"action": "attack", "target": target}
    else:
        # خارج از نبرد: دستور شروع نبرد
        if is_dm and _contains_any(t, COMBAT_WORDS):
            return {"action": "combat"}

    # ۵) استراحت
    if _contains_any(t, REST_WORDS) and len(t) < 30:
        kind = "long" if ("طولانی" in t or "بلند" in t or "شب" in t) else "short"
        return {"action": "rest", "kind": kind}

    # ۶) مشعل روشن کردن
    if _contains_any(t, TORCH_WORDS) and (
        _contains_any(t, ["روشن", "افروز", "بزن", "آتش"]) or len(t) <= 6
    ):
        return {"action": "torch"}

    # ۶.۵) شروع نبرد (حتی در حالت نبرد برای سازگاری)
    if is_dm and _contains_any(t, COMBAT_WORDS):
        if not in_combat:
            return {"action": "combat"}
        return {"action": "attack", "target": ""}

    # ۷) نگاه و بررسی
    if _contains_any(t, LOOK_WORDS) and len(t) < 40:
        return {"action": "look"}

    # ۸) حرکت/ادامه
    if _contains_any(t, MOVE_WORDS) and len(t) < 30:
        return {"action": "narrate", "text": t}

    # ۹) هر چیز دیگر → روایت توسط AI
    return {"action": "narrate", "text": t}


def _detect_spell(text: str) -> str:
    """طلسم را از متن تشخیص می‌دهد."""
    if any(w in text for w in ["شفا", "مداوا", "درمان", "معالج"]):
        return "curewounds"
    if any(w in text for w in ["آتیش", "آتش", "شعله"]):
        return "firebolt"
    if any(w in text for w in ["موشک", "پرتابه"]):
        return "magicmissile"
    if any(w in text for w in ["نور مقدس", "شعله مقدس"]):
        return "sacredflame"
    if any(w in text for w in ["انفجار", "باستانی", "تاریک"]):
        return "eldritchblast"
    if any(w in text for w in ["ستاره", "هدایت"]):
        return "guidingbolt"
    return "firebolt"  # پیش‌فرض


# فرهنگ نام هیولاها: فارسی → کلید
MONSTER_FA = {
    "گابلین": "goblin", "گابلینا": "goblin", "گابلین‌ها": "goblin",
    "اورک": "orc", "اورک‌ها": "orc", "اورکها": "orc",
    "اسکلت": "skeleton", "اسکلت‌ها": "skeleton", "اسکلتها": "skeleton",
    "زامبی": "zombie", "زامبی‌ها": "zombie",
    "گرگ": "wolf", "گرگ‌ها": "wolf", "گرگها": "wolf",
    "راهزن": "bandit", "راهزنان": "bandit", "راهزن‌ها": "bandit",
    "هارپی": "harpy", "هارپی‌ها": "harpy",
    "ترول": "troll", "ترول‌ها": "troll",
    "عنکبوت": "giant_spider", "عنکبوت غول": "giant_spider",
    "اژدها": "dragon_young", "اژدهای": "dragon_young",
}
