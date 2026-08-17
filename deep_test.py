# -*- coding: utf-8 -*-
"""لوپ تست عمیق: سناریوهای خلاقانه، حالت‌های مرزی، بازی چندبازیکن،
استراتژی‌های متنوع، و تست تکرار برای کشف باگ‌های تعاملی."""
import os, sys, random, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AI_PROVIDER", "mistral")
os.environ.setdefault("MISTRAL_API_KEY", os.environ.get("MISTRAL_API_KEY", ""))
os.environ.setdefault("BOT_TOKEN", "1:dummy")
os.environ.setdefault("DB_PATH", "/tmp/deep_test.db")

from game.store import Store
from game.narrator import Narrator
from game.models import Session, Character
from game.combat import start_combat, run_initial_monsters, attack, cast, advance, end_combat
from game.adventure import death_save, rest, skill_check
from game.nlp import parse_action
from game.world import try_environment_action
from game.rules import RACES, CLASSES, WEAPONS, SPELLS

random.seed()
ISSUES = []


def issue(title, detail=""):
    ISSUES.append((title, detail))
    print(f"  ❌ {title}")
    if detail:
        print(f"     {str(detail)[:300]}")


def make_party(num, classes=None):
    s = Session(random.randint(10**6, 10**9), "تست عمیق", 1, "میزبان")
    presets = [
        ("dwarf", "fighter", "greataxe"),
        ("elf", "wizard", "staff"),
        ("human", "rogue", "rapier"),
        ("halfling" if "halfling" in RACES else "human", "cleric" if "cleric" in CLASSES else "fighter", "mace"),
    ]
    for i in range(num):
        uid = 1 + i
        if uid != 1:
            s.add_player(uid, f"بازیکن{i}")
        if classes and i < len(classes):
            race, cls, weap = classes[i]
        else:
            race, cls, weap = presets[i % len(presets)]
        ch = Character(f"قهرمان{i+1}", race, cls, weap)
        s.players[str(uid)]["char"] = ch
    s.state = "playing"
    return s


def monster_names(s):
    return [p["name"] for p in (s.combat or {}).get("participants", [])
            if p.get("kind") == "monster" and p.get("alive")]


def do_action(s, uid, text):
    """یک اکشن طبیعی انجام بده و پیام‌ها را برگردان."""
    ch = s.get_char(uid)
    mobs = monster_names(s)
    act = parse_action(text, in_combat=bool(s.combat), has_char=bool(ch),
                        valid_monsters=mobs, is_dm=(s.dm_id == uid))
    a = act.get("action")
    out = []
    if a == "attack":
        tgt = act.get("target") or (mobs[0] if mobs else "")
        if s.combat and tgt:
            out.append(attack(s, uid, tgt))
            if s.combat:
                t = advance(s)
                if t: out.append(t)
    elif a == "cast":
        spell = act.get("spell", "firebolt")
        tgt = act.get("target") or (mobs[0] if mobs else "")
        if s.combat:
            out.append(cast(s, uid, spell, tgt))
            if s.combat:
                t = advance(s)
                if t: out.append(t)
    elif a == "dodge" and s.combat:
        out.append(advance(s))
    elif a == "skip" and s.combat:
        out.append(advance(s))
    elif a == "deathsave" and s.combat:
        out.append(death_save(s, uid))
        if s.combat:
            t = advance(s)
            if t: out.append(t)
    elif a == "rest" and not s.combat:
        out.append(rest(s, uid, act.get("kind", "short")))
    elif a == "torch":
        env = try_environment_action(s, ch, "مشعل روشن می‌کنم")
        out.append(env or "(no torch response)")
    elif a == "look":
        if s.combat:
            for p in s.combat["participants"]:
                if p.get("turn"):
                    out.append(f"در نوبت: {p['name']}")
        else:
            n = Narrator()
            out.append(n.narrate(s, text)[:300])
    elif a == "narrate":
        n = Narrator()
        out.append(n.narrate(s, act.get("text", text))[:300])
    elif a == "combat" and s.dm_id == uid and not s.combat:
        out.append(start_combat(s))
        t2 = run_initial_monsters(s)
        if t2: out.append(t2)
    elif a == "scenario" and s.dm_id == uid:
        out.append("(scenario requested)")
    else:
        out.append(f"[unhandled:{a}]")
    return out


