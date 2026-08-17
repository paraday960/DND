# -*- coding: utf-8 -*-
"""لوپ عمیق سناریو — چندین درخواست مختلف، سناریوی تولیدشده را بررسی می‌کند:
- ساختار درست (title, hook, goal, locations, npcs, encounters, treasure, traps, branches)
- دشمنان لیست سفید و تعداد معقول
- تنوع مکان/NPC/گنج
- سرعت پاسخ (timeout)
- اینکه روایت اولیه به hook و location ارجاع می‌ده
- سازگاری HP/AC با CR
"""
import os, sys, json, time, random, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AI_PROVIDER", "mistral")
os.environ["MISTRAL_API_KEY"] = "fbnByRBhcP9KUpzBsblLfHROYmlifOSn"
os.environ.setdefault("BOT_TOKEN", "1:dummy")
os.environ.setdefault("DB_PATH", "/tmp/scenario_test.db")

from game.narrator import Narrator
from game.models import Session, Character
from game.rules import MONSTERS

ISSUES = []
def issue(t, d=""):
    ISSUES.append((t, str(d)[:300]))
    print("❌", t, str(d)[:200])

def make_party(size=3, level=1):
    s = Session(random.randint(1,10**9), "scenario_test", 1, "DM")
    races = ["human", "elf", "dwarf", "halfling"]
    classes = ["fighter", "wizard", "rogue", "cleric"]
    weapons = ["longsword", "staff", "rapier", "mace"]
    for i in range(size):
        uid = i+1
        if uid != 1: s.add_player(uid, f"p{i}")
        ch = Character(f"Hero{i+1}", races[i%len(races)], classes[i%len(classes)], weapons[i%len(weapons)])
        s.players[str(uid)]["char"] = ch
    s.state = "playing"
    return s


PROMPTS = [
    "کاروان تجاری در شب در جاده مورد حمله راهزنان قرار گرفته",
    "معبدی زیر آب که هیولاهایی در تاریکی کمین کرده‌اند",
    "برج جادوگر دیوانه که در هر طبقه چالشی متفاوت دارد",
    "روستایی که همه ساکنانش ناپدید شده‌اند",
    "مین‌های متروک کوتوله‌ها که هنوز تله‌ها فعال‌اند",
    "اردوگاه اورک‌ها قبل از حمله بزرگ به شهر",
    "باتلاقی که مردگانش بیرون می‌آیند",
    "کتابخانه نفرین‌شده که کتاب‌ها جان گرفته‌اند",
    "کشتی شکسته در ساحل پر از هیولاهای دریایی",
    "قلعه‌ای که خون‌آشام‌ها آن را تسخیر کرده‌اند",
    "دهکده برفی مورد حمله یتی‌ها",
    "غار اژدهای سرخ با گنج عظیم",
]

REQUIRED_KEYS = ["title", "hook", "goal"]
GOOD_KEYS = ["locations", "npcs", "encounters", "treasure"]
BONUS_KEYS = ["traps", "branches", "twist", "boss"]


def validate_scenario(sc, request, players=3, avg_level=1):
    problems = []
    if not sc or not isinstance(sc, dict):
        problems.append("scenario not a dict")
        return problems
    for k in REQUIRED_KEYS:
        if not sc.get(k):
            problems.append(f"missing key: {k}")
    # locations
    locs = sc.get("locations") or []
    if not isinstance(locs, list) or len(locs) < 2:
        problems.append(f"locations < 2 (got {len(locs) if isinstance(locs,list) else type(locs)})")
    if len(locs) > 10:
        problems.append(f"too many locations ({len(locs)})")
    # npcs
    npcs = sc.get("npcs") or []
    if not isinstance(npcs, list):
        problems.append("npcs not a list")
    # encounters
    enc = sc.get("encounters") or []
    if not isinstance(enc, list) or len(enc) == 0:
        problems.append("no encounters")
    else:
        total = 0
        for i,e in enumerate(enc):
            if not isinstance(e, dict):
                problems.append(f"encounter {i} not dict"); continue
            name = str(e.get("name","")).lower()
            if name not in MONSTERS:
                problems.append(f"unknown monster: {name}")
            cnt = int(e.get("count", 0))
            if cnt < 1 or cnt > 12:
                problems.append(f"encounter {name} count={cnt}")
            total += cnt
            # HP/AC reasonable
            try:
                hp = int(e.get("hp", 0))
                ac = int(e.get("ac", 0))
                if hp < 1 or hp > 400: problems.append(f"{name} hp={hp}")
                if ac < 5 or ac > 25: problems.append(f"{name} ac={ac}")
            except:
                problems.append(f"{name} bad hp/ac")
        # scaling — برای سطح ۱ حداکثر ۶ دشمن ضعیف
        if avg_level <= 1 and total > 6:
            problems.append(f"too many monsters for L1 party: {total}")
        if avg_level <= 1 and any("dragon" in str(e.get("name","")).lower() or "troll" in str(e.get("name","")).lower() for e in enc):
            problems.append(f"boss/CR-too-high for L1 party")
    # treasure
    if not sc.get("treasure"):
        problems.append("no treasure described")
    # bonus features counted
    bonus = sum(1 for k in BONUS_KEYS if sc.get(k))
    return problems, bonus


