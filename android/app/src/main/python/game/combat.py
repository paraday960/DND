# -*- coding: utf-8 -*-
"""موتور نبرد D&D 5e — اکشن، بونس‌اکشن، ری‌اکشن، حمله فرصت، وضعیت‌ها، مزیت/ضعف."""
import random

from .dice import DiceError, parse_dice, roll_dice, roll_d20
from .models import Session
from .rules import (
    CLASSES, MONSTERS, SPELLS, WEAPONS, WEAPON_RANGES, CONDITIONS,
    ability_mod, proficiency_bonus,
)


# ---------------------- توابع کمکی D&D ----------------------
def roll_adv_disadv(adv=False, dis=False):
    """رول d20 با مزیت (advantage) یا ضعف (disadvantage). اگر هر دو true باشند لغو می‌شوند."""
    if adv and dis:
        adv, dis = False, False
    r1 = roll_d20()
    if not adv and not dis:
        return r1, [r1], None
    r2 = roll_d20()
    if adv:
        return max(r1, r2), [r1, r2], "adv"
    return min(r1, r2), [r1, r2], "dis"


def roll_with_mods(base_mod=0, adv=False, dis=False, crit_on=20):
    """یک رول d20 به همراه مودیفایر و مزیت/ضعف انجام می‌دهد. خروجی: (total, raw, rolls, is_crit, is_fumble, mode)"""
    raw, rolls, mode = roll_adv_disadv(adv, dis)
    crit = (raw == crit_on)
    fumble = (raw == 1)
    total = raw + base_mod
    return total, raw, rolls, crit, fumble, mode


def get_participant_ch(session, p):
    """اگر participant بازیکن باشد کاراکتر واقعی‌اش را برمی‌گرداند."""
    if p.get("kind") != "player":
        return None
    return session.get_char(int(p.get("uid", 0)))


def has_condition(p, cond):
    """چک کردن اینکه یک شرکت‌کننده وضعیت خاصی دارد یا نه."""
    return cond in p.get("conditions", [])


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


def _calc_attack_adv_dis(attacker, target, is_ranged=False):
    """محاسبه مزیت و ضعف برای حمله attacker به target."""
    adv = False
    dis = False
    reasons = []
    # وضعیت‌های حمله‌کننده
    if has_condition(attacker, "blinded") or has_condition(attacker, "poisoned") or \
       has_condition(attacker, "frightened") or has_condition(attacker, "restrained") or \
       has_condition(attacker, "prone") and not is_ranged:
        dis = True
        reasons.append("در وضعیت نامناسب")
    if has_condition(attacker, "invisible") or has_condition(attacker, "hidden"):
        adv = True
        reasons.append("نامرئی/مخفی")
    # وضعیت‌های هدف
    if has_condition(target, "blinded") or has_condition(target, "restrained") or \
       has_condition(target, "stunned") or has_condition(target, "unconscious") or \
       has_condition(target, "paralyzed") or has_condition(target, "prone") and not is_ranged:
        adv = True
        reasons.append("هدف در وضعیت آسیب‌پذیر")
    if has_condition(target, "dodge"):
        dis = True
        reasons.append("هدف در حالت دفاع فعال")
    if has_condition(target, "invisible"):
        dis = True
        reasons.append("هدف نامرئی")
    if has_condition(target, "prone") and is_ranged:
        dis = True
        reasons.append("هدف روی زمین و حمله دوربرد")
    # اگر هدف paralyzed/unconscious باشد و حمله نزدیک، کریت روی ۵ فوت اتوماتیک است
    auto_crit_melee = (has_condition(target, "paralyzed") or has_condition(target, "unconscious")) and not is_ranged
    if auto_crit_melee:
        adv = True
    # کمک هم‌گروهی
    if attacker.get("helped_by"):
        adv = True
        reasons.append("هم‌گروهی کمک کرده")
    return adv, dis, reasons, auto_crit_melee