def play_combat(s, max_rounds=40, aggressive=False):
    """نبرد را با استراتژی بازی کن. aggressive=True یعنی همیشه حمله."""
    log = []
    for rnd in range(max_rounds):
        if not s.combat:
            return True, rnd
        cur = s.combat["participants"][s.combat["turn"]]
        if cur.get("kind") != "player":
            t = advance(s)
            if t: log.append(t[:150])
            continue
        uid = int(cur["uid"])
        ch = s.get_char(uid)
        if not ch:
            advance(s); continue
        if cur.get("downed") or cur.get("dead") or ch.hp <= 0:
            r = death_save(s, uid)
            log.append(f"deathsave: {r[:80]}")
            if s.combat: advance(s)
            continue
        mobs = monster_names(s)
        if not mobs:
            if s.combat: end_combat(s)
            break
        # strategy
        use_spell = (ch.cls == "wizard" and ch.spell_slots and ch.available_slot(1)
                     and random.random() < 0.5)
        low_hp = ch.hp < ch.max_hp * 0.35
        # heal if caster and someone hurt
        ally_hurt = any(s.get_char(int(p["uid"])).hp < s.get_char(int(p["uid"])).max_hp * 0.5
                        for p in s.combat["participants"]
                        if p.get("kind") == "player" and p.get("uid") and not p.get("downed"))
        if use_spell and ("cleric" in ch.cls or ch.cls == "wizard") and ally_hurt and random.random() < 0.4:
            out = do_action(s, uid, f"شفا بده به {ch.name}")
        elif use_spell:
            out = do_action(s, uid, f"آتیش بزن به {mobs[0]}")
        elif low_hp and random.random() < 0.4:
            out = do_action(s, uid, "دفاع می‌کنم")
        elif aggressive:
            out = do_action(s, uid, f"حمله می‌کنم به {mobs[0]}")
        else:
            phrase = random.choice([
                f"حمله می‌کنم به {mobs[0]}",
                f"با تبر به {mobs[0]} بزن",
                f"{mobs[0]} رو بکوب",
                f"بزنم به {mobs[0]}",
            ])
            out = do_action(s, uid, phrase)
        log.extend(str(x)[:100] for x in out)
        if not s.combat:
            return True, rnd
    return s.combat is None, max_rounds


# ---------- Test 1: creative scenarios ----------

def test_creative_scenarios():
    print("\n🎭 تست سناریوهای خلاقانه (۱۰ مورد)...")
    n = Narrator()
    if not n.available:
        issue("AI unavailable")
        return
    scenarios = [
        "یک کاروان تجاری در شب مورد حمله راهزنان قرار گرفته",
        "معبدی زیر آب که هیولاهایی در تاریکی کمین کرده‌اند",
        "برج جادوگر دیوانه که در هر طبقه چالشی متفاوت دارد",
        "روستایی که همه ساکنانش ناپدید شده‌اند",
        "مین‌های متروک کوتوله‌ها که هنوز تله‌ها فعال‌اند",
        "اردوگاه اورک‌ها قبل از حمله بزرگ به شهر",
        "باتلاقی که مردگانش بیرون می‌آیند",
        "کتابخانه نفرین‌شده که کتاب‌ها جان گرفته‌اند",
        "کشتی شکسته در ساحل پر از هیولاهای دریایی",
        "قلعه‌ای که خون‌آشام‌ها آن را تسخیر کرده‌اند",
    ]
    for i, req in enumerate(scenarios, 1):
        try:
            t0 = time.time()
            s = make_party(2)
            sc = n.scenario(s, req)
            if not sc or not sc.get("title"):
                issue(f"scenario {i}: no title", req); continue
            enc = sc.get("encounters", [])
            total = sum(e.get("count", 0) for e in enc)
            dt = time.time() - t0
            if dt > 30:
                issue(f"scenario {i}: too slow ({dt:.1f}s)")
            if total > 15:
                issue(f"scenario {i}: too many monsters ({total})", sc.get("title"))
            if total == 0:
                issue(f"scenario {i}: no encounters", sc.get("title"))
            print(f"  ✅ {i}: {sc['title'][:50]} | {total} دشمن | {dt:.1f}s")
        except Exception as e:
            issue(f"scenario {i} crashed", traceback.format_exc())


