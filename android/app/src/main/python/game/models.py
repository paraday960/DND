# -*- coding: utf-8 -*-
"""مدل‌های اصلی: کاراکتر و جلسه بازی."""
import random
import string

from .rules import (
    ABILITIES, RACES, CLASSES, WEAPONS, SPELLS,
    STANDARD_ARRAY, ability_mod, level_from_xp, proficiency_bonus,
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
        self.abilities = stats or make_stats()
        # اعمال پاداش نژادی
        for k, v in RACES[self.race]["bonus"].items():
            self.abilities[k] += v

        hit_die = CLASSES[cls]["hit_die"]
        con_mod = ability_mod(self.abilities["CON"])
        self.hit_die = hit_die
        self.max_hp = (hp if hp else hit_die) + con_mod * level
        self.max_hp = max(self.max_hp, level)
        self.hp = self.max_hp
        # زره ساده: کلاس‌های زره‌پوش +۲ AC
        armor_bonus = 2 if CLASSES[cls]["armor"] else 0
        self.ac = 10 + ability_mod(self.abilities["DEX"]) + armor_bonus

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
        return {"old": old_level, "new": self.level, "hp_gain": max(gain, 1),
                "features": self.features()}

    def features(self) -> list:
        f = list(CLASSES[self.cls]["features"])
        if self.level >= 5:
            f.append("حمله اضافه (Extra Attack)")
        if self.level >= 3 and self.cls in ("wizard", "sorcerer", "bard", "warlock", "druid", "cleric"):
            f.append("طلسم سطح ۲")
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
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        ch = cls(d["name"], d["race"], d["cls"], d["weapon"], stats=dict(d["abilities"]),
                 level=d["level"], xp=d["xp"], gold=d.get("gold", 10))
        ch.hp = d.get("hp", ch.max_hp)
        ch.max_hp = d.get("max_hp", ch.max_hp)
        ch.ac = d.get("ac", ch.ac)
        ch.hit_die = d.get("hit_die", ch.hit_die)
        return ch


class Session:
    """یک اتاق بازی — حداکثر ۸ بازیکن، با DM و سناریو و لاگ رویدادها."""

    def __init__(self, chat_id: int, name: str, dm_id: int, dm_name: str):
        self.chat_id = chat_id
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
        self.add_player(dm_id, dm_name)

    # ---------- بازیکن‌ها ----------
    def add_player(self, uid: int, uname: str) -> str:
        """بازیکن اضافه می‌کند؛ اگر ظرفیت پر باشد خطا برمی‌گرداند."""
        if str(uid) in self.players:
            return "already"
        if len(self.players) >= 8:
            return "full"
        self.players[str(uid)] = {"user": uname, "char": None}
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
    def scenario_text(self) -> str:
        if not self.scenario:
            return "(هنوز سناریویی ساخته نشده — DM با /scenario بسازد)"
        s = self.scenario
        out = [f"🐉 **{s.get('title', 'ماجرای بی‌نام')}**",
               f"\n🎯 **هدف:** {s.get('goal', '—')}",
               f"💡 **شروع:** {s.get('hook', '—')}"]
        if s.get("locations"):
            out.append("\n🗺️ **مکان‌ها:** " + ", ".join(s["locations"]))
        if s.get("npcs"):
            out.append("👥 **NPCها:** " + ", ".join(s["npcs"]))
        if s.get("encounters"):
            enc = []
            for e in s["encounters"]:
                enc.append(f"{e.get('count', 1)}× {e.get('name', '؟')}")
            out.append("⚔️ **رویارویی‌ها:** " + ", ".join(enc))
        if s.get("treasure"):
            out.append(f"💎 **گنج:** {s['treasure']}")
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
        s.players = {}
        for uid, p in (d.get("players") or {}).items():
            char = Character.from_dict(p["char"]) if p.get("char") else None
            s.players[uid] = {"user": p.get("user", "؟"), "char": char}
        return s