def _apply_damage_resistance(session, target, dmg, dmg_type="bludgeoning"):
    """اعمال مقاومت/آسیب‌پذیری/ایمنی. خروجی: (damage_after, tags)"""
    tags = []
    # خشم بربر مقاومت در برابر آسیب‌های فیزیکی می‌دهد
    if target.get("kind") == "player" and session is not None:
        real_char = get_participant_ch(session, target)
        if real_char and getattr(real_char, "rage_active", False):
            if dmg_type in ("bludgeoning", "piercing", "slashing"):
                dmg = max(1, dmg // 2)
                tags.append("مقاومت (خشم)")
    return max(0, dmg), tags


def _resolve_one_attack(session, attacker, target, atk_bonus, dmg_expr=None,
                        dmg_type="bludgeoning", is_ranged=False, extra_dmg_dice=None,
                        dmg_modifier=0, adv_override=None, dis_override=None,
                        critical=False) -> tuple:
    """یک حمله منفرد را اجرا می‌کند. خروجی: (lines_text, target_was_downed).
    
    نکته مهم قانون D&D: در کریت فقط **تاس‌های آسیب** دو برابر می‌شوند، modifier عدد ثابت اضافه نمی‌شود.
    """
    adv, dis, reasons, auto_crit = _calc_attack_adv_dis(attacker, target, is_ranged)
    if adv_override:
        adv = True
    if dis_override:
        dis = True
    # حمله دوربرد در ۵ فوت دشمن، با ضعف
    if is_ranged and not has_condition(target, "prone"):
        if target.get("distance", 0) == 0:
            dis = True
            reasons.append("حمله دور در نزدیکی دشمن")
    # هالفلینگ: رول ۱ را دوباره می‌اندازد (luck)
    attacker_ch = get_participant_ch(session, attacker)
    raw, rolls, mode = roll_adv_disadv(adv, dis)
    if attacker_ch and attacker_ch.race == "halfling" and raw == 1 and not attacker_ch.resources.get("luck_used", False):
        raw2 = roll_d20()
        rolls.append(raw2)
        raw = raw2
        attacker_ch.resources["luck_used"] = True
        reasons.append("شانس هالفلینگ")
    # الهام بارد اگر دارد
    insp_bonus = 0
    if attacker.get("inspiration_die"):
        die = attacker.pop("inspiration_die")
        sides = int(die[1:]) if die.startswith("d") else 6
        insp_bonus = random.randint(1, sides)
        reasons.append(f"الهام بارد +{insp_bonus}")
    atk = raw + atk_bonus + insp_bonus
    crit = (raw == 20) or auto_crit or critical
    fumble = (raw == 1)
    hit = (crit or (raw != 1 and atk >= target.get("ac", 10))) and not fumble
    lines = []
    adv_tag = ""
    if mode == "adv":
        adv_tag = f" (با مزیت، تاس‌ها {rolls[0]} و {rolls[1]})"
    elif mode == "dis":
        adv_tag = f" (با ضعف، تاس‌ها {rolls[0]} و {rolls[1]})"
    if hit:
        dmg_dice = dmg_expr or attacker.get("dmg", "1d6+0")
        # قانون کریت: فقط تاس‌ها دو برابر می‌شوند، modifier ثابت نه
        base_dice_dmg = _roll_damage(dmg_dice) - (_extract_static_mod(dmg_dice))  # فقط تاس
        static_mod = _extract_static_mod(dmg_dice) + dmg_modifier
        if crit:
            base_dice_dmg += _roll_damage(dmg_dice) - _extract_static_mod(dmg_dice)  # تاس‌های دوباره
        # تاس‌های آسیب اضافه (sneak attack, hunter's mark, smite و...)
        extra_dice_total = 0
        if extra_dmg_dice:
            for d_expr in (extra_dmg_dice if isinstance(extra_dmg_dice, list) else [extra_dmg_dice]):
                if isinstance(d_expr, str):
                    extra_dice_total += _roll_damage(d_expr) - _extract_static_mod(d_expr)
                    if crit:
                        extra_dice_total += _roll_damage(d_expr) - _extract_static_mod(d_expr)
                else:
                    extra_dice_total += int(d_expr)
        dmg = base_dice_dmg + static_mod + extra_dice_total
        dmg = max(dmg, 1)
        # اعمال مقاومت/ضعف
        dmg, res_tags = _apply_damage_resistance(session, target, dmg, dmg_type)
        target["hp"] = max(0, target.get("hp", 10) - dmg)
        # بررسی غلظت طلسم (Concentration)
        if target.get("kind") == "player":
            real_char = get_participant_ch(session, target)
            if real_char and "concentrating" in real_char.conditions and dmg > 0:
                dc = max(10, dmg // 2)
                save = roll_d20() + real_char.stat_mod("CON")
                if save < dc:
                    real_char.conditions.remove("concentrating")
                    lines.append(f"⚠️ تمرکز {target['name']} شکست! (رول {save} در برابر DC {dc})")
        line = f"🎲 {attacker['name']} به {target['name']} حمله کرد: {atk} "
        line += f"(رول {raw}{'+' + str(atk_bonus + insp_bonus) if (atk_bonus + insp_bonus) else ''}) "
        line += f"(AC {target.get('ac', 10)}){adv_tag} — 💥 اصابت! {dmg} آسیب"
        if dmg_type != "bludgeoning":
            type_fa = {"fire": "آتش", "cold": "سرما", "lightning": "برق", "acid": "اسید",
                       "poison": "سم", "necrotic": "نکروز", "radiant": "تابشی", "force": "نیرو",
                       "piercing": "سوراخ‌کننده", "slashing": "برنده"}.get(dmg_type, dmg_type)
            line += f" ({type_fa})"
        if crit:
            line += " 🔥 **بحرانی!**"
        if insp_bonus:
            line += f" 🎻 الهام +{insp_bonus}"
        if res_tags:
            line += f" [{'; '.join(res_tags)}]"
        lines.append(line)
        downed = False
        # Half-orc Relentless Endurance
        if target["hp"] <= 0:
            real_char_target = get_participant_ch(session, target)
            if real_char_target and real_char_target.race == "half_orc" and not real_char_target.resources.get("relentless_used", False):
                target["hp"] = 1
                real_char_target.hp = 1
                real_char_target.resources["relentless_used"] = True
                lines.append(f"💪 **{target['name']} (نیمه‌اورک)** با پافشاری از مرگ برگشت! (۱ HP)")
                downed = False
            else:
                target["hp"] = 0
                target["downed"] = True
                if real_char_target:
                    real_char_target.hp = 0
                    real_char_target.death_saves = {"success": 0, "fail": 0}
                lines.append(f"💀 **{target['name']} از پا درآمد!** (در نوبتت /deathsave بزن)")
                downed = True
        return "\n".join(lines), downed
    else:
        miss_tag = " — لغزش دست!" if fumble else " — خطا!"
        line = f"🎲 {attacker['name']} به {target['name']} حمله کرد: {atk} "
        line += f"(AC {target.get('ac', 10)}){adv_tag}{miss_tag}"
        return line, False


def _extract_static_mod(dmg_expr: str) -> int:
    """مقدار ثابت پایانی عبارت آسیب (مثل +3 یا -1 در 1d8+3, 2d6-1) را برمی‌گرداند."""
    try:
        count, sides, mod = parse_dice(str(dmg_expr))
        return mod
    except Exception:
        return 0



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
        # در شروع نبرد اکشن و بونس‌اکشن و ری‌اکشن همه در دسترس است
        ch.reset_turn_resources()
        combat["participants"].append({
            "kind": "player", "uid": uid, "name": ch.name,
            "emoji": CLASSES.get(ch.cls, {}).get("emoji", "🧙"),
            "init": init, "hp": ch.hp, "max_hp": ch.max_hp,
            "ac": ch.ac, "alive": True, "downed": not alive,
            "conditions": list(ch.conditions),
            "distance": 0,  # 0: نزدیک، 1: متوسط، 2: دور
            "acted": False,
            "bonus_acted": False,
            "reaction_available": True,
            "disengage_active": False,
            "helped_by": None,
            "hidden": False,
            "_attacks_this_turn": 0,
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
                    "distance": 0,
                    "acted": False,
                    "bonus_acted": False,
                    "reaction_available": True,
                    "disengage_active": False,
                    "_attacks_this_turn": 0,
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
                "distance": 0, "acted": False, "bonus_acted": False,
                "reaction_available": True, "disengage_active": False,
                "_attacks_this_turn": 0,
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


def _trigger_opportunity_attacks(session, mover, from_dist, to_dist):
    """وقتی موجودی از محدوده نزدیک (0) دور می‌شود بدون disengage، حملات فرصت را فعال می‌کند."""
    messages = []
    if mover.get("disengage_active", False):
        return messages
    if from_dist == 0 and to_dist > 0:
        # همه دشمنان نزدیک یک حمله فرصت با ری‌اکشن می‌زنند
        enemies = []
        if mover["kind"] == "player":
            enemies = [p for p in session.combat["participants"]
                       if p["kind"] == "monster" and p.get("alive") and p.get("distance", 0) == 0
                       and p.get("reaction_available", True) and p.get("hp", 0) > 0]
        else:
            enemies = [p for p in session.combat["participants"]
                       if p["kind"] == "player" and not p.get("dead")
                       and p.get("distance", 0) == 0 and p.get("reaction_available", True)
                       and p.get("hp", 0) > 0]
        for enemy in enemies:
            if enemy.get("reaction_available", True):
                enemy["reaction_available"] = False
                if enemy["kind"] == "monster":
                    atk_bonus = enemy.get("atk_bonus", 2)
                    hit_msg, _ = _resolve_one_attack(session, enemy, mover, atk_bonus)
                    messages.append(f"⚡ **حمله فرصت!** {enemy['name']} هنگام فرار {mover['name']} حمله می‌کند:\n{hit_msg}")
                else:
                    # بازیکن: حمله پایه با سلاح
                    ch = get_participant_ch(session, enemy)
                    if ch:
                        hit_msg, _ = _resolve_one_attack(session, enemy, mover, ch.attack_bonus(), dmg_expr=WEAPONS[ch.weapon]["dmg"], dmg_type="slashing" if "sword" in ch.weapon or "axe" in ch.weapon else "piercing")
                        messages.append(f"⚡ **حمله فرصت!** {enemy['name']} هنگام فرار {mover['name']} حمله می‌کند:\n{hit_msg}")
    return messages


def _goto_next(combat, session=None):
    """حرکت به نوبت بعدی شرکت‌کننده زنده؛ در صورت عبور از پایان لیست، round را زیاد می‌کند."""
    n = len(combat["participants"])
    if n == 0:
        return []
    cur_idx = combat["turn"]
    messages = []
    nxt = _next_alive(combat, cur_idx)
    if nxt <= cur_idx:
        combat["round"] += 1
    combat["turn"] = nxt
    nxt_p = combat["participants"][nxt]
    # وضعیت‌های یک‌نوبته پاک می‌شوند
    for cond in ("dodge",):
        if cond in nxt_p.get("conditions", []):
            nxt_p["conditions"].remove(cond)
    # بافت +AC سپر جادویی در شروع نوبت بعد تمام می‌شود
    if nxt_p.get("temp_ac_boost"):
        boost = nxt_p.pop("temp_ac_boost")
        nxt_p["ac"] = max(10, nxt_p["ac"] - boost)
        if nxt_p.get("kind") == "player" and session:
            ch = get_participant_ch(session, nxt_p)
            if ch:
                ch.ac = nxt_p["ac"]
    # منابع نوبت ریست می‌شوند
    nxt_p["acted"] = False
    nxt_p["bonus_acted"] = False
    nxt_p["reaction_available"] = True
    nxt_p["_attacks_this_turn"] = 0
    nxt_p["disengage_active"] = False
    nxt_p["helped_by"] = None
    nxt_p["hidden"] = False
    nxt_p["_main_attack_done"] = False
    # در نوبت بازیکن منابع کاراکتر هم ریست
    if nxt_p.get("kind") == "player" and session:
        ch = get_participant_ch(session, nxt_p)
        if ch:
            ch.reset_turn_resources()
            # مدیریت خشم بربر
            if ch.rage_active:
                ch.rage_turns += 1
                # اگر تا نوبت بعدی حمله نزده باشی یا آسیب نخورده باشی، خشم خاموش می‌شود
                if ch.rage_turns > 1:
                    ch.rage_active = False
                    ch.rage_turns = 0
                    ch.rage_dmg_bonus = 0
                    messages.append(f"😤 خشم {ch.name} فروکش کرد.")
    # وقتی نوبت به یک بازیکن می‌رسد، در صورت زنده بودن، وضعیت downed از نوبت قبل پاک شود
    if nxt_p.get("kind") == "player" and not nxt_p.get("dead") and nxt_p.get("hp", 0) > 0:
        nxt_p["downed"] = False
    return messages


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


def attack(session: Session, uid: int, target_name: str, is_bonus_offhand=False) -> str:
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
    if is_bonus_offhand:
        if cur.get("bonus_acted"):
            return "بونس‌اکشن این نوبت را قبلاً گرفتی!"
    else:
        if cur.get("acted"):
            return "در این نوبت اکشن اصلی را قبلاً گرفتی! می‌توانی بونس‌اکشن بگیری یا `/skip` کنی."

    target = _find_target(combat, target_name)
    if not target:
        names = ", ".join(p["name"] for p in combat["participants"]
                          if p["kind"] == "monster" and p["alive"])
        return f"هدف پیدا نشد. دشمنان: {names}"

    from .rules import WEAPONS
    weapon = WEAPONS[ch.weapon]
    if is_bonus_offhand and ch.weapon not in ("dagger", "scimitar", "handaxe", "rapier", "shortsword"):
        return "حمله دست دوم فقط با سلاح سبک (خنجر، شمشیر خمیده، تبر دستی و...) ممکن است!"
    weapon_range = WEAPON_RANGES.get(ch.weapon, {"type": "melee", "reach": 1.5})
    is_ranged = weapon_range.get("type") == "ranged"
    dmg_type = "piercing" if "bow" in ch.weapon or "dagger" in ch.weapon or "arrow" in ch.weapon else \
               "slashing" if "axe" in ch.weapon or "sword" in ch.weapon or "scimitar" in ch.weapon else \
               "bludgeoning" if "mace" in ch.weapon or "hammer" in ch.weapon or "staff" in ch.weapon else "bludgeoning"
    # اگر دور هستی و سلاح نزدیک، باید اول move کنی
    if cur.get("distance", 0) > 0 and weapon_range["type"] == "melee":
        return f"فاصله تو تا دشمن زیاد است! اول با `/move near` نزدیک شو."

    # تعداد حمله بر اساس Extra Attack (برای اکشن اصلی؛ بونس حمله فقط یکی می‌زند)
    n_attacks = 1
    if not is_bonus_offhand:
        if ch.cls in ("fighter", "barbarian", "paladin", "ranger", "monk") and ch.level >= 5:
            n_attacks = 2
        if ch.cls == "fighter" and ch.level >= 11:
            n_attacks = 3
        if ch.cls == "fighter" and ch.level >= 20:
            n_attacks = 4

    # بررسی مزیت برای Sneak Attack: هر حمله‌ای که با مزیت است یا هدف کنار یال است
    has_ally_adjacent = False
    for p in combat["participants"]:
        if p.get("kind") == "player" and p.get("uid") != str(uid) \
           and p.get("hp", 0) > 0 and p.get("distance", 0) == target.get("distance", 0):
            has_ally_adjacent = True
            break
    has_adv, has_dis, _, _ = _calc_attack_adv_dis(cur, target, is_ranged)

    parts = []
    killed = False
    if is_bonus_offhand:
        cur["bonus_acted"] = True
        ch.bonus_action_available = False
        if not cur.get("_main_attack_done"):
            return "حمله دست دوم (Offhand) فقط بعد از اینکه اکشن اصلی را با حمله انجام دادی ممکن است!"
    else:
        cur["acted"] = True
        cur["_main_attack_done"] = True
    ch.hidden = False
    cur["hidden"] = False
    # بونس آسیب خشم بربر
    rage_dmg = ch.rage_dmg_bonus if ch.rage_active else 0
    atk_bonus = ch.attack_bonus()
    static_dmg_mod = ch.stat_mod(weapon["stat"])
    if is_bonus_offhand:
        static_dmg_mod = 0  # حمله دست دوم پاداش توانایی به آسیب نمی‌گیرد (جز استثنائاتی که ساده‌سازی می‌کنیم)
    # آسیب mark (hunter's mark/hex)
    marked_dice = []
    if cur.get("marked_target") == target["name"]:
        marked_dice.append("1d6")

    for atk_i in range(n_attacks):
        if target.get("hp", 0) <= 0 or not target.get("alive", True):
            break
        extra_dice = []
        # Sneak Attack راگ: فقط در اولین حمله هر نوبت که مزیت دارد یا هم‌گروهی نزدیک است
        if ch.cls == "rogue" and atk_i == 0 and (has_adv or has_ally_adjacent or cur.get("helped_by") or cur.get("hidden")):
            sa_dice_count = max(1, (ch.level + 1) // 2)
            extra_dice.append(f"{sa_dice_count}d6")
            parts.append(f"🗡️ **حمله غافلگیرانه!**")
        extra_dice.extend(marked_dice)
        hit_msg, downed = _resolve_one_attack(
            session, cur, target, atk_bonus,
            dmg_expr=weapon["dmg"], dmg_type=dmg_type,
            is_ranged=is_ranged,
            extra_dmg_dice=extra_dice if extra_dice else None,
            dmg_modifier=static_dmg_mod + rage_dmg,
        )
        parts.append(hit_msg)
        if target.get("hp", 0) <= 0:
            target["alive"] = False
            combat["xp_pool"] += target["xp"]
            killed = True
            break
    # پاک کردن کمک هم‌گروهی بعد از حمله
    if cur.get("helped_by"):
        cur["helped_by"] = None
    result = "\n".join(parts)
    if killed:
        result += f"\n☠️ **{target['name']} نابود شد!** (+{target['xp']} XP به خزانه گروه)"
    # خشم بربر: حمله زدی پس ادامه پیدا می‌کند
    if ch.rage_active:
        ch.rage_turns += 1
    if is_bonus_offhand:
        result = "🗡️ **حمله دست دوم (Two-Weapon Fighting)!**\n" + result
    session.add_log(ch.name, result.replace("\n", " ")[:400])
    return result


def offhand_attack(session: Session, uid: int, target_name: str = "") -> str:
    """حمله با دست دوم به عنوان بونس‌اکشن."""
    combat = _combat(session)
    if not target_name:
        # هدف آخرین هدف attacked
        for p in reversed(combat.get("participants", [])):
            if p["kind"] == "monster" and p.get("alive"):
                target_name = p["name"]
                break
    return attack(session, uid, target_name, is_bonus_offhand=True)


def divine_smite(session: Session, uid: int, slot_level: int = 1) -> str:
    """Divine Smite پالادین: بعد از ضربه، اسلات می‌سوزانی تا آسیب تابشی اضافه بزنی (بونس‌اکشن یا در لحظه ضربه).
    برای سادگی به عنوان بونس‌اکشن است که آسیب را روی آخرین هدف می‌ریزد.
    """
    combat = _combat(session)
    ch = session.get_char(uid)
    if not ch:
        return "کاراکترت پیدا نشد."
    if ch.cls != "paladin":
        return "این قابلیت فقط برای پالادین است."
    cur = combat["participants"][combat["turn"]]
    if cur.get("uid") != str(uid):
        return "نوبت تو نیست."
    if cur.get("bonus_acted"):
        return "بونس‌اکشنت را استفاده کردی."
    if not ch.spend_slot(slot_level):
        return f"جایگاه طلسم سطح {slot_level} نداری!"
    # پیدا کردن آخرین هدفی که ضربه زده شد
    target = None
    for p in combat["participants"]:
        if p["kind"] == "monster" and p.get("alive") and p.get("distance", 0) == 0:
            target = p
            break
    if not target:
        # اسلات برگشته
        ch.spell_slots_used[slot_level] = max(0, ch.spell_slots_used.get(slot_level, 1) - 1)
        return "هیچ هدف نزدیک برای اسمایت پیدا نشد."
    # محاسبه آسیب اسمایت: 2d8 برای undead/fiend یک d8 اضافه (در ساده‌سازی 2d8 + 1d8 در slot بالاتر)
    dmg = sum(roll_dice(2 + (slot_level - 1), 8))
    target["hp"] = max(0, target["hp"] - dmg)
    cur["bonus_acted"] = True
    ch.bonus_action_available = False
    msg = f"✨ **Divine Smite!** انرژی الهی از سلاح {ch.name} به {target['name']} می‌تابد! 💥 {dmg} آسیب تابشی!"
    if target["hp"] <= 0:
        target["alive"] = False
        combat["xp_pool"] += target["xp"]
        msg += f"\n☠️ **{target['name']} از نور الهی سوخت و نابود شد!** (+{target['xp']} XP)"
    session.add_log(ch.name, msg)
    return msg


def move_action(session: Session, uid: int, where: str) -> str:
    """حرکت در نبرد: near/far/flee — مدیریت فاصله و حمله فرصت."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    ch = get_participant_ch(session, cur)
    if cur.get("downed") or cur.get("dead"):
        return "نمی‌توانی حرکت کنی."
    where = where.strip().lower()
    cur_dist = cur.get("distance", 0)
    msgs = []
    if where in ("near", "جلو", "نزدیک"):
        new_dist = 0
        if cur_dist == 0:
            return "همین الان در نزدیکی هستی!"
        cur["distance"] = 0
        msgs.append(f"🏃 {cur['name']} به سمت دشمنان دوید و در خط مقدم قرار گرفت!")
    elif where in ("far", "عقب", "دور"):
        new_dist = 1
        if cur_dist > 0:
            return "همین الان دور هستی!"
        # حمله فرصت
        opp = _trigger_opportunity_attacks(session, cur, cur_dist, new_dist)
        msgs.extend(opp)
        cur["distance"] = 1
        msgs.append(f"🏹 {cur['name']} به عقب رفت و در فاصله دور ایستاد (برای کمان/طلسم مناسب).")
    elif where in ("flee", "فرار"):
        new_dist = 2
        opp = []
        if not cur.get("disengage_active", False):
            opp = _trigger_opportunity_attacks(session, cur, cur_dist, 0)
        msgs.extend(opp)
        cur["distance"] = 2
        msgs.append(f"🏃💨 {cur['name']} سعی در فرار از میدان نبرد دارد! (در صورتی که در ۲ نوبت متوالی flee بزنی فرار می‌کنی)")
    return "\n".join(msgs)


def dash(session: Session, uid: int) -> str:
    """اکشن Dash: حرکت اضافه — در مدل ساده ما باعث می‌شود می‌توانی دو مرحله دور شوی/نزدیک شوی و حمله فرصت را نادیده می‌گیری اگر disengage نگرفتی."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    if cur.get("downed") or cur.get("dead"):
        return "نمی‌توانی حرکت کنی."
    cur["acted"] = True
    session.add_log(cur["name"], "اکشن دویدن (Dash) گرفت")
    return f"🏃 {cur['name']} دوید! حالا می‌توانی به `/move near|far|flee` حرکت کنی، حمله فرصت یک بار کمتر است."


def disengage(session: Session, uid: int) -> str:
    """اکشن Disengage: حرکت در این نوبت حمله فرصت ایجاد نمی‌کند."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    if cur.get("downed") or cur.get("dead"):
        return "نمی‌توانی حرکت کنی."
    cur["acted"] = True
    cur["disengage_active"] = True
    ch = get_participant_ch(session, cur)
    if ch:
        ch.disengage_active = True
    session.add_log(cur["name"], "عقب‌نشینی امن (Disengage)")
    return f"🚪 {cur['name']} عقب‌نشینی امن گرفت! حالا می‌توانی بدون حمله فرصت دور شوی (`/move flee`)."


def help_action(session: Session, uid: int, target_name: str = "") -> str:
    """اکشن Help: به هم‌گروهی در حمله بعدی به هدف مزیت می‌دهد."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    if cur.get("downed") or cur.get("dead"):
        return "نمی‌توانی کمک کنی."
    target = None
    if target_name:
        for p in session.combat["participants"]:
            if p["kind"] == "player" and p["uid"] != str(uid) and target_name.lower() in p["name"].lower():
                target = p
                break
    if not target:
        # هدف: اولین هم‌گروهی زنده
        for p in session.combat["participants"]:
            if p["kind"] == "player" and p["uid"] != str(uid) and p.get("hp", 0) > 0 and not p.get("downed"):
                target = p
                break
    if not target:
        return "هم‌گروهی برای کمک پیدا نشد."
    cur["acted"] = True
    target["helped_by"] = cur["name"]
    session.add_log(cur["name"], f"کمک کرد به {target['name']}")
    return f"🤝 {cur['name']} به {target['name']} کمک می‌کند! حمله بعدی {target['name']} با مزیت انجام می‌شود."


def hide(session: Session, uid: int) -> str:
    """اکشن Hide: چک DEX (Stealth) در مقابل میانگین passive perception دشمنان."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    ch = get_participant_ch(session, cur)
    if not ch:
        return "کاراکترت پیدا نشد."
    if cur.get("downed") or cur.get("dead"):
        return "نمی‌توانی پنهان شوی."
    cur["acted"] = True
    stealth_mod = ch.stat_mod("DEX") + (proficiency_bonus(ch.level) if "stealth" in ch.proficiencies else 0)
    roll = roll_d20() + stealth_mod
    # passive perception دشمنان: 10 + WIS
    monsters = [p for p in session.combat["participants"] if p["kind"] == "monster" and p.get("alive")]
    if not monsters:
        cur["hidden"] = True
        ch.hidden = True
        return f"🙈 {cur['name']} پنهان شد! هیچ دشمنی در میدان نیست."
    avg_pp = 10 + 2  # برای سادگی
    success = roll >= avg_pp
    if success:
        cur["hidden"] = True
        ch.hidden = True
        session.add_log(cur["name"], f"پنهان شد: رول {roll} در برابر {avg_pp}")
        return f"🙈 {cur['name']} با موفقیت پنهان شد! (رول {roll}) حمله بعدی با مزیت خواهد بود."
    else:
        session.add_log(cur["name"], f"پنهان نشد: رول {roll} در برابر {avg_pp}")
        return f"👀 نتوانستی پنهان شوی! (رول {roll} کمتر از {avg_pp}) دشمنان هنوز تو را می‌بینند."


def shove(session: Session, uid: int, target_name: str = "") -> str:
    """اکشن Shove: چک STR (Athletics) روبروی هدف؛ می‌توانی هدف را به زمین بیندازی (prone)."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    ch = get_participant_ch(session, cur)
    if not ch:
        return "کاراکترت پیدا نشد."
    if cur.get("downed") or cur.get("dead"):
        return "نمی‌توانی کسی را هل بدهی."
    target = _find_target(session.combat, target_name) if target_name else None
    if not target:
        names = ", ".join(p["name"] for p in session.combat["participants"]
                         if p["kind"] == "monster" and p["alive"])
        return f"هدف پیدا نشد. دشمنان: {names}"
    cur["acted"] = True
    mod = ch.stat_mod("STR") + (proficiency_bonus(ch.level) if "athletics" in ch.proficiencies else 0)
    my_roll = roll_d20() + mod
    target_mod = _default_atk_bonus(_monster_key(target), MONSTERS.get(_monster_key(target), {}))
    target_roll = roll_d20() + target_mod
    if my_roll > target_roll:
        target.setdefault("conditions", []).append("prone")
        session.add_log(cur["name"], f"{target['name']} را هل داد و به زمین انداخت")
        return f"💪 {cur['name']} با قدرت {target['name']} را هل داد و روی زمین انداخت! (رول {my_roll} در مقابل {target_roll}) هدف الان وضعیت prone دارد."
    else:
        return f"🦵 هل دادن {cur['name']} موفق نبود! (رول {my_roll} در مقابل {target_roll}) {target['name']} مقاومت کرد."


def second_wind(session: Session, uid: int) -> str:
    """Second Wind جنگجو: 1d10 + سطح fighter HP."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    ch = get_participant_ch(session, cur)
    if not ch:
        return "کاراکترت پیدا نشد."
    if ch.cls != "fighter":
        return "این قابلیت فقط برای جنگجو است."
    if ch.resources.get("second_wind", {}).get("used", 0) >= ch.resources.get("second_wind", {}).get("max", 1):
        return "نفس دوم را در این استراحت قبلاً استفاده کردی!"
    cur["acted"] = True
    ch.resources["second_wind"]["used"] += 1
    heal = random.randint(1, 10) + ch.level
    real_heal = ch.heal(heal)
    cur["hp"] = ch.hp
    session.add_log(ch.name, f"نفس دوم گرفت، +{real_heal} HP")
    return f"💨 **نفس دوم!** {ch.name} نفس عمیق کشید و {real_heal} HP بازیافت کرد."


def action_surge(session: Session, uid: int) -> str:
    """Action Surge جنگجو: یک اکشن اضافه در همین نوبت."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    ch = get_participant_ch(session, cur)
    if not ch:
        return "کاراکترت پیدا نشد."
    if ch.cls != "fighter":
        return "این قابلیت فقط برای جنگجو است."
    if ch.resources.get("action_surge", {}).get("used", 0) >= ch.resources.get("action_surge", {}).get("max", 1):
        return "اکشن اضافه را در این استراحت قبلاً استفاده کردی!"
    ch.resources["action_surge"]["used"] += 1
    cur["acted"] = False  # می‌تواند دوباره اکشن اصلی بگیرد
    session.add_log(ch.name, "از Action Surge استفاده کرد")
    return f"⚡ **اکشن اضافه!** {ch.name} موج انرژی دریافت کرد و حالا می‌تواند یک اکشن دیگر بزند!"


def rage(session: Session, uid: int) -> str:
    """خشم بربر (Bonus Action)."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    ch = get_participant_ch(session, cur)
    if not ch:
        return "کاراکترت پیدا نشد."
    if ch.cls != "barbarian":
        return "این قابلیت فقط برای بربر است."
    if ch.rage_active:
        return "همین الان در خشم هستی!"
    if ch.resources.get("rage", {}).get("used", 0) >= ch.resources.get("rage", {}).get("max", 2):
        return "تعداد دفعات خشم در این استراحت طولانی تمام شده!"
    ch.resources["rage"]["used"] += 1
    ch.rage_active = True
    ch.rage_turns = 0
    cur["bonus_acted"] = True
    ch.bonus_action_available = False
    # خشم: +2 آسیب در این سطح، مقاومت فیزیکی
    rage_dmg_bonus = 2 if ch.level < 9 else 3 if ch.level < 16 else 4
    ch.rage_dmg_bonus = rage_dmg_bonus
    session.add_log(ch.name, f"وارد حالت خشم شد (+{rage_dmg_bonus} آسیب، مقاومت فیزیکی)")
    return f"🪓 **خشم!** {ch.name} وارد خشم وحشیانه شد!\n" \
           f"• +{rage_dmg_bonus} آسیب با سلاح‌های STR\n" \
           f"• مقاومت در برابر آسیب کوبنده/سوراخ/برنده (نصف آسیب)\n" \
           f"• حملات با مزیت STR"


def bardic_inspiration(session: Session, uid: int, target_name: str = "") -> str:
    """الهام بَرد (Bonus Action)."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    ch = get_participant_ch(session, cur)
    if not ch:
        return "کاراکترت پیدا نشد."
    if ch.cls != "bard":
        return "این قابلیت فقط برای بَرد است."
    if ch.resources.get("bardic_inspiration", {}).get("used", 0) >= ch.resources.get("bardic_inspiration", {}).get("max", 3):
        return "تعداد دی‌های الهام در این استراحت طولانی تمام شده!"
    target = None
    if target_name:
        for p in session.combat["participants"]:
            if p["kind"] == "player" and p["uid"] != str(uid) and target_name.lower() in p["name"].lower():
                target = p
                break
    if not target:
        for p in session.combat["participants"]:
            if p["kind"] == "player" and p.get("hp", 0) > 0 and not p.get("downed"):
                target = p
                break
    if not target:
        return "هم‌گروهی برای الهام پیدا نشد."
    ch.resources["bardic_inspiration"]["used"] += 1
    cur["bonus_acted"] = True
    ch.bonus_action_available = False
    die = ch.resources["bardic_inspiration"]["dice"]
    target["inspiration_die"] = die
    tch = get_participant_ch(session, target)
    if tch:
        tch.inspiration = True
    session.add_log(ch.name, f"به {target['name']} الهام بَرد داد ({die})")
    return f"🎻 **الهام بَرد!** {ch.name} آهنگی الهام‌بخش برای {target['name']} نواخت! در یکی از رول‌های بعدی {die} اضافه می‌شود."


def dodge(session: Session, uid: int) -> str:
    """اقدام دفاعی: حمله‌ها علیه بازیکن تا نوبت بعدی با ضعف انجام می‌شوند."""
    if not is_player_turn(session, uid):
        return "هنوز نوبت تو نیست."
    cur = session.combat["participants"][session.combat["turn"]]
    if cur.get("downed") or cur.get("dead") or cur.get("hp", 1) <= 0:
        return "در وضعیت مرگ نمی‌توانی دفاع کنی — `/deathsave` بزن."
    if cur.get("acted"):
        return "قبلاً اکشن اصلی را گرفتی! (Dodge اکشن اصلی است)"
    if "dodge" not in cur.setdefault("conditions", []):
        cur["conditions"].append("dodge")
    cur["acted"] = True
    ch = get_participant_ch(session, cur)
    session.add_log(cur["name"], "حالت دفاعی گرفت (Dodge)")
    return f"🛡️ {cur['name']} دفاع کرد؛ حمله‌ها علیه او با ضعف خواهند بود و DEX saves با مزیت است."


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

    spell_key = spell_key.lower().replace(" ", "")
    spell = SPELLS.get(spell_key)
    if not spell:
        from .rules import SPELLS as S
        return f"طلسم پیدا نشد. طلسم‌ها: {', '.join('`' + k + '`' for k in S if k in S)}"

    # بررسی بونس‌اکشن بودن طلسم
    is_bonus = spell.get("action") == "bonus"
    if is_bonus:
        if cur.get("bonus_acted"):
            return "بونس‌اکشن این نوبت را قبلاً استفاده کردی!"
    else:
        if cur.get("acted"):
            return "اکشن اصلی این نوبت قبلاً گرفته شده!"

    # بررسی دسترسی کلاس (اسپشیال کیس‌ها)
    castable_classes = ("wizard", "sorcerer", "bard", "warlock", "cleric", "druid", "paladin", "ranger", "monk")
    is_dragonbreath = spell_key == "dragonbreath"
    if is_dragonbreath:
        if ch.race != "dragonborn":
            return "این قابلیت فقط برای اژدهازاده است!"
        if ch.resources.get("breath", {}).get("used", 0) >= 1:
            return "نفس اژدها را در این استراحت استفاده کردی!"
    else:
        if ch.cls not in castable_classes and spell_key not in ("curewounds", "healingword"):
            return f"کلاس {ch.cls} اهل جادو نیست! 🥊"
    # مصرف اسلات
    cantrips = {"firebolt", "eldritchblast", "sacredflame", "rayoffrost", "poisonspray", "minorillusion", "prestidigitation"}
    if spell_key not in cantrips and not is_dragonbreath:
        slot_level = spell.get("level", 1)
        if not ch.spend_slot(slot_level):
            return f"🪄 جایگاه طلسم سطح {slot_level} نداری؛ استراحت کن."
    # اگر بونس اکشن بود مارک کن
    if is_bonus:
        cur["bonus_acted"] = True
        ch.bonus_action_available = False
    else:
        cur["acted"] = True
    parts = []
    spell_atk_bonus = ch.spell_mod() + proficiency_bonus(ch.level)
    spell_dc = 8 + spell_atk_bonus
    # ----- طلسم‌های التیام -----
    if "heal" in spell["kind"]:
        target = None
        if target_name:
            for p in combat["participants"]:
                if p["kind"] == "player" and target_name.lower() in p["name"].lower():
                    target = p
                    break
        if not target:
            target = cur
        if "1d4" in spell.get("heal", "1d8"):
            healed = sum(roll_dice(1, 4)) + ch.spell_mod()
        else:
            healed = sum(roll_dice(1, 8)) + ch.spell_mod()
        if spell.get("upcast", False) and ch.level >= 5:
            healed += sum(roll_dice(1, 8))
        if target["kind"] == "player":
            real_char = session.get_char(int(target["uid"]))
            if real_char:
                healed = real_char.heal(healed)
                target["hp"] = real_char.hp
                if real_char.hp > 0:
                    target["downed"] = False
                    target["alive"] = True
                    real_char.death_saves = {"success": 0, "fail": 0}
        parts.append(f"{spell['emoji']} {ch.name} طلسم «{spell['fa']}» را روی {target['name']} می‌اندازد... +{healed} HP")
        result = "\n".join(parts)
        session.add_log(ch.name, result.replace("\n", " "))
        return result
    # ----- سپر جادویی (Shield - Reaction) -----
    if spell_key == "shield":
        ch.ac += 5
        cur["ac"] += 5
        cur["reaction_available"] = False
        ch.reaction_available = False
        parts.append(f"🛡️ {ch.name} طلسم سپر جادویی را به عنوان ری‌اکشن فعال کرد! AC تا نوبت بعد ۵+ می‌شود.")
        result = "\n".join(parts)
        return result
    # ----- نفس اژدها (Dragonborn Breath) -----
    if is_dragonbreath:
        ch.resources["breath"]["used"] = 1
        dmg = sum(roll_dice(2, 6))
        parts.append(f"🐲 {ch.name} نفس آتشین اژدهای خود را بیرون می‌دهد! همه در مخروط ۴.۵ متر...")
        for p in combat["participants"]:
            if p["kind"] == "monster" and p.get("alive") and p.get("distance", 0) <= 1:
                save = roll_d20() + 2  # DEX save
                if save >= spell_dc:
                    actual = dmg // 2
                    parts.append(f"🛡️ {p['name']} با موفقیت جاخالی داد و {actual} آسیب خورد!")
                else:
                    actual = dmg
                    parts.append(f"🔥 {p['name']} کامل سوخت: {actual} آسیب آتش!")
                p["hp"] = max(0, p["hp"] - actual)
                if p["hp"] <= 0:
                    p["alive"] = False
                    combat["xp_pool"] += p["xp"]
                    parts.append(f"☠️ {p['name']} خاکستر شد!")
        result = "\n".join(parts)
        session.add_log(ch.name, result.replace("\n", " "))
        return result
    # ----- طلسم‌های حمله تک‌هدف -----
    target = _find_target(combat, target_name)
    if not target:
        names = ", ".join(p["name"] for p in combat["participants"]
                         if p["kind"] == "monster" and p["alive"])
        return f"هدف پیدا نشد. دشمنان: {names}"
    is_ranged_spell = "ranged" in spell["kind"] or spell_key in ("firebolt", "eldritchblast", "rayoffrost", "guidingbolt", "hex", "huntersmark")
    if "attack" in spell["kind"]:
        hit_msg, downed = _resolve_one_attack(session, cur, target, spell_atk_bonus,
                                              dmg_expr=spell["dmg"], dmg_type=spell.get("damage_type", "force"),
                                              is_ranged=is_ranged_spell)
        parts.append(f"{spell['emoji']} {ch.name} «{spell['fa']}» می‌اندازد!")
        parts.append(hit_msg)
    elif "auto" in spell["kind"]:
        dmg = _roll_damage(spell["dmg"])
        target["hp"] = max(0, target["hp"] - dmg)
        parts.append(f"{spell['emoji']} {ch.name} «{spell['fa']}» می‌اندازد: خودکار اصابت! {dmg} آسیب به {target['name']}!")
    elif "save" in spell["kind"]:
        # طلسم‌هایی که save می‌خواهند
        dmg = _roll_damage(spell["dmg"])
        # پیدا کردن استت ذخیره
        save_stat = "DEX"
        if "con" in spell["kind"]:
            save_stat = "CON"
        if "wis" in spell["kind"]:
            save_stat = "CHA"
        save_bonus = 2  # برای هیولاها
        save_roll = roll_d20() + save_bonus
        if save_roll >= spell_dc:
            actual_dmg = dmg // 2
            parts.append(f"🛡️ {target['name']} در برابر طلسم مقاومت کرد (رول {save_roll} در برابر DC {spell_dc}): {actual_dmg} آسیب نصف!")
        else:
            actual_dmg = dmg
            parts.append(f"{spell['emoji']} {target['name']} در ذخیره شکست خورد! {actual_dmg} آسیب کامل!")
            if "holdperson" in spell_key or "paralyze" in spell.get("effect", ""):
                target.setdefault("conditions", []).append("paralyzed")
                parts.append(f"🫵 {target['name']} فلج شد!")
            if "sleep" in spell_key:
                target.setdefault("conditions", []).append("unconscious")
                parts.append(f"💤 {target['name']} به خواب عمیق فرو رفت!")
        target["hp"] = max(0, target["hp"] - actual_dmg)
    # ----- افکت‌های mark (نشان شکارچی/نفرین) -----
    if spell_key in ("huntersmark", "hex"):
        cur["marked_target"] = target["name"]
        ch.conditions.append("concentrating")
        parts.append(f"🎯 {target['name']} علامت خورد! تمام حملات بعدی به او 1d6 آسیب اضافی خواهند زد (تا زمانی که تمرکز داری).")
    # ----- Mage Armor -----
    if spell_key == "magearmor":
        new_ac = 13 + ability_mod(ch.abilities["DEX"])
        if ch.armor == "none":
            ch.ac = new_ac
            cur["ac"] = ch.ac
        parts.append(f"🧙 زره جادویی فعال شد! AC الان {ch.ac} است.")
    # ----- Shield Spell (Reaction) -----
    if spell_key == "shield":
        # این به عنوان ری‌اکشن در مقابل حمله فراخوانی می‌شود، +5 AC می‌دهد تا شروع نوبت بعد
        ch.ac += 5
        cur["ac"] += 5
        cur.setdefault("temp_ac_boost", 0)
        cur["temp_ac_boost"] += 5
        cur["reaction_available"] = False
        ch.reaction_available = False
        parts.append(f"🛡️ سپر جادویی فعال شد! AC تا شروع نوبت بعد ۵+ می‌شود (الان {ch.ac}).")
    # ----- Misty Step -----
    if spell_key == "mistystep":
        cur["distance"] = 1 if cur.get("distance", 0) == 0 else 0
        parts.append(f"💨 در مه ناپدید شدی و در موقعیت جدید ظاهر شدی!")
    # بررسی کشته شدن هدف
    if target.get("hp", 0) <= 0 and target.get("alive", True):
        target["alive"] = False
        combat["xp_pool"] += target["xp"]
        parts.append(f"\n☠️ **{target['name']} نابود شد!** (+{target['xp']} XP)")
    result = "\n".join(parts)
    session.add_log(ch.name, result.replace("\n", " ")[:500])
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