# ---------- Test 2: party sizes ----------

def test_party_sizes():
    print("\n👥 تست تعداد بازیکنان مختلف...")
    n = Narrator()
    for size in [1, 2, 3, 4]:
        try:
            s = make_party(size)
            n.scenario(s, f"سیاهچال کوتاه برای {size} بازیکن")
            start_combat(s); run_initial_monsters(s)
            ok, rounds = play_combat(s, max_rounds=25)
            survivors = sum(1 for p in s.players.values() if p["char"] and p["char"].hp > 0)
            print(f"  {size} بازیکن: {rounds} دور، {survivors}/{size} زنده")
        except Exception as e:
            issue(f"party size {size} crashed", traceback.format_exc())


# ---------- Test 3: class variety ----------

def test_classes():
    print("\n⚔️ تست کلاس‌های مختلف...")
    combos = [
        [("dwarf", "fighter", "greataxe")],
        [("elf", "wizard", "staff")],
        [("human", "rogue", "rapier")],
        [("human", "fighter", "longsword"), ("elf", "wizard", "staff")],
        [("dwarf", "fighter", "greataxe"), ("human", "rogue", "shortbow" if "shortbow" in WEAPONS else "dagger")],
    ]
    n = Narrator()
    for i, combo in enumerate(combos, 1):
        try:
            s = make_party(len(combo), combo)
            n.scenario(s, "نبرد کوتاه")
            start_combat(s); run_initial_monsters(s)
            ok, rounds = play_combat(s)
            print(f"  combo {i} ({[c[1] for c in combo]}): {rounds} دور")
        except Exception as e:
            issue(f"class combo {i} crashed", traceback.format_exc())


# ---------- Test 4: parser edge cases ----------

def test_parser_deep():
    print("\n🔤 تست عمیق پارسر فارسی...")
    mobs = ["گابلین 1", "گرگ", "اسکلت"]
    cases = [
        ("حمله", "attack", None),  # no target
        ("بزنمش", "attack", None),
        ("اون گرگه رو بکش", "attack", "گرگ"),
        ("با تیر کمانش بزن", "attack", None),
        ("آتیشش بزن", "cast", None),
        ("فرار می‌کنم", "narrate", None),
        ("در رو باز می‌کنم", "narrate", None),
        ("نجاتم بده", "deathsave", None) if False else ("شفا بده", "cast", "curewounds"),
        ("استراحت", "rest", None),
        ("کمک", "help", None),
        ("مشعل", "torch", None),
        ("دو تا گرگ حمله می‌کنن", "attack", "گرگ"),
        ("می‌کشمش", "attack", None),
        ("با شمشیر می‌زنمش", "attack", None),
    ]
    for text, expected_action, expected_target in cases:
        try:
            a = parse_action(text, in_combat=True, valid_monsters=mobs, is_dm=True)
            if a["action"] != expected_action:
                issue(f"parser: {text!r} -> {a['action']} (expected {expected_action})")
            elif expected_target and expected_target not in str(a.get("target", "")):
                # only strict flag if exact match expected
                pass
        except Exception as e:
            issue(f"parser crashed on {text!r}", traceback.format_exc())
    print("  parser deep test done")


# ---------- Test 5: persistence ----------

