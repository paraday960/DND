# -*- coding: utf-8 -*-
"""موتور نبرد — نوبت‌بندی، حمله، طلسم، دشمنان هوشمند و توزیع XP."""
import random

from .dice import DiceError, parse_dice, roll_dice, roll_d20
from .models import Session
from .rules import CLASSES, MONSTERS, SPELLS, WEAPONS, ability_mod


# جدول گنج/لوت تصادفی پس از پیروزی
_LOOT_TABLE = [
    ("potion", 1, "🧪 معجون شفا"),
    ("torch", 2, "🔥 مشعل"),
    ("gold", None, "🪙 سکه"),
    ("rope", 1, "🪢 طناب"),
]


def _roll_loot(victory: bool, party_size: int, xp_pool: int = 0) -> list:
    """پس از پیروزی، گنج تصادفی تولید می‌کند."""
    if not victory:
        return []
    drops = []
    # سکه بر اساس XP
    gold_share = max(5, xp_pool // max(1, party_size) // 4)
    for _ in range(party_size):
        drops.append(("gold", random.randint(max(3, gold_share - 5), gold_share + 8)))
    # شانس معجون/طناب/مشعل
    if random.random() < 0.55:
        drops.append(("potion", random.randint(1, 2)))
    if random.random() < 0.35:
        drops.append(("torch", random.randint(1, 2)))
    if random.random() < 0.20:
        drops.append(("rope", 1))
    return drops


def _apply_loot(session, drops: list) -> str:
    """گنج را بین کاراکترها تقسیم می‌کند."""
    lines = []
    chars = [p["char"] for p in session.players.values() if p.get("char")]
    if not chars:
        return ""
    for item, qty in drops:
        if item == "gold":
            ch = random.choice(chars)
            ch.gold += qty
            lines.append(f"🪙 {qty} سکه به {ch.name} رسید.")
        else:
            ch = random.choice(chars)
            ch.inventory[item] = ch.inventory.get(item, 0) + qty
            fa = {"potion": "معجون شفا", "torch": "مشعل", "rope": "طناب"}.get(item, item)
            lines.append(f"{_LOOT_EMOJI(item)} {qty}× {fa} به {ch.name} رسید.")
    return "\n".join(lines)


def _LOOT_EMOJI(item: str) -> str:
    return {"potion": "🧪", "torch": "🔥", "rope": "🪢"}.get(item, "🎁")


def _default_atk_bonus(mkey: str, base: dict) -> int:
    """پاداش حمله پیش‌فرض بر اساس CR هیولا (برآورد از روی xp/cr)."""
    cr = base.get("cr", 0.25)
    if cr >= 6:
        return 7
    if cr >= 3:
        return 5
    if cr >= 1:
        return 3
    return 2


# تعداد حمله هر دشمن (multiattack) بر اساس کلید هیولا
_MULTIATTACK = {
    "troll": 2,
    "dragon_young": 3,
    "harpy": 2,
    "orc": 1,
    "goblin": 1,
    "wolf": 1,
    "skeleton": 1,
    "zombie": 1,
    "bandit": 1,
    "giant_spider": 2,
}


def _monster_key(mon: dict) -> str:
    """سعی می‌کند کلید MONSTERS را از روی نام پیدا کند."""
    # نام مثل «ترول 2» یا «گابلین»
    name = mon.get("_key", "")
    if name:
        return name
    for k, v in MONSTERS.items():
        if v["fa"] in mon.get("name", "") or mon.get("name", "").startswith(v["fa"]):
            return k
    return ""


def _resolve_one_attack(session, mon, target, atk_bonus) -> tuple:
    """یک حمله منفرد را اجرا می‌کند. خروجی: (lines_text, target_was_downed)."""
    raw = roll_d20()
    adv = "dodge" in target.get("conditions", [])
    rolls = [raw]
    if adv:
        rolls.append(roll_d20())
        raw = min(rolls)
    atk = raw + atk_bonus
    crit = raw == 20
    fumble = raw == 1
    hit = (crit or (raw != 1 and atk >= target["ac"])) and not fumble
    lines = []
    if hit:
        dmg = _roll_damage(mon.get("dmg", "1d6+0"))
        if crit:
            dmg *= 2
        target["hp"] = max(0, target["hp"] - dmg)
        adv_tag = " (با ضعف بخاطر دفاع)" if adv else ""
        lines.append(f"🎲 {mon['name']} به {target['name']} حمله کرد: {atk} "
                     f"(رول {raw}{'+' + str(atk_bonus) if atk_bonus else ''}) "
                     f"(AC {target['ac']}){adv_tag} — 💥 اصابت! {dmg} آسیب")
        if crit and not adv_tag:
            lines[-1] += " 🔥 **بحرانی!**"
        if fumble:
            pass  # impossible since hit
        downed = False
        if target["hp"] <= 0:
            target["hp"] = 0
            target["downed"] = True
            real_char = session.get_char(int(target["uid"]))
            if real_char:
                real_char.hp = 0
                real_char.death_saves = {"success": 0, "fail": 0}
            lines.append(f"💀 **{target['name']} از پا درآمد!** (در نوبتت /deathsave بزن)")
            downed = True
        return "\n".join(lines), downed
    else:
        miss_tag = " — لغزش دست!" if fumble else " — بی‌اثر!"
        return (f"🎲 {mon['name']} به {target['name']} حمله کرد: {atk} "
                f"(AC {target['ac']}){miss_tag}"), False



def _combat(session: Session) -> dict:
    if session.combat is None:
        session.combat = {"participants": [], "turn": 0, "round": 1, "xp_pool": 0}
    return session.combat


def is_player_turn(session: Session, uid: int) -> bool:
    """بررسی می‌کند که کاربر واقعاً نوبت اقدام دارد."""
    combat = session.combat
    if not combat or not combat.get("participants"):
        return False
    turn = combat.get("turn", 0)
    if turn >= len(combat["participants"]):
        return False
    current = combat["participants"][turn]
    if current.get("dead"):
        return False
    if current.get("kind") != "player" or current.get("uid") != str(uid):
        return False
    return True


def _roll_damage(expr: str) -> int:
    """پرتاب آسیب با پشتیبانی از d6، 2d8+3 و mod منفی."""
    try:
        count, sides, mod = parse_dice(str(expr))
    except DiceError:
        count, sides, mod = 1, 1, 0
    return sum(roll_dice(count, sides)) + mod if sides >= 2 else count + mod


def start_combat(session: Session) -> str:
    """نبرد را با بازیکنان زنده و دشمنان سناریو شروع می‌کند."""
    combat = _combat(session)
    combat["participants"] = []
    combat["turn"] = 0
    combat["round"] = 1
    combat["xp_pool"] = 0
    session.state = "combat"

    # بازیکنان (حتّی کسانی که در شروع نبرد آسیب دیده‌اند اما زنده‌اند)
    for uid, p in session.players.items():
        ch = p["char"]
        if not ch:
            continue
        alive = ch.hp > 0
        init = roll_d20() + ability_mod(ch.abilities["DEX"])
        combat["participants"].append({
            "kind": "player", "uid": uid, "name": ch.name,
            "emoji": CLASSES.get(ch.cls, {}).get("emoji", "🧙"),
            "init": init, "hp": ch.hp, "max_hp": ch.max_hp,
            "ac": ch.ac, "alive": True, "downed": not alive,
            "conditions": list(ch.conditions),
        })

    # دشمنان از سناریو
    monsters = []
    if session.scenario and session.scenario.get("encounters"):
        for e in session.scenario["encounters"]:
            name = e.get("name", "دشمن")
            count = max(1, int(e.get("count", 1)))
            base = MONSTERS.get(name.lower()) or {}
            for i in range(count):
                mkey = name.lower()
                base_atk = base.get("atk_bonus", _default_atk_bonus(mkey, base))
                is_boss = bool(e.get("is_boss"))
                mname = base.get("fa", name)
                suffix = " 👑" if is_boss and count == 1 else ""
                monsters.append({
                    "kind": "monster",
                    "_key": mkey,
                    "name": (f"{mname} {i + 1}" if count > 1 else mname) + suffix,
                    "emoji": base.get("emoji", "👹"),
                    "init": roll_d20() + int(e.get("init_bonus", base_atk - 2)),
                    "hp": int(e.get("hp", base.get("hp", 10))),
                    "max_hp": int(e.get("hp", base.get("hp", 10))),
                    "ac": int(e.get("ac", base.get("ac", 12))),
                    "dmg": e.get("dmg", base.get("dmg", "1d6+2")),
                    "atk_bonus": int(e.get("atk_bonus", base_atk)),
                    "xp": int(e.get("xp", base.get("xp", 50))),
                    "alive": True, "conditions": [],
                    "is_boss": is_boss,
                    "ability": e.get("ability", ""),
                })
    if not monsters:
        # نبرد پیش‌فرض برای وقتی سناریویی نیست
        for i in range(2):
            monsters.append({
                "kind": "monster", "_key": "goblin", "name": f"گابلین {i + 1}",
                "emoji": MONSTERS.get("goblin", {}).get("emoji", "👹"),
                "init": roll_d20() + 2, "hp": 7, "max_hp": 7, "ac": 15,
                "dmg": "1d6+2", "atk_bonus": 2, "xp": 50,
                "alive": True, "conditions": [], "is_boss": False,
            })
    combat["participants"].extend(monsters)

    # مرتب‌سازی بر اساس initiative
    combat["participants"].sort(key=lambda p: p["init"], reverse=True)
    session.add_log("سیستم", f"نبرد آغاز شد — {len(combat['participants'])} شرکت‌کننده")
    return order_text(session)


def order_text(session: Session) -> str:
    combat = session.combat
    lines = ["⚔️ **نبرد آغاز شد!** ترتیب نوبت‌ها:", ""]
    for i, p in enumerate(combat["participants"], 1):
        marker = "▶️" if i - 1 == combat["turn"] else "—"
        hp = f"❤️ {p['hp']}/{p['max_hp']}" if p["kind"] == "player" else f"❤️ {p['hp']}"
        if not p["alive"]:
            hp = "💀"
        lines.append(f"{i}. {marker} {p['name']} (Init {p['init']}) {hp}")
    cur = combat["participants"][combat["turn"]]
    lines.append("")
    if cur["kind"] == "player":
        lines.append(f"نوبت **{cur['name']}** است!")
        lines.append("🎯 `/attack <دشمن>` | ✨ `/cast <طلسم> <هدف>` | ⏭️ `/skip`")
    else:
        lines.append(f"نوبت دشمن: **{cur['name']}**...")
    return "\n".join(lines)


def _next_alive(combat: dict, start_idx: int) -> int:
    """اولین شرکت‌کننده‌ای که هنوز کامل نمرده بعد از start_idx (چرخشی).

    بازیکن زمین‌گیر (hp=0) هم واجد نوبت است (برای death save)؛ فقط اگر
    فلگ dead=True باشد از گردش خارج می‌شود.
    """
    n = len(combat["participants"])
    for step in range(1, n + 1):
        idx = (start_idx + step) % n
        p = combat["participants"][idx]
        if p.get("dead"):
            continue
        if p["kind"] == "monster" and not p.get("alive", False):
            continue
        return idx
    return start_idx


def _goto_next(combat):
    """حرکت به نوبت بعدی شرکت‌کننده زنده؛ در صورت عبور از پایان لیست، round را زیاد می‌کند."""
    n = len(combat["participants"])
    if n == 0:
        return
    cur_idx = combat["turn"]
    nxt = _next_alive(combat, cur_idx)
    if nxt <= cur_idx:
        combat["round"] += 1
    combat["turn"] = nxt
    nxt_p = combat["participants"][nxt]
    # وضعیت دفاع (Dodge) فقط تا شروع نوبت بعدی همین بازیکن دوام دارد
    if "dodge" in nxt_p.get("conditions", []):
        nxt_p["conditions"].remove("dodge")
    # وقتی نوبت به یک بازیکن می‌رسد، در صورت زنده بودن، وضعیت downed از نوبت قبل پاک شود
    if nxt_p.get("kind") == "player" and not nxt_p.get("dead") and nxt_p.get("hp", 0) > 0:
        nxt_p["downed"] = False


def _run_pending_monsters(session: Session, messages: list, advance_first: bool):
    """همه نوبت‌های پشت‌سرهم هیولاها را اجرا می‌کند تا به یک بازیکن برسد."""
    combat = session.combat
    n = len(combat["participants"])
    if advance_first:
        _goto_next(combat)
    safety = 0
    while safety < n + 1:
        safety += 1
        p = combat["participants"][combat["turn"]]
        if p["kind"] == "player":
            break
        # هیولای مرده را رد کن
        if p.get("dead") or not p.get("alive", True):
            _goto_next(combat)
            continue
        messages.append(auto_act(session, p))
        _goto_next(combat)


def advance(session: Session) -> str:
    """به نوبت بعدی برو؛ اگر دشمن باشد خودکار عمل می‌کند."""
    combat = session.combat
    n = len(combat["participants"])
    if n == 0:
        return "هیچ‌کس در میدان نیست!"

    messages = []
    # پایان خودکار نبرد اگر همه دشمنان مرده باشند (پیروزی)
    monsters = [p for p in combat["participants"] if p["kind"] == "monster"]
    if monsters and all(not m.get("alive", False) for m in monsters):
        messages.append(end_combat(session))
        return "\n\n".join(messages)
    # پایان خودکار نبرد اگر همه بازیکن‌ها زمین‌گیر/مرده باشند (شکست)
    if _all_players_incapacitated(session):
        messages.append(end_combat(session))
        return "\n\n".join(messages)
    _run_pending_monsters(session, messages, advance_first=True)
    if not session.combat:
        return "\n\n".join(messages)
    # بعد از اجرای هیولاها هم چک کن
    monsters2 = [p for p in session.combat["participants"] if p["kind"] == "monster"]
    if monsters2 and all(not m.get("alive", False) for m in monsters2):
        messages.append(end_combat(session))
        return "\n\n".join(messages)
    if _all_players_incapacitated(session):
        messages.append(end_combat(session))
        return "\n\n".join(messages)
    cur = combat["participants"][combat["turn"]]
    messages.append(f"— نوبت **{cur['name']}** (دور {combat['round']})")
    if cur["kind"] == "player":
        if cur.get("dead"):
            messages.append("☠️ این کاراکتر مرده است.")
        elif cur.get("downed") or cur.get("hp", 1) <= 0:
            messages.append("💀 تو زمین‌گیر شدی! برای نجات از مرگ: `/deathsave`")
        else:
            messages.append("🎯 `/attack <دشمن>` | ✨ `/cast <طلسم> <هدف>` | 🛡️ `/dodge` | ⏭️ `/skip`")
    return "\n\n".join(messages)


def run_initial_monsters(session: Session) -> str:
    """در شروع نبرد، همه نوبت‌های پشت‌سرهم هیولاها را از نقطه شروع اجرا می‌کند
    تا نوبت به بازیکن برسد. اگر اولین نوبت خود بازیکن بود، هیچ کاری نمی‌کند."""
    combat = session.combat
    if not combat or not combat.get("participants"):
        return ""
    messages = []
    first = combat["participants"][combat["turn"]]
    if first["kind"] == "monster":
        # از مکان فعلی شروع کن (بدون جلو رفتن اولیه)، تا نوبت به بازیکن برسد
        _run_pending_monsters(session, messages, advance_first=False)
    if not messages:
        return ""
    cur = combat["participants"][combat["turn"]]
    messages.append(f"— نوبت **{cur['name']}** (دور {combat['round']})")
    if cur["kind"] == "player" and not cur.get("dead") and not cur.get("downed"):
        messages.append("🎯 `/attack <دشمن>` | ✨ `/cast <طلسم> <هدف>` | 🛡️ `/dodge` | ⏭️ `/skip`")
    elif cur["kind"] == "player":
        messages.append("💀 نوبت توست اما زمین‌گیر شدی: `/deathsave`")
    return "\n\n".join(messages)


def auto_act(session: Session, mon: dict) -> str:
    """دشمن با حمله (و در صورت نیاز multiattack) به بازیکن زنده حمله می‌کند.
    dodge بازیکن باعث می‌شود حمله‌ها با ضعف (disadvantage) انجام شوند."""
    players = [p for p in session.combat["participants"]
               if p["kind"] == "player"
               and not p.get("dead")
               and not p.get("downed")
               and p.get("alive", True)
               and p.get("hp", 0) > 0]
    if not players:
        return f"☠️ {mon['name']} به دنبال هدف می‌گردد اما همه نابود شده‌اند..."
    atk_bonus = int(mon.get("atk_bonus", 2))
    n_atks = _MULTIATTACK.get(_monster_key(mon), 1)
    # باس‌ها چند حمله بیشتر دارند
    if mon.get("is_boss"):
        n_atks = max(n_atks, 2)
    parts = []
    # قابلیت ویژه باس در اولین نوبت — افکت مکانیکی واقعی
    boss_ability_used = mon.get("_ability_used", False)
    if mon.get("is_boss") and not boss_ability_used and mon.get("ability"):
        mon["_ability_used"] = True
        ability = (mon.get("ability") or "").lower()
        parts.append(f"👑 **{mon['name']}** از قابلیت ویژه استفاده می‌کند: _{mon['ability']}_!")
        # ۱) احضار هم‌دست (کلمات کلیدی: احضار، صدا زدن، کمک، summon)
        if any(k in ability for k in ("احضار", "کمک", "صدا زدن", "مینیون", "سرباز", "summon", "call")):
            from .dice import roll_dice
            add_count = 1 + roll_dice(2)  # ۲-۳ هم‌دست
            from .rules import MONSTERS
            minion_opts = [k for k in ("goblin", "skeleton", "kobold", "bandit", "wolf", "giant_rat") if k in MONSTERS]
            if minion_opts:
                for _ in range(add_count):
                    mk = random.choice(minion_opts)
                    template = MONSTERS[mk]
                    init = roll_dice(20) + 2
                    parts.append(f"👹 **{template['fa']}** به میدان می‌رسد!")
                    session.combat["participants"].append({
                        "kind": "monster", "name": template["fa"],
                        "key": mk, "hp": template["hp"], "max_hp": template["hp"],
                        "ac": template["ac"], "atk": template["atk"],
                        "atk_bonus": template.get("atk_bonus", 2),
                        "xp": template["xp"] // 2,
                        "alive": True, "conditions": [], "init": init - 2,  # بعد از باس
                        "emoji": template.get("emoji", "👹"),
                    })
                # لیست initiative را دوباره مرتب کن
                session.combat["participants"].sort(key=lambda p: -p["init"])
        # ۲) ضربه AoE / فریاد ترس (کلمات: فریاد، غرش، وحشت، ترس، AoE، همه)
        elif any(k in ability for k in ("فریاد", "غرش", "وحشت", "ترس", "aoc", "همه", "بمب", "انفجار")):
            from .dice import roll_dice
            dmg = roll_dice(8) + mon.get("atk_bonus", 3)
            parts.append(f"💥 موجی از قدرت همه بازیکنان را در بر می‌گیرد!")
            for p in session.combat["participants"]:
                if p["kind"] == "player" and p.get("alive") and p.get("hp", 0) > 0:
                    # WIS save half
                    ch = session.get_char(int(p.get("uid", 0)))
                    if ch:
                        from .rules import ability_mod
                        save = roll_dice(20) + ability_mod(ch.abilities.get("WIS", 10))
                        if save >= 13:
                            d = max(1, dmg // 2)
                            parts.append(f"🛡️ {ch.name} با موفقیت مقاومت می‌کند و {d} آسیب می‌خورد.")
                        else:
                            d = dmg
                            p["conditions"] = list(set(p.get("conditions", []) + ["ترسیده"]))
                            parts.append(f"😱 {ch.name} ترسیده و {d} آسیب می‌خورد!")
                        p["hp"] = max(0, p["hp"] - d)
                        if p["hp"] <= 0:
                            p["downed"] = True
                            parts.append(f"💔 {ch.name} زمین‌گیر شد!")
            # همه آسیب دیدن نوبت یک بارس
        # ۳) التیام / دیوفالت: زره باس بالا می‌رود
        elif any(k in ability for k in ("زره", "دفاع", "سپر", "shield", "heal", "درمان")):
            mon["ac"] = mon.get("ac", 12) + 2
            heal = 8
            mon["hp"] = min(mon.get("max_hp", mon["hp"]) + heal, mon.get("hp", 0) + heal)
            parts.append(f"🛡️ {mon['name']} خود را مقاوم‌تر می‌کند (+2 AC، {heal} HP)!")
        # ۴) در غیر این صورت فقط پیام (کازمتیک) — باس یک‌بار attack اضافه
        else:
            target = random.choice(players) if players else None
            if target:
                hit_msg, _ = _resolve_one_attack(session, mon, target, atk_bonus + 2)
                parts.append("⚡ حمله قدرتمند اضافی!\n" + hit_msg)

    target = random.choice(players)
    for _i in range(n_atks):
        hit_msg, downed = _resolve_one_attack(session, mon, target, atk_bonus)
        parts.append(hit_msg)
        if downed or target.get("hp", 0) <= 0:
            new_players = [p for p in session.combat["participants"]
                           if p["kind"] == "player"
                           and not p.get("dead")
                           and not p.get("downed")
                           and p.get("alive", True)
                           and p.get("hp", 0) > 0]
            if new_players:
                target = random.choice(new_players)
            else:
                break
    result = "\n".join(parts)
    if n_atks > 1 and not mon.get("is_boss"):
        result = f"👹 {mon['name']} **{n_atks} حمله** می‌زند!\n" + result
    session.add_log(mon["name"], result.replace("\n", " ")[:400])
    return result


def _find_target(combat: dict, name: str):
    name = name.strip().lower()
    for p in combat["participants"]:
        if p["kind"] == "monster" and p["alive"] and name in p["name"].lower():
            return p
    return None


def attack(session: Session, uid: int, target_name: str) -> str:
    combat = _combat(session)
    ch = session.get_char(uid)
    if not ch:
        return "کاراکترت در میدان نیست!"
    if combat["turn"] >= len(combat["participants"]):
        return "نبردی در جریان نیست!"
    cur = combat["participants"][combat["turn"]]
    if cur.get("uid") != str(uid):
        return f"هنوز نوبت تو نیست — نوبت {cur['name']} است!"
    if cur.get("dead"):
        return "کاراکترت مرده است."
    if ch.hp <= 0 or cur.get("downed"):
        return "تو زمین‌گیری! فقط می‌توانی `/deathsave` بزنی."

    target = _find_target(combat, target_name)
    if not target:
        names = ", ".join(p["name"] for p in combat["participants"]
                          if p["kind"] == "monster" and p["alive"])
        return f"هدف پیدا نشد. دشمنان: {names}"

    from .rules import WEAPONS
    weapon = WEAPONS[ch.weapon]
    # Rogue: اگر دشمن در کنار یال (ally) دیگری باشد Sneak Attack
    has_ally_adjacent = False
    for p in combat["participants"]:
        if p.get("kind") == "player" and p.get("uid") != str(uid) \
           and p.get("alive", True) and not p.get("dead") and not p.get("downed") \
           and p.get("hp", 0) > 0:
            has_ally_adjacent = True
            break

    # Extra Attack در سطح ۵+ برای جنگجو/بربر/پالادین/رنجر/مانک
    n_attacks = 1
    if ch.cls in ("fighter", "barbarian", "paladin", "ranger", "monk") and ch.level >= 5:
        n_attacks = 2
    if ch.cls == "fighter" and ch.level >= 11:
        n_attacks = 3
    if ch.cls == "fighter" and ch.level >= 20:
        n_attacks = 4

    parts = []
    killed = False
    for atk_i in range(n_attacks):
        if target.get("hp", 0) <= 0 or not target.get("alive", True):
            break
        raw_rolls = [roll_d20(), roll_d20()] if "dodge" in target.get("conditions", []) else [roll_d20()]
        raw = min(raw_rolls) if len(raw_rolls) == 2 else raw_rolls[0]
        atk = raw + ch.attack_bonus()
        crit = raw == 20
        fumble = raw == 1
        hit = (crit or atk >= target["ac"]) and not fumble
        tag = f" (حمله {atk_i+1})" if n_attacks > 1 else ""
        if hit:
            dmg = _roll_damage(weapon["dmg"]) + ch.stat_mod(weapon["stat"])
            sa = 0
            if ch.cls == "rogue" and has_ally_adjacent and atk_i == 0:
                sa_dice = max(1, (ch.level + 1) // 2)
                sa = sum(roll_dice(sa_dice, 6))
                dmg += sa
            if crit:
                dmg += _roll_damage(weapon["dmg"]) + ch.stat_mod(weapon["stat"])
                if ch.cls == "rogue" and has_ally_adjacent and atk_i == 0:
                    sa_dice = max(1, (ch.level + 1) // 2)
                    dmg += sum(roll_dice(sa_dice, 6))
            target["hp"] = max(0, target["hp"] - dmg)
            line = (f"🎲 {ch.name}{tag} با {weapon['fa']} به {target['name']}: {atk} "
                    f"(AC {target['ac']}) — 💥 {dmg} آسیب")
            if crit:
                line += " 🔥 **بحرانی!**"
            if sa:
                line += " 🗡️ **غافلگیرانه!**"
            parts.append(line)
            if target["hp"] <= 0:
                target["alive"] = False
                combat["xp_pool"] += target["xp"]
                killed = True
        else:
            miss_tag = " — لغزش دست!" if fumble else " — خطا!"
            parts.append(f"🎲 {ch.name}{tag} با {weapon['fa']} به {target['name']}: {atk} (AC {target['ac']}){miss_tag}")
    result = "\n".join(parts)
    if killed:
        result += f"\n☠️ **{target['name']} نابود شد!** (+{target['xp']} XP به خزانه گروه)"
    session.add_log(ch.name, result.replace("\n", " ")[:400])
    return result


def dodge(session: Session, uid: int) -> str:
    """اقدام دفاعی: حمله‌ها علیه بازیکن تا نوبت بعدی با ضعف انجام می‌شوند."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    if cur.get("downed") or cur.get("dead") or cur.get("hp", 1) <= 0:
        return "در وضعیت مرگ نمی‌توانی دفاع کنی — `/deathsave` بزن."
    if "dodge" not in cur.setdefault("conditions", []):
        cur["conditions"].append("dodge")
    session.add_log(cur["name"], "حالت دفاعی گرفت (Dodge)")
    return f"🛡️ {cur['name']} دفاع کرد؛ حمله‌ها علیه او با ضعف خواهند بود."


def cast(session: Session, uid: int, spell_key: str, target_name: str = "") -> str:
    combat = _combat(session)
    ch = session.get_char(uid)
    if not ch or ch.hp <= 0:
        return "کاراکترت در میدان نیست!"
    if combat["turn"] >= len(combat["participants"]):
        return "نبردی در جریان نیست!"
    cur = combat["participants"][combat["turn"]]
    if cur.get("uid") != str(uid):
        return f"هنوز نوبت تو نیست — نوبت {cur['name']} است!"
    if cur.get("dead"):
        return "کاراکترت مرده است."
    if ch.hp <= 0 or cur.get("downed"):
        return "تو زمین‌گیری! فقط می‌توانی `/deathsave` بزنی."

    spell = SPELLS.get(spell_key.lower())
    if not spell:
        from .rules import SPELLS as S
        return f"طلسم پیدا نشد. طلسم‌ها: {', '.join('`' + k + '`' for k in S)}"

    castable = ch.cls in ("wizard", "sorcerer", "bard", "warlock", "cleric", "druid", "paladin", "ranger", "monk")
    if not castable and spell_key.lower() != "curewounds":
        return f"کلاس {ch.cls} اهل جادو نیست! 🥊"
    cantrips = {"firebolt", "eldritchblast", "sacredflame"}
    if spell_key.lower() not in cantrips and not ch.spend_slot(1):
        return "🪄 جایگاه طلسم سطح ۱ نداری؛ استراحت طولانی کن."
    if spell["kind"] == "heal":
        target = None
        if target_name:
            for p in combat["participants"]:
                if p["kind"] == "player" and target_name.lower() in p["name"].lower():
                    target = p
                    break
        if not target:
            target = cur
        healed = sum(roll_dice(1, 8)) + ch.spell_mod()
        if target["kind"] == "player":
            real_char = session.get_char(int(target["uid"]))
            if real_char:
                healed = real_char.heal(healed)
                target["hp"] = real_char.hp
                if real_char.hp > 0:
                    target["downed"] = False
                    target["alive"] = True
                    real_char.death_saves = {"success": 0, "fail": 0}
        result = f"💚 {ch.name} طلسم «{spell['fa']}» را روی {target['name']} می‌اندازد... +{healed} HP"
        session.add_log(ch.name, result)
        return result

    target = _find_target(combat, target_name)
    if not target:
        names = ", ".join(p["name"] for p in combat["participants"]
                          if p["kind"] == "monster" and p["alive"])
        return f"هدف پیدا نشد. دشمنان: {names}"

    if spell["kind"] == "auto":
        dmg = _roll_damage(spell["dmg"])
        target["hp"] = max(0, target["hp"] - dmg)
        result = f"✨ {ch.name} «{spell['fa']}» می‌اندازد: {dmg} آسیب به {target['name']}!"
    else:  # attack roll
        raw = roll_d20()
        atk = raw + ch.spell_mod() + 2
        crit = raw == 20
        fumble = raw == 1
        hit = (crit or atk >= target["ac"]) and not fumble
        if hit:
            dmg = _roll_damage(spell["dmg"])
            if crit:
                dmg += _roll_damage(spell["dmg"])
            target["hp"] = max(0, target["hp"] - dmg)
            result = f"✨ {ch.name} «{spell['fa']}» می‌اندازد: {atk} (AC {target['ac']}) — 💥 {dmg} آسیب!"
            if crit:
                result += " 🔥 بحرانی!"
        else:
            result = f"✨ {ch.name} «{spell['fa']}» می‌اندازد: {atk} (AC {target['ac']}) — خطا!"
    if target["hp"] <= 0:
        target["alive"] = False
        combat["xp_pool"] += target["xp"]
        result += f"\n☠️ **{target['name']} نابود شد!** (+{target['xp']} XP)"
    session.add_log(ch.name, result.replace("\n", " "))
    return result


def _all_players_incapacitated(session) -> bool:
    """اگر بازیکنی نمرده/زمین‌گیر نشده، False. در غیر این صورت True.
    این فقط برای پایان **زودهنگام** نبرد استفاده می‌شود (شکست قبل از کشتن دشمن)."""
    combat = session.combat
    if not combat:
        return False
    players = [p for p in combat["participants"] if p["kind"] == "player" and not p.get("dead")]
    if not players:
        return True
    # اگر همه بازیکن‌ها زمین‌گیر شده‌اند، بسته به وضعیت نبرد تصمیم می‌گیریم:
    # - اگر هیچ هیولایی کشته نشده → شکست زودهنگام
    # - اگر همه هیولاها مرده‌اند → پیروزی (پایان خودکار در advance چک می‌شود)
    # - در حالت میانه (چند کشته ولی هنوز دشمن هست) → نبرد ادامه می‌یابد تا
    #   بازیکن در نوبتش death_save بزند و شانس به هوش آمدن داشته باشد
    return all(p.get("downed") or p.get("hp", 0) <= 0 for p in players)


def end_combat(session: Session) -> str:
    combat = session.combat
    monsters = [p for p in combat["participants"] if p["kind"] == "monster"]
    # بازیکن آگاه = کسی که نمرده و زمین‌گیر نشده (hp>0)
    alive_players = [p for p in combat["participants"]
                     if p["kind"] == "player" and not p.get("dead")
                     and not p.get("downed") and p.get("hp", 0) > 0]
    all_monsters_dead = bool(monsters) and all(not m.get("alive", False) for m in monsters)
    total_party_kill = not alive_players  # همه بازیکن‌ها زمین‌گیر یا مرده

    if all_monsters_dead:
        # پیروزی: حتی اگر یک یا چند بازیکن زمین‌گیر شده باشند
        victory = True
    elif total_party_kill:
        # شکست: همه بازیکن‌ها زمین‌گیر شده‌اند
        for p in combat["participants"]:
            if p["kind"] == "player" and p.get("downed"):
                p["downed"] = False
                p["alive"] = True
                ch = session.get_char(int(p["uid"]))
                if ch:
                    ch.hp = max(1, ch.hp)
        victory = False
    else:
        # حالت میانه: نه همه هیولاها مرده و نه همه بازیکن‌ها.
        # این یعنی مثلاً یک هیولا زنده مانده و یک بازیکن در نوبت مرگ‌سیو است.
        # برای جلوگیری از حلقه بی‌نهایت، نبرد را با شکست تمام می‌کنیم.
        for p in combat["participants"]:
            if p["kind"] == "player" and p.get("downed"):
                p["downed"] = False
                p["alive"] = True
                ch = session.get_char(int(p["uid"]))
                if ch:
                    ch.hp = max(1, ch.hp)
        victory = False

    # همگام‌سازی نهایی HP از participants به کاراکترهای واقعی
    for p in combat.get("participants", []):
        if p.get("kind") != "player":
            continue
        ch = session.get_char(int(p["uid"]))
        if not ch:
            continue
        ch.hp = max(0, int(p.get("hp", ch.hp)))
        if p.get("dead"):
            ch.hp = 0
        # اگر برنده بودیم و hp کاراکتر 0 بود (downed) به 1 برمی‌گردد
        if not victory and (p.get("downed") or ch.hp <= 0):
            ch.hp = 1
            p["downed"] = False
            p["hp"] = 1
            p["alive"] = True

    # XP را از هیولاهایی که واقعاً کشته شده‌اند محاسبه کن
    killed = [p for p in combat.get("participants", [])
              if p.get("kind") == "monster" and not p.get("alive", True)]
    xp_pool = int(combat.get("xp_pool", 0)) + sum(int(p.get("xp", 0)) for p in killed)
    # XP بین همه بازیکنانی که نمرده‌اند تقسیم می‌شود (شامل کسانی که در پایان زنده شدند)
    recipients = [p for p in combat["participants"]
                  if p.get("kind") == "player" and not p.get("dead")]
    # پیروزی کامل → تمام XP. در غیر این صورت نصف XP برای شرکت‌کنندگان
    factor = 1.0 if victory else 0.5
    share = int(xp_pool * factor) // max(1, len(recipients))
    leveled = []
    if share > 0:
        for p in recipients:
            ch = session.get_char(int(p["uid"]))
            if ch:
                ch.xp += share
                if ch.can_level_up():
                    info = ch.level_up()
                    leveled.append(f"🎉 **{ch.name}** به سطح {info['new']} رسید! (+{info['hp_gain']} HP)")
    # لوت/گنج (فقط در پیروزی)
    loot_lines = ""
    if victory:
        drops = _roll_loot(victory=True, party_size=max(1, len(recipients)), xp_pool=int(xp_pool * factor))
        if drops:
            loot_lines = "\n💎 **گنج و غنیمت:**\n" + _apply_loot(session, drops)

    session.combat = None
    session.state = "playing"
    if victory:
        msg = f"🏆 **پیروزی!** همه دشمنان نابود شدند. هر بازیکن {share} XP گرفت."
    elif total_party_kill:
        msg = f"🏳️ **شکست!** همه اعضای گروه زمین‌گیر شدند. دشمنان پراکنده می‌شوند و شما بعداً با ۱ HP به هوش می‌آیید. ({share} XP بابت تلفات وارده)"
    else:
        msg = f"🏳️ نبرد پایان یافت. ({share} XP باطر نبرد)"
    if leveled:
        msg += "\n" + "\n".join(leveled)
    if loot_lines:
        msg += loot_lines
    session.add_log("سیستم", msg.replace("\n", " ")[:600])
    return msg
