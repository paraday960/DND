# -*- coding: utf-8 -*-
"""موتور نبرد — نوبت‌بندی، حمله، طلسم، دشمنان هوشمند و توزیع XP."""
import random

from .dice import DiceError, parse_dice, roll_dice, roll_d20
from .models import Session
from .rules import MONSTERS, SPELLS, ability_mod


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
    return current.get("kind") == "player" and current.get("uid") == str(uid) and current.get("alive", False)


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

    # بازیکنان زنده
    for uid, p in session.players.items():
        ch = p["char"]
        if not ch or ch.hp <= 0:
            continue
        init = roll_d20() + ability_mod(ch.abilities["DEX"])
        combat["participants"].append({
            "kind": "player", "uid": uid, "name": ch.name,
            "init": init, "hp": ch.hp, "max_hp": ch.max_hp,
            "ac": ch.ac, "alive": True, "conditions": list(ch.conditions),
        })

    # دشمنان از سناریو
    monsters = []
    if session.scenario and session.scenario.get("encounters"):
        for e in session.scenario["encounters"]:
            name = e.get("name", "دشمن")
            count = max(1, int(e.get("count", 1)))
            base = MONSTERS.get(name.lower()) or {}
            for i in range(count):
                monsters.append({
                    "kind": "monster",
                    "name": f"{base.get('fa', name)} {i + 1}" if count > 1 else base.get("fa", name),
                    "init": roll_d20() + int(e.get("init_bonus", 1)),
                    "hp": int(e.get("hp", base.get("hp", 10))),
                    "max_hp": int(e.get("hp", base.get("hp", 10))),
                    "ac": int(e.get("ac", base.get("ac", 12))),
                    "dmg": e.get("dmg", base.get("dmg", "1d6+2")),
                    "xp": int(e.get("xp", base.get("xp", 50))),
                    "alive": True, "conditions": [],
                })
    if not monsters:
        # نبرد پیش‌فرض برای وقتی سناریویی نیست
        for i in range(2):
            monsters.append({
                "kind": "monster", "name": f"گابلین {i + 1}",
                "init": roll_d20() + 2, "hp": 7, "max_hp": 7, "ac": 15,
                "dmg": "1d6+2", "xp": 50, "alive": True, "conditions": [],
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
    """اولین شرکت‌کننده زنده بعد از start_idx (چرخشی)."""
    n = len(combat["participants"])
    for step in range(1, n + 1):
        idx = (start_idx + step) % n
        if combat["participants"][idx]["alive"]:
            return idx
    return start_idx


def advance(session: Session) -> str:
    """به نوبت بعدی برو؛ اگر دشمن باشد خودکار عمل می‌کند."""
    combat = session.combat
    n = len(combat["participants"])
    if n == 0:
        return "هیچ‌کس در میدان نیست!"
    cur_idx = combat["turn"]
    nxt = _next_alive(combat, cur_idx)
    if nxt <= cur_idx:
        combat["round"] += 1
    combat["turn"] = nxt

    messages = []
    # نوبت‌های دشمن خودکار اجرا می‌شوند
    for _ in range(n + 1):
        p = combat["participants"][combat["turn"]]
        if p["kind"] == "player":
            break
        messages.append(auto_act(session, p))
        if not p["alive"]:
            nxt2 = _next_alive(combat, combat["turn"])
            if nxt2 <= combat["turn"]:
                combat["round"] += 1
            combat["turn"] = nxt2

    cur = combat["participants"][combat["turn"]]
    messages.append(f"— نوبت **{cur['name']}** (دور {combat['round']})")
    if cur["kind"] == "player":
        messages.append("🎯 `/attack <دشمن>` | ✨ `/cast <طلسم> <هدف>` | ⏭️ `/skip`")
    return "\n\n".join(messages)


def auto_act(session: Session, mon: dict) -> str:
    """دشمن به نزدیک‌ترین بازیکن زنده حمله می‌کند."""
    players = [p for p in session.combat["participants"]
               if p["kind"] == "player" and p["alive"]]
    if not players:
        return f"☠️ {mon['name']} به دنبال هدف می‌گردد اما همه نابود شده‌اند..."
    target = random.choice(players)
    atk = roll_d20() + 2
    hit = atk >= target["ac"]
    crit = atk == 20
    if hit:
        dmg = _roll_damage(mon.get("dmg", "1d6+0"))
        if crit:
            dmg *= 2
        target["hp"] = max(0, target["hp"] - dmg)
        result = (f"🎲 {mon['name']} به {target['name']} حمله کرد: {atk} "
                  f"(AC {target['ac']}) {'— 💥 اصابت! ' + str(dmg) + ' آسیب' if hit else '— خطا!'}")
        if target["hp"] <= 0:
            target["alive"] = False
            real_char = session.get_char(int(target["uid"]))
            if real_char:
                real_char.hp = 0
                real_char.death_saves = {"success": 0, "fail": 0}
            result += f"\n💀 **{target['name']} از پا درآمد!**"
    else:
        result = f"🎲 {mon['name']} به {target['name']} حمله کرد: {atk} (AC {target['ac']}) — بی‌اثر!"
    session.add_log(mon["name"], result.replace("\n", " "))
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
    if not ch or ch.hp <= 0:
        return "کاراکترت در میدان نیست!"
    if combat["turn"] >= len(combat["participants"]):
        return "نبردی در جریان نیست!"
    cur = combat["participants"][combat["turn"]]
    if cur.get("uid") != str(uid):
        return f"هنوز نوبت تو نیست — نوبت {cur['name']} است!"

    target = _find_target(combat, target_name)
    if not target:
        names = ", ".join(p["name"] for p in combat["participants"]
                          if p["kind"] == "monster" and p["alive"])
        return f"هدف پیدا نشد. دشمنان: {names}"

    from .rules import WEAPONS
    weapon = WEAPONS[ch.weapon]
    rolls = [roll_d20(), roll_d20()] if "dodge" in target.get("conditions", []) else [roll_d20()]
    atk = (min(rolls) if len(rolls) == 2 else rolls[0]) + ch.attack_bonus()
    crit = atk == 20
    hit = crit or atk >= target["ac"]
    if hit:
        dmg = _roll_damage(weapon["dmg"]) + ch.stat_mod(weapon["stat"])
        if crit:
            dmg += _roll_damage(weapon["dmg"]) + ch.stat_mod(weapon["stat"])
        target["hp"] = max(0, target["hp"] - dmg)
        result = (f"🎲 {ch.name} با {weapon['fa']} به {target['name']}: {atk} "
                  f"(AC {target['ac']}) {'— 💥 اصابت! ' + str(dmg) + ' آسیب' if hit else ''}")
        if crit:
            result += " 🔥 **حمله بحرانی!**"
        if target["hp"] <= 0:
            target["alive"] = False
            combat["xp_pool"] += target["xp"]
            result += f"\n☠️ **{target['name']} نابود شد!** (+{target['xp']} XP به خزانه گروه)"
    else:
        result = f"🎲 {ch.name} با {weapon['fa']} به {target['name']}: {atk} (AC {target['ac']}) — خطا!"
    session.add_log(ch.name, result.replace("\n", " "))
    return result


def dodge(session: Session, uid: int) -> str:
    """اقدام دفاعی: حمله‌ها علیه بازیکن تا نوبت بعدی با ضعف انجام می‌شوند."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
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
        atk = roll_d20() + ch.spell_mod() + 2
        crit = atk == 20
        hit = crit or atk >= target["ac"]
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


def end_combat(session: Session) -> str:
    combat = session.combat
    monsters = [p for p in combat["participants"] if p["kind"] == "monster"]
    alive_players = [p for p in combat["participants"] if p["kind"] == "player" and p["alive"]]
    all_dead = monsters and all(not m["alive"] for m in monsters)

    if all_dead and alive_players:
        victory = True
    else:
        victory = False

    xp_pool = combat.get("xp_pool", 0)
    share = xp_pool // len(alive_players) if alive_players else 0
    leveled = []
    if victory and share > 0:
        for p in alive_players:
            ch = session.get_char(int(p["uid"]))
            if ch:
                ch.xp += share
                if ch.can_level_up():
                    info = ch.level_up()
                    leveled.append(f"🎉 **{ch.name}** به سطح {info['new']} رسید! (+{info['hp_gain']} HP)")
    session.combat = None
    session.state = "playing"
    if victory:
        msg = f"🏆 **پیروزی!** همه دشمنان نابود شدند. هر بازیکن زنده {share} XP گرفت."
    else:
        msg = f"🏳️ نبرد پایان یافت. گروه عقب‌نشینی کرد. (XP توزیع نشد)"
    if leveled:
        msg += "\n" + "\n".join(leveled)
    session.add_log("سیستم", msg.replace("\n", " "))
    return msg