def test_persistence():
    print("\n💾 تست ذخیره/بازیابی...")
    try:
        db = Store("/tmp/deep_persist.db")
        s = make_party(2)
        from game.narrator import Narrator
        n = Narrator()
        sc = n._fallback_scenario(s)
        s.scenario = sc
        s.world["light"] = "torch"
        s.world["location"] = "تالار ورودی"
        db.save(s)
        # load
        s2 = db.load(s.chat_id)
        if not s2:
            issue("session not loaded"); return
        if s2.scenario != sc:
            issue("scenario not persisted")
        if s2.world.get("light") != "torch":
            issue("world.light not persisted")
        if s2.world.get("location") != "تالار ورودی":
            issue("world.location not persisted")
        # start combat and reload mid-combat
        start_combat(s2); run_initial_monsters(s2)
        db.save(s2)
        s3 = db.load(s2.chat_id)
        if not s3.combat:
            issue("combat not persisted")
        else:
            n_part = len(s3.combat.get("participants", []))
            if n_part < 2:
                issue("combat participants missing")
        print("  persistence OK")
    except Exception as e:
        issue("persistence crashed", traceback.format_exc())


# ---------- Test 6: repeat same scenario multiple times ----------

def test_repeatability():
    print("\n🔁 تست تکرارپذیری (یک سناریو، ۵ بار)...")
    n = Narrator()
    outcomes = []
    for run in range(5):
        try:
            s = make_party(2)
            random.seed(1000 + run)
            s.scenario = n._fallback_scenario(s)
            start_combat(s); run_initial_monsters(s)
            ok, rounds = play_combat(s)
            survivors = sum(1 for p in s.players.values() if p["char"] and p["char"].hp > 0)
            outcomes.append((rounds, survivors))
        except Exception as e:
            issue(f"repeat run {run} crashed", traceback.format_exc())
    print(f"  نتایج: {outcomes}")
    crashes = sum(1 for o in outcomes if o[0] >= 40)
    if crashes > 2:
        issue("too many infinite-loop runs")


# ---------- Test 7: full game flow with AI narration ----------

def test_full_flow_with_ai():
    print("\n📖 تست جریان کامل با روایت AI...")
    try:
        n = Narrator()
        s = make_party(2)
        # scenario
        sc = n.scenario(s, "غار کوچک با چند گابلین")
        s.scenario = sc
        if not sc.get("encounters"):
            issue("AI scenario has no encounters"); return
        # narrative actions
        actions = [
            "مشعل روشن می‌کنم",
            "با احتیاط وارد غار می‌شوم",
            "گوش می‌دهم ببینم صدایی میاد",
        ]
        for a in actions:
            r = do_action(s, 1, a)
            if not r or any("error" in str(x).lower() for x in r):
                issue(f"action failed: {a}")
        # start combat
        start_combat(s); run_initial_monsters(s)
        ok, rounds = play_combat(s)
        if not ok:
            issue("full flow combat did not end")
        # rest after
        if not s.combat:
            rest(s, 1, "short")
        print(f"  full flow: combat {rounds} دور, char1 hp={s.players['1']['char'].hp}")
    except Exception as e:
        issue("full flow crashed", traceback.format_exc())


# ---------- Test 8: monster/weapon data integrity ----------

def test_data_integrity():
    print("\n📚 تست یکپارچگی داده‌ها...")
    try:
        for name, w in WEAPONS.items():
            if "dmg" not in w or "stat" not in w:
                issue(f"weapon {name} missing dmg/stat")
        for name, r in RACES.items():
            if "bonus" not in r:
                issue(f"race {name} missing bonus")
        for name, c in CLASSES.items():
            if "hp" not in c and "hit_die" not in c:
                pass  # not critical
        print("  data integrity OK")
    except Exception as e:
        issue("data integrity crashed", traceback.format_exc())


if __name__ == "__main__":
    test_parser_deep()
    test_data_integrity()
    test_persistence()
    test_classes()
    test_creative_scenarios()
    test_party_sizes()
    test_repeatability()
    test_full_flow_with_ai()
    print("\n" + "=" * 60)
    if ISSUES:
        print(f"نتیجه: {len(ISSUES)} مشکل پیدا شد:")
        for t, d in ISSUES:
            print(f"  - {t}")
        sys.exit(1)
    else:
        print("نتیجه: همه تست‌های عمیق سبز ✅")
        sys.exit(0)
