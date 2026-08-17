# -*- coding: utf-8 -*-
"""لوپ فشرده: صدها سناریو/حزب/نبرد با seedهای متفاوت برای کشتن باگ."""
import os, sys, random, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AI_PROVIDER", "none")
os.environ.setdefault("BOT_TOKEN", "1:dummy")
os.environ.setdefault("DB_PATH", "/tmp/fuzz_test.db")

from game.models import Session, Character
from game.combat import start_combat, run_initial_monsters, attack, cast, advance, end_combat, dodge
from game.adventure import death_save, rest
from game.nlp import parse_action
from game.rules import RACES, CLASSES, WEAPONS, MONSTERS
from game.narrator import Narrator

ISSUES = []
def issue(t, d=""):
    ISSUES.append((t, d))
    print("❌", t, str(d)[:200])

def make_party(size, seed=None):
    if seed: random.seed(seed)
    s = Session(random.randint(1,10**9), "fuzz", 1, "DM")
    races = list(RACES.keys())
    classes = list(CLASSES.keys())
    weapons = list(WEAPONS.keys())
    for i in range(size):
        uid = i+1
        if uid != 1: s.add_player(uid, f"p{i}")
        ch = Character(f"Hero{i+1}", random.choice(races), random.choice(classes), random.choice(weapons))
        s.players[str(uid)]["char"] = ch
    s.state = "playing"
    return s

def random_scenario(s, max_monsters=6):
    n = Narrator()
    sc = n._fallback_scenario(s)
    # randomize encounters
    enc = []
    mkeys = list(MONSTERS.keys())
    n_types = random.randint(1, min(3, len(mkeys)))
    chosen = random.sample(mkeys, n_types)
    total = 0
    for k in chosen:
        c = random.randint(1, 3)
        if total + c > max_monsters: c = max(1, max_monsters - total)
        m = MONSTERS[k]
        enc.append({"name": k, "count": c, "ac": m["ac"], "hp": m["hp"], "dmg": m["dmg"], "xp": m["xp"]})
        total += c
        if total >= max_monsters: break
    sc["encounters"] = enc
    return sc

def auto_play(s, max_rounds=80):
    """Play out combat with random but legal actions."""
    rounds = 0
    total_actions = 0
    safety = 0
    while s.combat and rounds < max_rounds:
        safety += 1
        if safety > 500:
            return False, f"infinite loop (safety) at round {rounds}"
        cur = s.combat["participants"][s.combat["turn"]]
        if cur.get("kind") != "player":
            msg = advance(s)
            continue
        uid = int(cur["uid"])
        ch = s.get_char(uid)
        if not ch:
            advance(s); continue
        if cur.get("dead"):
            advance(s); continue
        if ch.hp <= 0 or cur.get("downed"):
            death_save(s, uid)
            if s.combat: advance(s)
            rounds += 1; total_actions += 1; continue
        mobs = [p for p in s.combat["participants"] if p["kind"]=="monster" and p.get("alive")]
        if not mobs: break
        target = mobs[0]["name"]
        # choose action
        can_cast = ch.cls in ("wizard","sorcerer","bard","warlock","cleric","druid","paladin","ranger")
        r = random.random()
        try:
            if can_cast and ch.available_slot(1) and r < 0.25:
                spell = random.choice(["firebolt","curewounds"])
                if spell == "curewounds":
                    cast(s, uid, "curewounds", ch.name)
                else:
                    cast(s, uid, spell, target)
            elif r < 0.10:
                dodge(s, uid)
            else:
                attack(s, uid, target)
        except Exception as e:
            return False, f"action crash uid={uid}: {traceback.format_exc()}"
        total_actions += 1
        if s.combat:
            adv = advance(s)
        rounds += 1
    if s.combat:
        # forced cleanup
        end_combat(s)
        return False, f"combat did not end in {max_rounds} rounds"
    return True, f"{total_actions} actions"

def main():
    print("="*60)
    print("FUZZ TEST: 200 random combos")
    for i in range(200):
        size = random.choice([1,2,3,4,5,6])
        s = make_party(size, seed=1000+i)
        s.scenario = random_scenario(s)
        try:
            start_combat(s)
            run_initial_monsters(s)
            ok, info = auto_play(s)
            if not ok:
                issue(f"run {i} size={size}", info)
            elif (i+1) % 50 == 0:
                print(f"  {i+1}/200 OK")
        except Exception as e:
            issue(f"run {i} size={size} crashed", traceback.format_exc())

    print("\n" + "="*60)
    print("PARSER FUZZ: many natural-language phrases")
    phrases = [
        "حمله می‌کنم به گابلین", "بزنمش", "اون گرگه رو بکش", "آتیشش بزن", "شفا بده",
        "در رو باز می‌کنم", "مشعل روشن کن", "استراحت کوتاه", "استراحت طولانی",
        "کمک", "دفاع می‌کنم", "مرگ‌سیو", "نگاه کن", "می‌رم جلو", "کجایم",
        "می‌خوام سناریو جدید بسازیم", "نبرد شروع کن", "وضعیتم چطوره",
        "معجون می‌خورم", "طلا برمی‌دارم", "مخفیانه حرکت می‌کنم", "گوش می‌دهم",
        "با تبر به گابلین بزن", "تیر بزن به اورک", "بسوزونش", "فرار می‌کنم",
        "با احتیاط وارد می‌شوم", "سلام ای پیرمرد", "تاس بنداز", "لول آپ",
    ]
    for p in phrases:
        try:
            r = parse_action(p, in_combat=False, valid_monsters=["گابلین","گرگ"], is_dm=True)
            if r.get("action") in (None, ""):
                issue(f"parser empty action: {p}")
            r2 = parse_action(p, in_combat=True, valid_monsters=["گابلین","گرگ"], is_dm=False)
        except Exception as e:
            issue(f"parser crash: {p}", traceback.format_exc())

    print("\n" + "="*60)
    print("PERSISTENCE FUZZ: save/load mid-combat")
    try:
        from game.store import Store
        for i in range(20):
            db = Store(f"/tmp/fuzz_persist_{i}.db")
            s = make_party(3, seed=9000+i)
            s.scenario = random_scenario(s)
            start_combat(s); run_initial_monsters(s)
            ok, info = auto_play(s, max_rounds=20)
            db.save(s)
            s2 = db.load(s.chat_id)
            if s2 is None:
                issue(f"persist {i}: load returned None"); continue
            if i == 0 and not s2.combat:
                # might have ended - just check state
                pass
    except Exception as e:
        issue("persistence fuzz crash", traceback.format_exc())

    print("\n" + "="*60)
    if ISSUES:
        print(f"نتیجه: {len(ISSUES)} مشکل")
        for t,d in ISSUES[:20]:
            print(f"  - {t}")
        sys.exit(1)
    else:
        print("نتیجه: همه فاز تست‌ها سبز ✅")
        sys.exit(0)

if __name__ == "__main__":
    main()
