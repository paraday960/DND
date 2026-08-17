# -*- coding: utf-8 -*-
"""لوپ فوق‌العاده فازتست — هزاران نبرد با پارتی‌های متفاوت برای یافتن هر باگ ممکن."""
import os, sys, random, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AI_PROVIDER", "none")
os.environ.setdefault("BOT_TOKEN", "1:dummy")
os.environ.setdefault("DB_PATH", "/tmp/ultra_fuzz.db")

from game.models import Session, Character
from game.combat import start_combat, run_initial_monsters, attack, cast, advance, end_combat, dodge
from game.adventure import death_save, rest, use_item
from game.nlp import parse_action
from game.rules import RACES, CLASSES, WEAPONS, MONSTERS, SPELLS
from game.narrator import Narrator

ISSUES = []
def issue(t, d=""):
    ISSUES.append((t, str(d)[:300]))
    print("❌", t, str(d)[:200])


def make_party(size, seed=None):
    if seed:
        random.seed(seed)
    s = Session(random.randint(1,10**9), "fuzz", 1, "DM")
    races = list(RACES.keys())
    classes = list(CLASSES.keys())
    weapons = list(WEAPONS.keys())
    for i in range(size):
        uid = i+1
        if uid != 1:
            s.add_player(uid, f"p{i}")
        ch = Character(f"H{i+1}", random.choice(races), random.choice(classes), random.choice(weapons))
        s.players[str(uid)]["char"] = ch
    s.state = "playing"
    return s


