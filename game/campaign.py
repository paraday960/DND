# -*- coding: utf-8 -*-
"""سیستم کمپین چندمرحله‌ای — داستان را در چند فصل پیش می‌برد."""
import random

# قالب فصل‌های کمپین
CHAPTER_TEMPLATES = [
    {
        "title": "فصل ۱: تماس برای ماجراجویی",
        "hook": "در مهمان‌سرای دهکده، یک پی‌رسان پیر نامه‌ای فوری به دست شما می‌رساند.",
        "goal": "با فرستاده دیدار کن و سرنخ اولین ماموریت را پیدا کن.",
        "enemy_scale": 0.6,  # ضریب بودجه نبرد
        "next_clue": "روستای متروک در دامنه کوه",
    },
    {
        "title": "فصل ۲: راهزنان جاده",
        "hook": "جاده‌ای که به مقصد می‌رسد توسط راهزنانی تسخیر شده.",
        "goal": "اردوگاه راهزنان را در هم بکوب.",
        "enemy_scale": 0.8,
        "next_clue": "یک نقشه قدیمی که به ورودی معبد اشاره دارد",
    },
    {
        "title": "فصل ۳: معبد فراموش‌شده",
        "hook": "در معبد تاریک، موجودات مرده پاسدار گنجی باستانی هستند.",
        "goal": "به ژرفای معبد برسید و دشمن اصلی این فصل را شکست دهید.",
        "enemy_scale": 1.0,
        "next_clue": "طلسمی که نام لانه اژدها را فاش می‌کند",
    },
    {
        "title": "فصل ۴: پنجه هیولا",
        "hook": "هیولایی بزرگ از دل کوه بیرون آمده و روستاها را ویران می‌کند.",
        "goal": "با هیولای این فصل روبه‌رو شوید.",
        "enemy_scale": 1.2,
        "next_clue": "مختصات لانه نهایی",
    },
    {
        "title": "فصل ۵: رویارویی نهایی",
        "hook": "در دل تاریکی، مغز متفکر همه‌چیز منتظر شماست.",
        "goal": "دشمن نهایی را شکست دهید و ماجرا را به پایان برسانید.",
        "enemy_scale": 1.5,
        "next_clue": None,
    },
]


def make_campaign():
    """یک کمپین جدید با ۵ فصل بساز."""
    return {
        "chapter": 0,  # صفر یعنی هنوز شروع نشده
        "chapters": [dict(t) for t in CHAPTER_TEMPLATES],
        "notes": [],
        "choices": [],
    }


def start_chapter(campaign, session, narrator):
    """فصل فعلی را شروع کن و سناریوی آن را بساز."""
    if campaign["chapter"] >= len(campaign["chapters"]):
        return None
    chapter = campaign["chapters"][campaign["chapter"]]
    # سناریوی مختص فصل
    scale = chapter.get("enemy_scale", 1.0)
    prompt = chapter.get("title", "") + " — " + chapter.get("goal", "")
    # narrator.scenario را با بودجه کمتر صدا بزن
    sc = narrator.scenario(session, prompt)
    if sc:
        sc["chapter_title"] = chapter["title"]
        sc["chapter_goal"] = chapter["goal"]
    return sc


def advance_chapter(campaign, outcome="victory"):
    """فصل را جلو ببر. خروجی: پیام متنی."""
    if campaign["chapter"] >= len(campaign["chapters"]) - 1:
        if outcome == "victory":
            return ("🏆 **پیروزی نهایی!** شما تمام فصل‌ها را گذراندید و "
                    "دشمن را شکست دادید. نام شما در تاریخ این سرزمین ثبت می‌شود.")
        return "💀 شکست در فصل نهایی..."
    chapter = campaign["chapters"][campaign["chapter"]]
    campaign["chapter"] += 1
    next_ch = campaign["chapters"][campaign["chapter"]]
    return (f"📖 **پایان فصل:** {chapter['title']}\n\n"
            f"سرنخ: {chapter.get('next_clue', '—')}\n\n"
            f"➡️ **فصل بعدی:** {next_ch['title']}\n"
            f"_{next_ch['hook']}_")


def chapter_status(campaign) -> str:
    if campaign["chapter"] >= len(campaign["chapters"]):
        return "🏆 کمپین تمام شده."
    ch = campaign["chapters"][campaign["chapter"]]
    return f"📖 {ch['title']}\n🎯 هدف: {ch['goal']}"
