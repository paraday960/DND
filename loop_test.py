# -*- coding: utf-8 -*-
"""لوپ تست خودکار: بازی به‌عنوان بازیکن با متن فارسی طبیعی."""
import os, sys, random, time, json, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AI_PROVIDER", "mistral")
os.environ.setdefault("MISTRAL_API_KEY", os.environ.get("MISTRAL_API_KEY", ""))
os.environ.setdefault("BOT_TOKEN", "1:dummy")
os.environ.setdefault("DB_PATH", "/tmp/loop_test.db")

from game.store import Store
from game.narrator import Narrator
from game.models import Session, Character
from game.combat import start_combat, run_initial_monsters, attack, cast, dodge, advance, end_combat
from game.adventure import death_save, rest, skill_check
from game.nlp import parse_action, MONSTER_FA
from game.world import try_environment_action

random.seed()
ISSUES = []


def issue(title, detail=""):
    ISSUES.append((title, detail))
    print(f"  ❌ BUG: {title}")
    if detail:
        print(f"     {detail[:200]}")


def make_party(num_players=2):
    s = Session(random.randint(10**6, 10**9), "تست", 1, "آرش")
    races_classes = [
        ("dwarf", "fighter", "greataxe"),
        ("elf", "wizard", "staff"),
        ("human", "rogue", "rapier"),
        ("halfling" if "halfling" in __import__('game.rules', fromlist=['RACES']).RACES else "human",
         "cleric", "mace") if False else ("human", "fighter", "longsword"),
    ]
    for i in range(num_players):
        uid = 1 + i
        if uid != 1:
            s.add_player(uid, f"بازیکن{i}")
        race, cls, weap = races_classes[i % len(races_classes)]
        ch = Character(f"قهرمان{i+1}", race, cls, weap)
        s.players[str(uid)]["char"] = ch
    s.state = "playing"
    return s


def monster_names_fa(s):
    return [p["name"] for p in (s.combat or {}).get("participants", []) if p["kind"] == "monster" and p.get("alive")]


def run_natural_action(s, uid, text):
    """یک متن فارسی طبیعی را به بازی بده و نتیجه را برگردان."""
    ch = s.get_char(uid)
    mobs = monster_names_fa(s)
    act = parse_action(text, in_combat=bool(s.combat), has_char=bool(ch),
                       valid_monsters=mobs, is_dm=(s.dm_id == uid))
    a = act.get("action")
    msgs = []

    if a == "attack":
        tgt = act.get("target") or ""
        # map persian monster name
        if tgt:
            for fa, key in MONSTER_FA.items():
                if fa in tgt:
                    tgt = fa
                    break
        if not tgt or not s.combat:
            return ["(no target or no combat)"]
        r = attack(s, uid, tgt)
        msgs.append(r)
        if s.combat:
            t = advance(s)
            if t:
                msgs.append(t)
    elif a == "cast":
        spell = act.get("spell", "firebolt")
        tgt = act.get("target") or ""
        if tgt:
            for fa in MONSTER_FA:
                if fa in tgt:
                    tgt = fa
                    break
        r = cast(s, uid, spell, tgt)
        msgs.append(r)
        if s.combat:
            t = advance(s)
            if t:
                msgs.append(t)
    elif a == "dodge":
        r = dodge(s, uid)
        msgs.append(r)
        if s.combat:
            t = advance(s)
            if t:
                msgs.append(t)
    elif a == "skip":
        if s.combat:
            t = advance(s)
            msgs.append(t or "رد شد")
    elif a == "deathsave":
        r = death_save(s, uid)
        msgs.append(r)
        if s.combat:
            t = advance(s)
            if t:
                msgs.append(t)
    elif a == "torch":
        env = try_environment_action(s, ch, "مشعل روشن می‌کنم")
        if env:
            msgs.append(env)
        else:
            msgs.append("(مشعل در دسترس نیست)")
    elif a == "look":
        if s.combat:
            msgs.append("(وضعیت نبرد)")
        else:
            msgs.append("(بررسی محیط)")
    elif a == "rest":
        msgs.append(rest(s, uid, act.get("kind", "short")))
    elif a == "sheet":
        msgs.append(ch.sheet_text()[:200] if ch else "no char")
    elif a == "party":
        msgs.append(f"تیم {len(s.players)} نفره")
    elif a == "scenario":
        msgs.append("(سناریو ساخته می‌شود)")
    elif a == "combat":
        t1 = start_combat(s)
        msgs.append(t1)
        t2 = run_initial_monsters(s)
        if t2:
            msgs.append(t2)
    elif a == "narrate":
        narrator = Narrator()
        t = narrator.narrate(s, act.get("text", text))
        msgs.append(t[:300])
    else:
        msgs.append(f"[action={a}]")
    return msgs