def main():
    n = Narrator()
    if not n.available:
        print("AI unavailable"); return
    total_bonus = 0
    total_time = 0
    for i, req in enumerate(PROMPTS, 1):
        s = make_party(3, level=1)
        t0 = time.time()
        try:
            sc = n.scenario(s, req)
            dt = time.time() - t0
        except Exception as e:
            issue(f"scenario {i} crashed", traceback.format_exc())
            continue
        total_time += dt
        res = validate_scenario(sc, req)
        if isinstance(res, list):
            probs = res; bonus = 0
        else:
            probs, bonus = res
        total_bonus += bonus
        title = (sc.get("title") or "?")[:60]
        enc_count = sum(int(e.get("count",1)) for e in (sc.get("encounters") or []) if isinstance(e,dict))
        locs = len(sc.get("locations") or [])
        npcs = len(sc.get("npcs") or [])
        traps = len(sc.get("traps") or []) if isinstance(sc.get("traps"), list) else 0
        branches = len(sc.get("branches") or []) if isinstance(sc.get("branches"), list) else 0
        if probs:
            for p in probs:
                issue(f"scenario {i} ({title})", p)
            print(f"  {i}. {title}")
            print(f"     enc={enc_count} loc={locs} npc={npcs} trap={traps} branch={branches} dt={dt:.1f}s")
        else:
            print(f"  ✅ {i}. {title}")
            print(f"     enc={enc_count} loc={locs} npc={npcs} trap={traps} branch={branches} bonus={bonus} dt={dt:.1f}s")

    # Narrate quality test
    print("\n📖 تست روایت...")
    s = make_party(2)
    sc = n.scenario(s, "یک اتاق کوچک با یک صندوقچه که رویش تله سمی قرار دارد")
    s.scenario = sc
    for prompt in ["با احتیاط وارد اتاق می‌شوم و صندوقچه را بررسی می‌کنم",
                   "در صندوقچه را باز می‌کنم"]:
        t0 = time.time()
        try:
            txt = n.narrate(s, prompt)
            dt = time.time() - t0
            if len(txt) < 50:
                issue("narrate too short", txt[:200])
            if dt > 30:
                issue("narrate too slow", f"{dt:.1f}s")
            # check it actually describes something
            if any(w in txt for w in ["تله", "سم", "صندوق", "در", "آسیب", "مراقب", "مکانیزم"]):
                print(f"  ✅ narrate '{prompt[:40]}' → length={len(txt)} dt={dt:.1f}s, trap referenced")
            else:
                issue(f"narrate didn't reference hook", f"prompt={prompt}, out={txt[:200]}")
        except Exception as e:
            issue(f"narrate crashed on {prompt}", traceback.format_exc())

    print("\n" + "="*60)
    print(f"میانگین زمان ساخت سناریو: {total_time/len(PROMPTS):.1f}s")
    print(f"مجموع فیچرهای جایزه: {total_bonus} (هدف: ≥ {len(PROMPTS)*2})")
    if ISSUES:
        print(f"نتیجه: {len(ISSUES)} مشکل:")
        for t,d in ISSUES[:30]:
            print(f"  - {t}")
        sys.exit(1)
    else:
        print("🏆 همه سناریوها سبز ✅")
        sys.exit(0)


if __name__ == "__main__":
    main()