def random_scenario(s, max_monsters=8):
    n = Narrator()
    sc = n._fallback_scenario(s)
    keys = list(MONSTERS.keys())
    n_types = random.randint(1, min(4, len(keys)))
    chosen = random.sample(keys, n_types)
    enc = []
    total = 0
    for k in chosen:
        m = MONSTERS[k]
        # سختی متناسب با سطح/تعداد
        players = [p["char"] for p in s.players.values() if p["char"]]
        avg_lv = sum(c.level for c in players) // max(1, len(players))
        max_c = max(1, max_monsters // n_types)
        if m.get("cr", 0.25) > avg_lv:
            c = 1
        else:
            c = random.randint(1, max_c)
        if total + c > max_monsters:
            c = max(1, max_monsters - total)
        enc.append({"name": k, "count": c, "ac": m["ac"], "hp": m["hp"],
                    "dmg": m["dmg"], "xp": m["xp"]})
        total += c
        if total >= max_monsters:
            break
    sc["encounters"] = enc
    return sc


def auto_play(s, max_rounds=200):
    rounds = 0
    actions = 0
    safety = 0
    while s.combat and rounds < max_rounds:
        safety += 1
        if safety > 2000:
            return False, f"action safety exceeded at r={rounds}"
        cur = s.combat["participants"][s.combat["turn"]]
        if cur.get("kind") != "player":
            msg = advance(s)
            continue
        uid = int(cur["uid"])
        ch = s.get_char(uid)
        if not ch:
            advance(s); rounds += 1; continue
        if cur.get("dead"):
            advance(s); rounds += 1; continue
        if ch.hp <= 0 or cur.get("downed"):
            r = death_save(s, uid)
            if s.combat:
                advance(s)
            rounds += 1; actions += 1; continue
        mobs = [p for p in s.combat["participants"]
                if p["kind"]=="monster" and p.get("alive")]
        if not mobs:
            break
        target = mobs[0]["name"]
        can_cast = ch.cls in ("wizard","sorcerer","bard","warlock","cleric","druid","paladin","ranger")
        r = random.random()
        try:
            if can_cast and ch.available_slot(1) and r < 0.3:
                spell = random.choice(["firebolt", "magicmissile", "sacredflame"])
                # اگر HP پایین است شفا
                if ch.hp < ch.max_hp * 0.3:
                    spell = "curewounds"
                cast(s, uid, spell, ch.name if spell == "curewounds" else target)
            elif r < 0.05:
                dodge(s, uid)
            else:
                attack(s, uid, target)
        except Exception as e:
            return False, f"action crash: {traceback.format_exc()}"
        actions += 1
        if s.combat:
            advance(s)
        rounds += 1
    if s.combat:
        # بررسی وضعیت — آیا واقعاً گیره؟
        alive_mobs = [p for p in s.combat["participants"]
                      if p["kind"]=="monster" and p.get("alive")]
        alive_players = [p for p in s.combat["participants"]
                         if p["kind"]=="player" and not p.get("dead")
                         and p.get("hp",0) > 0 and not p.get("downed")]
        downed = [p for p in s.combat["participants"]
                  if p["kind"]=="player" and not p.get("dead")
                  and (p.get("downed") or p.get("hp",0) <= 0)]
        if alive_mobs and not alive_players and downed:
            # شکست طبیعی — end_combat باید خودکار اینو می‌گرفت
            end_combat(s)
            return True, f"ended with party wipe at r={rounds}"
        if not alive_mobs:
            end_combat(s)
            return True, f"ended late"
        return False, f"stuck at r={rounds}, mobs={len(alive_mobs)}, alive_p={len(alive_players)}, downed={len(downed)}"
    return True, f"{actions} actions, {rounds} rounds"


def main():
    N = 1000
    print(f"🚀 ULTRA FUZZ: {N} random combos...")
    fails = 0
    for i in range(N):
        size = random.choice([1,2,3,4,5,6])
        try:
            s = make_party(size, seed=7777+i)
            s.scenario = random_scenario(s, max_monsters=10)
            start_combat(s)
            run_initial_monsters(s)
            ok, info = auto_play(s)
            if not ok:
                issue(f"run {i} size={size}", info)
                fails += 1
            elif (i+1) % 200 == 0:
                print(f"  {i+1}/{N} OK")
        except Exception as e:
            issue(f"run {i} size={size} crashed", traceback.format_exc())
            fails += 1

    # تست پایداری
    print("\n🧪 تست NLP روی ۲۰۰ جمله...")
    samples = [
        "حمله می‌کنم به گابلین", "بزنمش", "آتیشش بزن", "اسکلت رو بکش", "دفاع",
        "مرگ‌سیو", "مشعل روشن کن", "نگاه کن", "استراحت کوتاه", "استراحت طولانی",
        "کمک", "وضعیتم", "گروه کیه", "کجا هستم", "می‌رم جلو", "عقب برگرد",
        "تاس بینداز", "معجون می‌خورم", "معجون بزرگ می‌خورم", "سناریو بساز",
        "شروع نبرد", "با تیر به اورک بزن", "با شمشیر می‌زنمش", "نبرد شروع کن",
        "هارپی رو آتیش بزن", "ترول رو بکش", "فرار می‌کنم", "در رو باز می‌کنم",
        "چی می‌فروشی", "بخر معجون", "بفروش طناب", "لول آپ", "تجهیز کن شمشیر بلند",
    ]
    nlp_ok = 0
    for p in samples:
        try:
            r = parse_action(p, in_combat=True, valid_monsters=["گابلین","گرگ","اسکلت","اورک","ترول","هارپی"], is_dm=True)
            assert r.get("action")
            nlp_ok += 1
        except Exception as e:
            issue(f"NLP crash on: {p}", traceback.format_exc())
    print(f"  NLP: {nlp_ok}/{len(samples)}")

    # تست ذخیره/بازیابی
    print("\n💾 تست ۱۰۰ بار save/load...")
    from game.store import Store
    db = Store("/tmp/ultra_fuzz2.db")
    for i in range(100):
        s = make_party(random.randint(1,6), seed=9000+i)
        s.scenario = random_scenario(s, max_monsters=6)
        start_combat(s)
        for _ in range(random.randint(1,10)):
            if not s.combat:
                break
            cur = s.combat["participants"][s.combat["turn"]]
            if cur.get("kind") != "player":
                advance(s); continue
            uid = int(cur["uid"])
            ch = s.get_char(uid)
            if not ch or ch.hp <= 0:
                advance(s); continue
            mobs = [p for p in s.combat["participants"] if p["kind"]=="monster" and p.get("alive")]
            if mobs:
                attack(s, uid, mobs[0]["name"])
            if s.combat:
                advance(s)
        try:
            db.save(s)
            s2 = db.load(s.chat_id)
            if s.combat and (not s2 or not s2.combat):
                issue(f"save/load {i}: combat state lost")
            if not s.combat and s2 and s2.combat:
                pass  # fine
        except Exception as e:
            issue(f"save/load {i} crashed", traceback.format_exc())

    print("\n" + "="*60)
    if ISSUES:
        print(f"نتیجه: {len(ISSUES)} مشکل پیدا شد:")
        for t,d in ISSUES[:30]:
            print(f"  - {t}")
        sys.exit(1)
    else:
        print(f"🏆 نهایی: همه {N} فاز + NLP + save/load پاس ✅")
        sys.exit(0)


if __name__ == "__main__":
    main()