def play_combat(s, max_rounds=30):
    """بازی نبرد تا پیروزی/شکست با انتخاب‌های طبیعی."""
    log = []
    rnd = 0
    while s.combat and rnd < max_rounds:
        rnd += 1
        cur = s.combat["participants"][s.combat["turn"]]
        if cur["kind"] != "player":
            # should not happen - advance handles monsters
            t = advance(s)
            if t:
                log.append(("monster", t))
            continue
        uid = int(cur["uid"])
        ch = s.get_char(uid)
        if not ch:
            advance(s)
            continue
        # downed?
        if cur.get("downed") or cur.get("dead") or ch.hp <= 0:
            if cur.get("dead"):
                advance(s)
                continue
            msgs = run_natural_action(s, uid, "مرگ‌سیو")
            log.append((uid, "deathsave", msgs))
            continue
        # choose an action based on situation
        mobs = [p for p in s.combat["participants"] if p["kind"] == "monster" and p.get("alive")]
        if not mobs:
            break
        target = mobs[0]["name"]
        # Wizard casts if has slots, else attack
        if ch.cls == "wizard" and ch.spell_slots and ch.available_slot(1) and random.random() < 0.5:
            if any(p.get("hp", 0) < p.get("max_hp", 1) for p in s.combat["participants"]
                   if p["kind"] == "player" and p.get("alive")) and random.random() < 0.3:
                text = f"شفا بده به {ch.name}"
            else:
                text = f"آتیش بزن به {target}"
        elif ch.hp < ch.max_hp * 0.4 and ch.cls in ("fighter", "rogue"):
            text = "دفاع می‌کنم"
        else:
            # varied natural phrases
            phrase = random.choice([
                f"حمله می‌کنم به {target}",
                f"با تبر به {target} بزن",
                f"بزنم به {target}",
                f"به {target} حمله کن",
                f"{target} رو بکوب",
                f"با شمشیر می‌زنم به {target}",
            ])
            text = phrase
        msgs = run_natural_action(s, uid, text)
        log.append((uid, text, msgs))
        # victory?
        if s.combat is None:
            break
    # if combat still running, end it
    if s.combat:
        end_combat(s)
    return log, rnd


def run_scenario(narrator, party_size=2, seed=None, request=""):
    if seed is not None:
        random.seed(seed)
    s = make_party(party_size)
    sc = narrator.scenario(s, request)
    s.scenario = sc
    return s


def test_basic_parser():
    print("🧪 تست پارسر زبان طبیعی...")
    cases = [
        ("حمله می‌کنم به گابلین", "attack"),
        ("اسکلت رو آتیش بزن", "cast"),
        ("دفاع می‌کنم", "dodge"),
        ("مرگ‌سیو", "deathsave"),
        ("مشعل روشن می‌کنم", "torch"),
        ("نگاه کن", "look"),
        ("استراحت کوتاه", "rest"),
        ("وضعیتم چطوره", "sheet"),
        ("گروه کیه", "party"),
        ("سناریو بساز", "scenario"),
        ("شروع نبرد", "combat"),
        ("در رو باز می‌کنم", "narrate"),
    ]
    for text, expected in cases:
        a = parse_action(text, in_combat=expected in ("attack", "cast", "dodge", "skip", "deathsave"),
                         valid_monsters=["گابلین", "اسکلت"], is_dm=True)
        ok = a["action"] == expected
        if not ok:
            issue(f"parser: {text!r} -> {a['action']} (expected {expected})")
    print("   done")


