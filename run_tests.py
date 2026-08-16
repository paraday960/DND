# -*- coding: utf-8 -*-
"""تست سریع موتور بازی — اجرا: python run_tests.py"""
import os
import sys

os.environ.setdefault("AI_PROVIDER", "none")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.dice import roll_expression, roll_advantage, roll_disadvantage, DiceError
from game.models import Character, Session
from game.combat import start_combat, advance, attack, cast, end_combat
from game.narrator import Narrator
from game.rules import ability_mod, level_from_xp

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {extra}")


print("🎲 تست تاس...")
r = roll_expression("2d6+3")
check("2d6+3", 5 <= r["total"] <= 15 and r["count"] == 2 and r["mod"] == 3, str(r))
r = roll_expression("d20")
check("d20", 1 <= r["total"] <= 20, str(r))
r = roll_advantage()
check("advantage", 1 <= r["total"] <= 20)
r = roll_disadvantage()
check("disadvantage", 1 <= r["total"] <= 20)
try:
    roll_expression("xyz")
    check("خطای عبارت نامعتبر", False)
except DiceError:
    check("خطای عبارت نامعتبر", True)

print("🧙 تست ساخت کاراکتر...")
ch = Character(name="آرین", race="elf", cls="rogue", weapon="rapier")
check("نژاد/کلاس", ch.race == "elf" and ch.cls == "rogue")
check("پاداش نژادی DEX", ch.abilities["DEX"] >= 10)
check("AC معقول", 10 <= ch.ac <= 20, f"AC={ch.ac}")
check("HP مثبت", ch.hp > 0, f"HP={ch.hp}")
check("بونوس حمله", ch.attack_bonus() >= 0)
check("sheet_text", "آرین" in ch.sheet_text())
check("level_from_xp(300)=2", level_from_xp(300) == 2)
check("ability_mod(18)=4", ability_mod(18) == 4)
ch.xp = 310
check("can_level_up", ch.can_level_up())
info = ch.level_up()
check("level_up", info["new"] == 2 and ch.level == 2 and ch.max_hp > 0)

print("💾 تست ذخیره‌سازی...")
from game.store import Store
store = Store("/tmp/test_dnd.db")
s = Session(chat_id=111, name="تست", dm_id=1, dm_name="DM")
s.add_player(2, "بازیکن")
s.players["2"]["char"] = ch
store.save(s)
s2 = store.load(111)
check("بازیابی جلسه", s2 and s2.code == s.code and s2.players["2"]["char"].name == "آرین")
check("find_by_code", store.find_by_code(s.code) is not None)
s3 = Session(chat_id=222, name="تست۲", dm_id=1, dm_name="DM")
for i in range(9):
    s3.add_player(100 + i, f"p{i}")
check("ظرفیت ۸ نفر", len(s3.players) == 8)

print("⚔️ تست نبرد...")
s4 = Session(chat_id=333, name="نبرد", dm_id=1, dm_name="DM")
c1 = Character(name="آرین", race="human", cls="fighter", weapon="longsword")
s4.players["1"]["char"] = c1
s4.scenario = {
    "encounters": [{"name": "goblin", "count": 2, "ac": 15, "hp": 7, "dmg": "1d6+2", "xp": 50}]
}
text = start_combat(s4)
check("شروع نبرد", s4.state == "combat" and len(s4.combat["participants"]) == 3, text)
# نوبت بازیکن → حمله
part = s4.combat["participants"]
player_turn = next((i for i, p in enumerate(part) if p["kind"] == "player"), None)
if player_turn is not None:
    s4.combat["turn"] = player_turn
    res = attack(s4, 1, "گابلین")
    check("حمله", "آرین" in res and ("اصابت" in res or "خطا" in res), res)
    adv = advance(s4)
    check("advance بعد از حمله", len(adv) > 0)
# پایان نبرد
for p in s4.combat["participants"]:
    if p["kind"] == "monster":
        p["alive"] = False
res = end_combat(s4)
check("پایان نبرد و XP", "XP" in res and s4.combat is None, res)

print("🧠 تست دانجن‌مستر (آفلاین)...")
n = Narrator()
check("fallback سناریو", n.scenario(s4).get("title"))
check("fallback روایت", "روایت" in n._fallback_narrate(s4, "در را باز می‌کنم"))

print(f"\n{'='*40}\nنتیجه: {PASS} ✅ | {FAIL} ❌")
sys.exit(1 if FAIL else 0)
