# -*- coding: utf-8 -*-
"""مدل‌های اصلی: کاراکتر و جلسه بازی."""
import random
import string

from .rules import (
    ABILITIES, RACES, CLASSES, WEAPONS, SPELLS, WEAPON_RANGES,
    STANDARD_ARRAY, ability_mod, level_from_xp, proficiency_bonus,
    DEFAULT_PROFICIENCIES, CONDITIONS,
)


def gen_code(length: int = 5) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def make_stats() -> dict:
    """آرایه استاندارد به‌صورت تصادفی بین توانایی‌ها توزیع می‌شود."""
    values = list(STANDARD_ARRAY)
    random.shuffle(values)
    return dict(zip(ABILITIES, values))


class Character:
    def __init__(self, name: str, race: str, cls: str, weapon: str,
                 stats: dict = None, level: int = 1, xp: int = 0,
                 gold: int = 10, hp: int = None):
        self.name = name.strip() or "بی‌نام"
        self.race = race
        self.cls = cls
        self.weapon = weapon
        self.level = level
        self.xp = xp
        self.gold = gold
        self.proficiencies = list(DEFAULT_PROFICIENCIES.get(cls, []))
        self.inventory = {"potion": 2, "torch": 3, "rope": 1}
        self.conditions = []
        self.death_saves = {"success": 0, "fail": 0}
        self.inspiration = False
        self.spell_slots = self._initial_spell_slots()
        self.spell_slots_used = {}
        # منابع ویژگی‌های کلاس (که در استراحت ریست می‌شوند)
        self.resources = self._initial_class_resources()
        # Hit Dice برای استراحت کوتاه
        self.hit_dice_used = 0
        # بونس اکشن و ری‌اکشن در هر نوبت (در ابتدای نوبت ریست می‌شوند)
        self.bonus_action_available = True
        self.reaction_available = True
        self.reaction_target = None  # برای آماده باش/فرصت
        # وضعیت حرکت
        self.distance = 0  # فاصله از دشمنان: 0 نزدیک، 1 متوسط، 2 دور
        self.disengage_active = False
        self.helped_target = None
        self.hidden = False
        # حالت خشم بربر
        self.rage_active = False
        self.rage_turns = 0
        # هنگام بازیابی از SQLite، امتیازها قبلاً شامل پاداش نژادی هستند؛
        # اعمال دوبارهٔ bonus باعث می‌شد هر بار load شدن کاراکتر قوی‌تر شود.
        self.abilities = dict(stats) if stats is not None else make_stats()
        if stats is None:
            for k, v in RACES[self.race]["bonus"].items():
                self.abilities[k] += v

        hit_die = CLASSES[cls]["hit_die"]
        con_mod = ability_mod(self.abilities["CON"])
        self.hit_die = hit_die
        # برای کاراکتر جدید با سطح بالاتر، میانگین هر مرحله (half+1) لحاظ می‌شود
        if hp is not None:
            self.max_hp = hp
        elif level == 1:
            self.max_hp = hit_die + con_mod
        else:
            avg = hit_die // 2 + 1
            self.max_hp = hit_die + (level - 1) * avg + con_mod * level
        self.max_hp = max(self.max_hp, level)
        self.hp = self.max_hp
        # زره پیش‌فرض (بعداً با equipment.equip_armor به‌روز می‌شود)
        self.armor = "medium" if CLASSES[cls].get("armor") else "none"
        # محاسبه اولیه AC
        armor_bonus = 2 if CLASSES[cls]["armor"] else 0
        dex_mod = ability_mod(self.abilities["DEX"])
        base_ac = 10 + dex_mod + armor_bonus
        # Unarmored Defense: بربر 10+DEX+CON، مانک 10+DEX+WIS
        if cls == "barbarian":
            base_ac = 10 + dex_mod + con_mod
        elif cls == "monk":
            wis_mod = ability_mod(self.abilities["WIS"])
            base_ac = 10 + dex_mod + wis_mod
        self.ac = base_ac
        # بونوس سپر: اگر weapon انتخابی shield است +2 AC
        self.shield_equipped = (weapon == "shield")
        if self.shield_equipped:
            self.ac += 2

    def _initial_spell_slots(self) -> dict:
        if self.cls not in ("wizard", "cleric", "druid", "bard", "sorcerer", "warlock", "paladin", "ranger"):
            return {}
        # مدل ساده‌شدهٔ slotها؛ استراحت طولانی آن‌ها را بازنشانی می‌کند.
        slots = {}
        slots[1] = max(1, min(4, 2 + self.level // 3))
        if self.level >= 3:
            slots[2] = max(0, min(3, (self.level - 1) // 2))
        if self.level >= 5:
            slots[3] = max(1, min(2, (self.level - 3) // 2))
        if self.level >= 7:
            slots[4] = 1 if self.level >= 7 else 0
        if self.level >= 9:
            slots[5] = 1
        return {k: v for k, v in slots.items() if v > 0}

    def _initial_class_resources(self) -> dict:
        res = {}
        # Fighter
        if self.cls == "fighter":
            res["second_wind"] = {"max": 1, "used": 0, "per": "short"}
            res["action_surge"] = {"max": 1 if self.level < 17 else 2, "used": 0, "per": "short"}
        # Barbarian
        if self.cls == "barbarian":
            res["rage"] = {"max": 2 + self.level // 4, "used": 0, "per": "long"}
        # Bard
        if self.cls == "bard":
            res["bardic_inspiration"] = {"max": max(3, self.level // 2 + 2), "used": 0, "dice": "d6" if self.level < 5 else "d8" if self.level < 10 else "d10" if self.level < 15 else "d12", "per": "long"}
        # Monk
        if self.cls == "monk":
            res["ki"] = {"max": max(2, self.level), "used": 0, "per": "short"}
        # Warlock
        if self.cls == "warlock":
            pass  # بعدا اضافه میشه invocations
        # Dragonborn breath weapon
        if self.race == "dragonborn":
            res["breath"] = {"max": 1, "used": 0, "per": "short"}
        # Halfling luck
        if self.race == "halfling":
            res["luck_used"] = False
        # Half-orc relentless endurance
        if self.race == "half_orc":
            res["relentless_used"] = False
        return res

    def available_slot(self, level: int = 1) -> bool:
        return self.spell_slots.get(level, 0) > self.spell_slots_used.get(level, 0)

    def spend_slot(self, level: int = 1) -> bool:
        if not self.available_slot(level):
            return False
        self.spell_slots_used[level] = self.spell_slots_used.get(level, 0) + 1
        return True

    def reset_spell_slots(self):
        self.spell_slots_used = {}

    def reset_short_rest(self):
        """استراحت کوتاه (۱ ساعت): hit dice می‌خوری، منابع per-short ریست می‌شوند."""
        # ریست منابعی که per short هستند
        for k, v in self.resources.items():
            if v.get("per") == "short":
                v["used"] = 0
        # Warlock اسلات‌ها با استراحت کوتاه برمی‌گردند
        if self.cls == "warlock":
            self.spell_slots_used = {}
        # Half-orc relentless endurance و dragonborn breath در short rest برمی‌گردند
        if self.race == "half_orc":
            self.resources["relentless_used"] = False
        if self.race == "dragonborn" and "breath" in self.resources:
            self.resources["breath"]["used"] = 0
        # خستگی کم نمیشه
        self.conditions = [c for c in self.conditions if c not in ("frightened", "charmed")]
        # هاله بارد/الهام و غیره هم ریست میشن

    def reset_long_rest(self):
        """استراحت طولانی (۸ ساعت): همه چیز ریست میشه، HP کامل، اسلات‌ها کامل، منابع long."""
        self.hp = self.max_hp
        self.hit_dice_used = 0
        self.death_saves = {"success": 0, "fail": 0}
        self.conditions = []
        self.spell_slots_used = {}
        # همه منابع ریست
        for k, v in self.resources.items():
            v["used"] = 0
        if self.race == "half_orc":
            self.resources["relentless_used"] = False
        if self.race == "halfling":
            self.resources["luck_used"] = False
        # خشم بربر خاموش میشه
        self.rage_active = False
        self.rage_turns = 0
        self.hidden = False

    def spend_hit_die(self) -> int:
        """یک hit die در استراحت کوتاه خرج می‌کند و مقدار heal را برمی‌گرداند."""
        if self.hit_dice_used >= self.level:
            return 0
        self.hit_dice_used += 1
        import random
        con_mod = self.stat_mod("CON")
        roll = random.randint(1, self.hit_die) + con_mod
        return max(1, roll)

    def reset_turn_resources(self):
        """در شروع نوبت بازیکن: بونس اکشن و ری‌اکشن دوباره در دسترس می‌شوند."""
        self.bonus_action_available = True
        self.reaction_available = True
        self.disengage_active = False
        self.helped_target = None
        # اگر در خشم هستی شمارنده را زیاد کن و اگر آسیب ندیدی خاموش کن (بعدا در combat هندل می‌کنیم)

    def advantage_on(self, roll_type: str, target=None) -> tuple:
        """بر اساس شرایط، برمی‌گرداند که آیا این رول مزیت (advantage) یا ضعف (disadvantage) دارد.
        خروجی: (has_adv, has_dis, reasons)
        """
        adv = False
        dis = False
        reasons = []
        # وضعیت‌های خودم
        if any(c in self.conditions for c in ("blinded", "frightened", "poisoned", "restrained", "stunned")):
            dis = True
            reasons.append("در وضعیت نامناسب")
        if "prone" in self.conditions and roll_type == "attack_ranged":
            dis = True
            reasons.append("روی زمین افتاده و از دور حمله می‌کنی")
        if "invisible" in self.conditions:
            adv = True
            reasons.append("نامرئی")
        # اگر هدف کمک دریافت کرده
        if self.helped_target == target:
            adv = True
            reasons.append("هم‌گروهی به تو کمک کرد")
        if self.hidden and roll_type == "attack":
            adv = True
            reasons.append("مخفی بودی، حمله غافلگیرانه")
        # وضعیت هدف
        if target and isinstance(target, dict):
            t_conds = target.get("conditions", [])
            if any(c in t_conds for c in ("blinded", "restrained", "stunned", "unconscious", "prone")):
                if roll_type == "attack_melee" or any(c in t_conds for c in ("unconscious", "paralyzed")):
                    adv = True
                    reasons.append("هدف در وضعیت آسیب‌پذیر است")
            if "invisible" in t_conds and roll_type in ("attack", "attack_melee", "attack_ranged"):
                dis = True
                reasons.append("هدف نامرئی است")
        # خشم
        if self.rage_active and roll_type == "strength_attack":
            adv = True
            reasons.append("در حالت خشم")
        return adv, dis, reasons

    # ---------- امکانات ----------
    def stat_mod(self, stat: str) -> int:
        return ability_mod(self.abilities[stat])

    def weapon_stat(self) -> str:
        return WEAPONS[self.weapon]["stat"]

    def attack_bonus(self) -> int:
        return self.stat_mod(self.weapon_stat()) + proficiency_bonus(self.level)

    def spell_mod(self) -> int:
        primary = CLASSES[self.cls]["primary"][0]
        return self.stat_mod(primary)

    def xp_for_next(self) -> int:
        return 0 if self.level >= 20 else self.xp_needed_for(self.level + 1)

    def xp_needed_for(self, target_level: int) -> int:
        from .rules import XP_TABLE
        return XP_TABLE[target_level - 1]

    def can_level_up(self) -> bool:
        return self.level < 20 and self.xp >= self.xp_needed_for(self.level + 1)

    def level_up(self) -> dict:
        old_level = self.level
        self.level += 1
        con_mod = ability_mod(self.abilities["CON"])
        gain = self.hit_die + con_mod
        self.max_hp += max(gain, 1)
        self.hp = self.max_hp
        # ارتقای طلسم‌ها
        if self.cls in ("wizard", "cleric", "druid", "bard", "sorcerer", "warlock", "paladin", "ranger"):
            self.spell_slots = self._initial_spell_slots()
            self.spell_slots_used = {}
        # یادگیری فیچر جدید بر اساس سطح
        gained = []
        new_features = self.features()
        if hasattr(self, "_known_features"):
            for f in new_features:
                if f not in self._known_features:
                    gained.append(f)
        self._known_features = list(new_features)
        return {"old": old_level, "new": self.level, "hp_gain": max(gain, 1),
                "features": new_features, "gained_features": gained}

    def features(self) -> list:
        f = list(CLASSES[self.cls]["features"])
        if self.level >= 2:
            f.append("واکنش (Reaction)")
        if self.level >= 3:
            f.append("مسیر تخصصی (Subclass)")
        if self.level >= 5:
            f.append("حمله اضافه (Extra Attack)")
        if self.level >= 3 and self.cls in ("wizard", "sorcerer", "bard", "warlock", "druid", "cleric"):
            f.append("طلسم سطح ۲")
        if self.level >= 6 and self.cls in ("wizard", "sorcerer", "bard", "warlock", "druid", "cleric"):
            f.append("طلسم سطح ۳")
        if self.level >= 9 and self.cls in ("wizard", "sorcerer", "cleric", "druid"):
            f.append("طلسم سطح ۵")
        if self.level >= 10:
            f.append("بهبود ability score (+2)")
        if self.level >= 15:
            f.append("ویژگی پیشرفته کلاس")
        if self.level >= 20:
            f.append("قابلیت نهایی (Capstone)")
        return f

    def heal(self, amount: int) -> int:
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

    def take_damage(self, amount: int) -> int:
        self.hp = max(0, self.hp - amount)
        return self.hp

    # ---------- نمایش ----------
    def sheet_text(self) -> str:
        r = RACES[self.race]
        c = CLASSES[self.cls]
        w = WEAPONS[self.weapon]
        lines = [
            f"📜 **{self.name}**",
            f"{r['emoji']} نژاد: {r['fa']}   |   {c['emoji']} کلاس: {c['fa']}   |   🎚️ سطح: {self.level}  ({self.xp} XP)",
            f"❤️ HP: {self.hp}/{self.max_hp}   |   🛡️ AC: {self.ac}   |   🏅 پاداش مهارت: +{proficiency_bonus(self.level)}",
            "—",
        ]
        for a in ABILITIES:
            lines.append(f"{a} {self.abilities[a]} ({ability_mod(self.abilities[a]):+d})")
        lines += [
            "—",
            f"{w['emoji']} سلاح: {w['fa']} ({w['dmg']})  |  🗡️ بونوس حمله: {self.attack_bonus():+d}",
            f"🪙 سکه: {self.gold}",
            f"✨ ویژگی‌ها: {', '.join(self.features())}",
        ]
        return "\n".join(lines)

    # ---------- سریال‌سازی ----------
    def to_dict(self) -> dict:
        return {
            "name": self.name, "race": self.race, "cls": self.cls,
            "weapon": self.weapon, "level": self.level, "xp": self.xp,
            "gold": self.gold, "abilities": self.abilities,
            "hp": self.hp, "max_hp": self.max_hp, "ac": self.ac,
            "hit_die": self.hit_die,
            "proficiencies": self.proficiencies, "inventory": self.inventory,
            "conditions": self.conditions, "death_saves": self.death_saves,
            "inspiration": self.inspiration,
            "spell_slots": self.spell_slots, "spell_slots_used": self.spell_slots_used,
            "resources": self.resources,
            "hit_dice_used": self.hit_dice_used,
            "rage_active": self.rage_active,
            "rage_turns": self.rage_turns,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        ch = cls(d["name"], d["race"], d["cls"], d["weapon"], stats=dict(d["abilities"]),
                 level=d["level"], xp=d["xp"], gold=d.get("gold", 10))
        ch.hp = d.get("hp", ch.max_hp)
        ch.max_hp = d.get("max_hp", ch.max_hp)
        ch.ac = d.get("ac", ch.ac)
        ch.hit_die = d.get("hit_die", ch.hit_die)
        ch.proficiencies = d.get("proficiencies", ch.proficiencies)
        ch.inventory = d.get("inventory", ch.inventory)
        ch.conditions = d.get("conditions", [])
        ch.death_saves = d.get("death_saves", {"success": 0, "fail": 0})
        ch.inspiration = d.get("inspiration", False)
        ch.spell_slots = {int(k): v for k, v in d.get("spell_slots", ch.spell_slots).items()}
        ch.spell_slots_used = {int(k): v for k, v in d.get("spell_slots_used", {}).items()}
        ch.resources = d.get("resources", ch.resources)
        ch.hit_dice_used = d.get("hit_dice_used", 0)
        ch.rage_active = d.get("rage_active", False)
        ch.rage_turns = d.get("rage_turns", 0)
        return ch


class Session:
    """یک اتاق بازی — حداکثر ۸ بازیکن، با DM و سناریو و لاگ رویدادها."""

    def __init__(self, chat_id: int, name: str, dm_id: int, dm_name: str):
        self.chat_id = chat_id
        self.host_chat_id = chat_id  # چتی که نبرد در آن اجرا می‌شود
        self.name = name
        self.code = gen_code()
        self.dm_id = dm_id
        self.dm_name = dm_name
        self.state = "lobby"          # lobby | playing | combat
        self.players = {}             # uid(str) -> {"user": name, "char": Character|None}
        self.scenario = None          # dict از سناریوی ساخته‌شده
        self.log = []                 # رویدادهای بازی برای حافظه AI
        self.combat = None            # dict وضعیت نبرد
        self.combat_xp = 0
        # وضعیت پویای دنیا (توسط AI یا دستورات تغییر می‌کند)
        # مثلاً {"light": "torch", "location": "تالار ورودی", "flags": {...}}
        self.world = {"light": "dark", "location": "", "flags": {}}
        self.campaign = None  # dict کمپین چندفصلی
        self.npc_memory = {}  # حافظه گفتگو با NPCها
        self.add_player(dm_id, dm_name)

    # ---------- بازیکن‌ها ----------
    def add_player(self, uid: int, uname: str, chat_id: int = None) -> str:
        """بازیکن اضافه می‌کند؛ اگر ظرفیت پر باشد خطا برمی‌گرداند.
        chat_id اولین چتی است که بازیکن از آن وارد شده (برای یادآوری)."""
        if str(uid) in self.players:
            return "already"
        if len(self.players) >= 8:
            return "full"
        self.players[str(uid)] = {"user": uname, "char": None,
                                  "chat_id": chat_id or self.host_chat_id}
        return "ok"

    def get_char(self, uid: int):
        p = self.players.get(str(uid))
        return p["char"] if p else None

    def has_char(self, uid: int) -> bool:
        ch = self.get_char(uid)
        return ch is not None

    def char_count(self) -> int:
        return sum(1 for p in self.players.values() if p["char"])

    # ---------- لاگ ----------
    def alive_players(self) -> list:
        """لیست uid بازیکنان زنده و آگاه در نبرد."""
        if not self.combat:
            return []
        out = []
        for p in self.combat.get("participants", []):
            if p.get("kind") != "player":
                continue
            if p.get("dead") or p.get("downed") or p.get("hp", 0) <= 0:
                continue
            out.append(p)
        return out

    def add_log(self, who: str, what: str):
        self.log.append({"who": who, "what": what})
        if len(self.log) > 60:
            self.log = self.log[-60:]

    def log_text(self, n: int = 15) -> str:
        parts = []
        for e in self.log[-n:]:
            parts.append(f"- {e['who']}: {e['what']}")
        return "\n".join(parts) or "(هنوز اتفاقی نیفتاده)"

    # ---------- سناریو ----------
    @staticmethod
    def _loc_name(l):
        if isinstance(l, dict):
            return l.get("name", str(l))
        return str(l)

    @staticmethod
    def _npc_name(n):
        if isinstance(n, dict):
            role = f" ({n.get('role','')})" if n.get("role") else ""
            return f"{n.get('name','؟')}{role}"
        return str(n)

    @staticmethod
    def _tres_text(t):
        if isinstance(t, dict):
            qty = t.get("qty", "")
            q = f" ×{qty}" if qty else ""
            return f"{t.get('item','؟')}{q}"
        return str(t)

    def scenario_text(self) -> str:
        if not self.scenario:
            return "(هنوز سناریویی ساخته نشده — DM با /scenario بسازد)"
        s = self.scenario
        out = [f"🐉 **{s.get('title', 'ماجرای بی‌نام')}**",
               f"\n🎯 **هدف:** {s.get('goal', '—')}",
               f"💡 **شروع:** {s.get('hook', '—')}"]
        if s.get("locations"):
            locs = []
            for l in s["locations"]:
                if isinstance(l, dict):
                    hint = f" — {l.get('encounter_hint','')}" if l.get("encounter_hint") else ""
                    locs.append(f"📍 {l.get('name','؟')}{hint}")
                else:
                    locs.append(f"📍 {l}")
            out.append("\n🗺️ **مکان‌ها:**\n" + "\n".join(locs))
        if s.get("npcs"):
            out.append("👥 **شخصیت‌ها:** " + "، ".join(self._npc_name(n) for n in s["npcs"]))
        if s.get("encounters"):
            enc = []
            for e in s["encounters"]:
                mark = " 👑" if e.get("is_boss") else ""
                loc = f" ({e['location']})" if e.get("location") else ""
                enc.append(f"{e.get('count', 1)}× {e.get('name', '؟')}{mark}{loc}")
            out.append("⚔️ **رویارویی‌ها:**\n  • " + "\n  • ".join(enc))
        if s.get("traps"):
            tr = []
            for t in s["traps"]:
                if isinstance(t, dict):
                    tr.append(f"🪤 {t.get('name','تله')} در {t.get('location','؟')} — DC {t.get('detect_dc','?')}")
            if tr:
                out.append("🪤 **تله‌های احتمالی:**\n  • " + "\n  • ".join(tr))
        if s.get("branches"):
            br = []
            for b in s["branches"]:
                if isinstance(b, dict):
                    br.append(f"🔀 {b.get('text','؟')}")
            if br:
                out.append("🔀 **انتخاب‌ها:**\n  • " + "\n  • ".join(br[:4]))
        if s.get("twist"):
            out.append(f"🌀 **پیچ داستانی (برای DM):** ||{s['twist']}||")
        if s.get("treasure"):
            tlist = s["treasure"]
            if isinstance(tlist, list):
                out.append("💎 **گنج:** " + "، ".join(self._tres_text(t) for t in tlist))
            else:
                out.append(f"💎 **گنج:** {tlist}")
        out.append("\n💬 حالا با `/story` یا نوشتن توصیف اکشن، ماجرا را شروع کنید!")
        return "\n".join(out)

    # ---------- سریال‌سازی ----------
    def to_dict(self) -> dict:
        players = {}
        for uid, p in self.players.items():
            players[uid] = {"user": p["user"],
                            "char": p["char"].to_dict() if p["char"] else None}
        return {
            "chat_id": self.chat_id, "name": self.name, "code": self.code,
            "dm_id": self.dm_id, "dm_name": self.dm_name, "state": self.state,
            "players": players, "scenario": self.scenario, "log": self.log,
            "combat": self.combat, "combat_xp": self.combat_xp,
            "world": self.world, "campaign": self.campaign,
            "npc_memory": self.npc_memory,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        s = cls(d["chat_id"], d["name"], d["dm_id"], d["dm_name"])
        s.code = d.get("code", s.code)
        s.state = d.get("state", "lobby")
        s.scenario = d.get("scenario")
        s.log = d.get("log", [])
        s.combat = d.get("combat")
        s.combat_xp = d.get("combat_xp", 0)
        s.world = d.get("world") or {"light": "dark", "location": "", "flags": {}}
        s.campaign = d.get("campaign")
        s.npc_memory = d.get("npc_memory", {})
        s.players = {}
        for uid, p in (d.get("players") or {}).items():
            char = Character.from_dict(p["char"]) if p.get("char") else None
            s.players[uid] = {"user": p.get("user", "؟"), "char": char}
        return s