def test_full_gameplay():
    print("\n🎮 تست کامل گیم‌پلی با ۳ سناریو...")
    narrator = Narrator()
    if not narrator.available:
        issue("AI narrator not available", "API key missing")
        return

    requests = [
        "سیاهچال کوتاه با چند گابلین",
        "جنگل تاریک با گرگ‌ها",
        "مقبره باستانی با اسکلت‌ها",
        "اردوگاه راهزنان در بزرگراه",
        "کلبه متروک در باتلاق",
        "غار عنکبوت‌های غول‌پیکر",
        "گورستان قدیمی",
        "پایگاه اورک‌های کوهستان",
    ]
    for i, req in enumerate(requests, 1):
        print(f"\n=== سناریو {i}: {req} ===")
        try:
            t0 = time.time()
            s = run_scenario(narrator, party_size=2, seed=100 + i, request=req)
            dt = time.time() - t0
            if not s.scenario:
                issue(f"scenario {i}: no scenario returned")
                continue
            print(f"  عنوان: {s.scenario.get('title', '?')}")
            enc = s.scenario.get("encounters", [])
            total = sum(e.get("count", 0) for e in enc)
            print(f"  دشمنان: {len(enc)} نوع، مجموعاً {total}")
            if total > 12:
                issue(f"scenario {i}: too many monsters ({total})")
            for e in enc:
                if e.get("name") not in __import__('game.rules', fromlist=['MONSTERS']).MONSTERS:
                    issue(f"scenario {i}: unknown monster {e.get('name')}")

            # narration
            text = narrator.narrate(s, "با احتیاط وارد می‌شوم")
            if not text or len(text) < 20:
                issue(f"scenario {i}: narration empty/short")
            else:
                print(f"  روایت: {text[:80]}...")

            # torch
            r = run_natural_action(s, 1, "مشعل روشن می‌کنم")
            if s.world.get("light") != "torch":
                issue(f"scenario {i}: torch did not light")

            # start combat
            t1 = start_combat(s)
            t2 = run_initial_monsters(s)
            if not s.combat:
                issue(f"scenario {i}: combat didn't start")
                continue
            n_part = len(s.combat["participants"])
            print(f"  نبرد شروع شد با {n_part} شرکت‌کننده")

            # play
            log, rounds = play_combat(s)
            print(f"  نبرد در {rounds} دور تمام شد")

            # after combat
            alive = sum(1 for p in s.players.values() if p["char"] and p["char"].hp > 0)
            print(f"  بازمانده: {alive}/{len(s.players)}")
            for uid, p in s.players.items():
                c = p["char"]
                if c:
                    print(f"    {c.name}: HP {c.hp}/{c.max_hp}, XP {c.xp}, lvl {c.level}")

            # rest
            if alive > 0:
                r = rest(s, 1, "short")
                if "استراحت" not in r:
                    issue(f"scenario {i}: rest failed: {r}")

        except Exception as e:
            issue(f"scenario {i} crashed", traceback.format_exc())


def test_edge_cases():
    print("\n🔍 تست موارد مرزی...")
    narrator = Narrator()

    # 1. Outside combat, an attack phrase should either start narration or warn about no combat
    s = make_party(1)
    r = run_natural_action(s, 1, "حمله می‌کنم به گابلین")
    joined = " ".join(str(x) for x in r)
    if len(joined) < 10:
        issue("attack outside combat gave no response", joined)

    # 2. Scenario then combat should use scenario monsters
    s2 = make_party(1)
    s2.scenario = narrator._fallback_scenario(s2)
    s2.scenario["encounters"] = [{"name": "wolf", "count": 3, "ac": 13, "hp": 11, "dmg": "1d6+2", "xp": 50}]
    start_combat(s2)
    wolves = [p for p in s2.combat["participants"] if p["kind"] == "monster"]
    if not all("گرگ" in p["name"] for p in wolves) or len(wolves) != 3:
        issue(f"scenario wolves not loaded: {[p['name'] for p in wolves]}")
    else:
        print(f"  ✅ سناریو با ۳ گرگ درست لود شد")

    # 3. Death save flow - simulate downed player
    s3 = make_party(1)
    s3.scenario = {"encounters": [{"name": "goblin", "count": 1, "ac": 15, "hp": 100, "dmg": "1d6+2", "xp": 50}]}
    start_combat(s3)
    # force down player
    me = next(p for p in s3.combat["participants"] if p["kind"] == "player")
    me["hp"] = 0
    me["downed"] = True
    s3.get_char(1).hp = 0
    r = death_save(s3, 1)
    if "مرگ‌سیو" not in r and "پایدار" not in r and "بلند" not in r and "مرد" not in r:
        issue("death save unexpected response", r)

    # 4. Persian digits
    a = parse_action("حمله می‌کنم به گابلین ۲", in_combat=True, valid_monsters=["گابلین 1", "گابلین 2"])
    if a["action"] != "attack":
        issue("Persian/number in action failed", str(a))

    print("  edge cases done")


if __name__ == "__main__":
    try:
        test_basic_parser()
        test_edge_cases()
        test_full_gameplay()
    except KeyboardInterrupt:
        print("\nstopped")
    print("\n" + "=" * 60)
    if ISSUES:
        print(f"نتیجه: {len(ISSUES)} باگ پیدا شد:")
        for t, d in ISSUES:
            print(f"  - {t}")
        sys.exit(1)
    else:
        print("نتیجه: همه تست‌ها سبز ✅")
        sys.exit(0)
