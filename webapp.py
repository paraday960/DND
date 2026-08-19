# -*- coding: utf-8 -*-
"""وباپ مینی‌گیم — سرور Flask: سرو صفحه بازی + API بازی.

امنیت: هویت کاربر با امضای initData تلگرام (HMAC) بررسی می‌شود.
حالت آزمایشی (WEBAPP_DEV=1) برای تست در مرورگر/پیش‌نمایش.
"""
import hashlib
import hmac
import json
import os
import random
import urllib.parse
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory

import config
from game.combat import (advance, attack, cast, dodge, dash, disengage,
                         help_action, hide, shove, second_wind, action_surge,
                         rage, bardic_inspiration, move_action,
                         offhand_attack, divine_smite,
                         jump_action, help_up, throw_action, dip_weapon,
                         cunning_action, hellish_rebuke,
                         end_combat, is_player_turn, run_initial_monsters,
                         start_combat)
from game.adventure import (death_save, inventory_text, rest,
                             skill_check, use_item)
from game.dice import (
    DiceError, roll_advantage, roll_disadvantage, roll_expression,
)
from game.map import move_to, describe as map_describe
from game.world import try_disarm_trap
from game.models import Character, Session
from game.rules import (ABILITIES, ABILITY_FA, CLASSES, MONSTERS,
                        RACES, SPELLS, WEAPONS, proficiency_bonus)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

_rooms = {}  # cache: code -> Session


def _rand_chat_id() -> int:
    return random.randint(10**9, 2 * 10**9)


def validate_init_data(init_data: str):
    """اعتبارسنجی initData تلگرام — کلید مخفی از توکن ربات ساخته می‌شود.

    مطابق مستندات رسمی تلگرام: باید مقادیر URL-decode شده (parse_qsl) استفاده شوند.
    چک اضافی: auth_date نباید بیش از ۲۴ ساعت قدیمی باشد.
    """
    import logging, time as _t
    log = logging.getLogger("webapp")
    try:
        if not init_data or not config.BOT_TOKEN:
            return None
        # parse_qsl به‌صورت پیش‌فرض درصد-کدها را decode می‌کند (رفتار رسمی تلگرام)
        fields = dict(parse_qsl(init_data, keep_blank_values=True))
        received = fields.pop("hash", None)
        if not received:
            return None
        # چک اعتبار زمانی
        try:
            ad = int(fields.get("auth_date", "0"))
            if abs(_t.time() - ad) > 86400:
                log.warning("initData expired (auth_date=%d, now=%.0f, diff=%.0fs)",
                            ad, _t.time(), abs(_t.time() - ad))
                return None
        except Exception:
            pass
        secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            log.warning(
                "initData hash mismatch (token len=%d, fields=%s, recv=%s, calc=%s)",
                len(config.BOT_TOKEN), ",".join(sorted(fields))[:200], received[:12], calc[:12])
            return None
        user_str = fields.get("user", "{}")
        try:
            u = json.loads(user_str)
            if not u.get("id"):
                return {"id": 0, "first_name": "بازیکن"}
            return u
        except Exception:
            return {"id": 0, "first_name": "بازیکن"}
    except Exception as e:
        log.warning("validate_init_data error: %s", e)
        return None


class _MemoryStore:
    """ذخیره‌سازی در حافظه برای حالت dev/test (وقتی store=None است)."""
    def __init__(self):
        self._rooms = {}
    def save(self, s):
        self._rooms[s.code] = s
        self._rooms[s.chat_id] = s
    def load(self, chat_id):
        return self._rooms.get(chat_id)
    def delete(self, chat_id):
        s = self._rooms.pop(chat_id, None)
        if s and getattr(s, "code", None):
            self._rooms.pop(s.code, None)
    def find_by_code(self, code):
        return self._rooms.get(code.upper() if code else code)


class _OfflineNarrator:
    """راوی آفلاین برای وقتی که narrator=None یا کلید AI تنظیم نیست."""
    available = False
    def scenario(self, session, req=""):
        return {"title": "سیاه‌چال فراموش‌شده", "hook": "ورودی تاریکی در مقابل شما قرار دارد...",
                "goal": "درون سیاه‌چال برو و گنج را پیدا کن.",
                "locations": [{"name": "ورودی سیاه‌چال", "description": "در سنگی کهنه در دامنه کوه."}],
                "npcs": [], "encounters": [], "treasure": None, "traps": [], "branches": [],
                "boss": None}
    def narrate(self, session, action):
        return f"شما اقدام کردید: {action}. داستان ادامه دارد..."
    def recap(self, session):
        return "شما در ورودی سیاه‌چال هستید. هوا سرد و مرطوب است."


def build_app(store, narrator, telegram_app=None, loop=None):
    # در حالت dev/test: اگر store نال بود از حافظه استفاده کن
    if store is None and config.WEBAPP_DEV:
        store = _MemoryStore()
    if narrator is None and config.WEBAPP_DEV:
        narrator = _OfflineNarrator()
    app = Flask(__name__)

    # ---------- CORS برای مینی‌گیم (اجازه می‌دهد iframeها و webviewها بدون خطا کار کنند) ----------
    @app.after_request
    def _add_cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Init-Data"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    # ---------- وب‌هوک تلگرام (جایگزین polling — سریع و بدون تأخیر) ----------
    @app.post("/webhook/<token>")
    def tg_webhook(token):
        import asyncio
        if token != config.BOT_TOKEN.split(":")[0]:
            return "unauthorized", 401
        data = request.get_json(force=True, silent=True)
        if not data:
            return "bad request", 400
        if telegram_app is not None and loop is not None:
            from telegram import Update as TgUpdate
            update = TgUpdate.de_json(data, telegram_app.bot)
            fut = asyncio.run_coroutine_threadsafe(
                telegram_app.process_update(update), loop)
            try:
                fut.result(timeout=120)
            except Exception:
                app.logger.exception("خطا در پردازش آپدیت وب‌هوک")
        return "ok"

    # ---------- ابزارها ----------
    def api_ok(data=None):
        return jsonify({"ok": True, **({"data": data} if data is not None else {})})

    def api_err(msg, code=400):
        return jsonify({"ok": False, "error": msg}), code

    def _json_body():
        """بدنه JSON را به‌صورت امن به dict تبدیل می‌کند (جلوگیری از کرش روی رشته/عدد/آرایه)."""
        if not request.is_json:
            return {}
        try:
            data = request.get_json(silent=True)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_user():
        init = (request.headers.get("X-Init-Data")
                or request.args.get("init_data")
                or request.args.get("tgWebAppData")
                or "")
        if init:
            user = validate_init_data(init)
            if user:
                return user
        # پشتیبانی از فرم پست (برای iframe و webviewهای خاص)
        if request.is_json:
            try:
                body_init = _json_body().get("init_data", "")
                if body_init:
                    user = validate_init_data(body_init)
                    if user:
                        return user
            except Exception:
                pass
        # حالت مهمان (وب‌محور): هر کسی با guest_id تصادفی + نام بتواند بازی کند
        # guest_id در localStorage کلاینت ذخیره می‌شود و هویت پایدار می‌دهد
        gid = (request.args.get("guest_id")
               or request.headers.get("X-Guest-Id")
               or "")
        gname = (request.args.get("guest_name")
                 or request.headers.get("X-Guest-Name")
                 or "")
        # همچنین از body
        if (not gid or not gname) and request.is_json:
            try:
                b = _json_body() or {}
                if not gid and b.get("guest_id"):
                    gid = str(b.get("guest_id"))
                if not gname and b.get("guest_name"):
                    gname = str(b.get("guest_name"))
            except Exception:
                pass
        if gid and gname:
            try:
                gid_int = int(gid)
            except (TypeError, ValueError):
                gid_int = 900000000 + (abs(hash(str(gid))) % 99000000)
            clean_name = (gname or "میهمان").strip()[:30] or "میهمان"
            return {"id": gid_int, "first_name": clean_name, "_guest": True}
        # حالت dev ریموت: با هدر X-Dev-Secret که سرور در استارتاپ تولید می‌کند
        # می‌توان از بیرون (مثلاً سندباکس دیباگ) بدون initData تلگرام تست کرد.
        dev_secret = request.headers.get("X-Dev-Secret", "")
        if config.DEV_SECRET and dev_secret and hmac.compare_digest(str(dev_secret), str(config.DEV_SECRET)):
            uid = request.args.get("user_id") or request.headers.get("X-User-Id")
            name = (request.args.get("user_name")
                    or request.headers.get("X-User-Name")
                    or "Arena-Test")
            try:
                uid_int = int(uid) if uid and uid != "None" else 900000001
            except (TypeError, ValueError):
                uid_int = 900000001
            return {"id": uid_int, "first_name": name or "Arena-Test", "_dev": True}
        if config.WEBAPP_DEV:
            uid = request.args.get("user_id") or request.headers.get("X-User-Id")
            name = (request.args.get("user_name")
                    or request.headers.get("X-User-Name")
                    or "ماجراجوی آزمایشی")
            try:
                uid_int = int(uid) if uid and uid != "None" else 900000001
            except (TypeError, ValueError):
                uid_int = 900000001
            return {"id": uid_int, "first_name": name or "ماجراجوی آزمایشی"}
        return None

    def need_user():
        u = get_user()
        if not u:
            return None, api_err("شناسایی نشدی — لطفاً نام خود را وارد کن تا وارد شوی.", 401)
        return u, None

    def _s(v, default=""):
        """هر مقداری را به string امن تبدیل می‌کند (برای جلوگیری از 500 روی garbage input)."""
        if v is None:
            return default
        try:
            return str(v).strip()
        except Exception:
            return default

    def room_of(code):
        code = _s(code).upper()
        if not code:
            return None
        if code in _rooms:
            return _rooms[code]
        s = store.find_by_code(code)
        if s:
            _rooms[code] = s
        return s

    def persist(s):
        store.save(s)
        _rooms[s.code] = s

    def sheet_of(ch: Character) -> dict:
        if not ch:
            return None
        return {
            "name": ch.name,
            "race_key": ch.race, "race": RACES[ch.race]["fa"], "race_emoji": RACES[ch.race]["emoji"],
            "cls_key": ch.cls, "cls": CLASSES[ch.cls]["fa"], "cls_emoji": CLASSES[ch.cls]["emoji"],
            "emoji": CLASSES[ch.cls]["emoji"],
            "level": ch.level, "xp": ch.xp,
            "xp_next": ch.xp_needed_for(ch.level + 1) if ch.level < 20 else None,
            "can_level_up": ch.can_level_up(),
            "hp": ch.hp, "max_hp": ch.max_hp, "ac": ch.ac, "gold": ch.gold,
            "weapon": WEAPONS[ch.weapon]["fa"], "weapon_emoji": WEAPONS[ch.weapon]["emoji"],
            "weapon_dmg": WEAPONS[ch.weapon]["dmg"], "weapon_key": ch.weapon,
            "attack_bonus": ch.attack_bonus(),
            "spell_attack_bonus": ch.spell_mod() + proficiency_bonus(ch.level) if hasattr(ch,"spell_mod") else 0,
            "abilities": [{"key": a, "fa": ABILITY_FA[a], "value": ch.abilities[a],
                           "mod": ch.stat_mod(a)} for a in ABILITIES],
            "features": ch.features(),
            "proficiencies": ch.proficiencies,
            "inventory": dict(ch.inventory),
            "conditions": list(ch.conditions),
            "inspiration": ch.inspiration,
            "rage_active": bool(getattr(ch, "rage_active", False)),
            "rage_turns": int(getattr(ch, "rage_turns", 0)),
            "dodge": bool(getattr(ch, "dodge", False)),
            "hidden": bool(getattr(ch, "hidden", False)),
            "spell_slots": dict(ch.spell_slots or {}),
            "spell_slots_used": dict(ch.spell_slots_used or {}),
            "resources": dict(ch.resources or {}),
            "hit_dice": ch.hit_die,
            "hit_dice_used": int(getattr(ch, "hit_dice_used", 0)),
            "death_saves": dict(getattr(ch, "death_saves", {"success": 0, "fail": 0})),
            "alive": bool(ch.hp > 0),
        }

    def _loc_name(l):
        if isinstance(l, dict):
            return l.get("name", str(l))
        return str(l)

    def _npc_name(n):
        if isinstance(n, dict):
            role = f" ({n.get('role','')})" if n.get("role") else ""
            return f"{n.get('name','؟')}{role}"
        return str(n)

    def scenario_view(s):
        """یک نسخه‌ی فیلترشده از سناریو برای ارسال به مرورگر (بدون پیچ/راز/NPC secret)."""
        if not s:
            return None
        return {
            "title": s.get("title"), "hook": s.get("hook"), "goal": s.get("goal"),
            "locations": [
                {"name": _loc_name(l),
                 "description": l.get("description","") if isinstance(l,dict) else "",
                 "encounter_hint": l.get("encounter_hint","") if isinstance(l,dict) else ""}
                for l in (s.get("locations") or [])
            ],
            "npcs": [{"name": (n.get("name") if isinstance(n,dict) else str(n)),
                      "role": (n.get("role") if isinstance(n,dict) else "")}
                     for n in (s.get("npcs") or [])],
            "encounters": [{
                "name": e.get("name","؟"), "count": e.get("count",1),
                "ac": e.get("ac"), "hp": e.get("hp"), "xp": e.get("xp"),
                "is_boss": bool(e.get("is_boss")),
                "location": e.get("location","")}
                for e in (s.get("encounters") or [])],
            "treasure": s.get("treasure"),
            "traps": [{"name": t.get("name",""), "location": t.get("location",""),
                       "detect_dc": t.get("detect_dc",13)}
                      for t in (s.get("traps") or []) if not t.get("triggered")],
            "branches": s.get("branches") or [],
            "boss": ({"name": s["boss"].get("name",""),
                      "ability": s["boss"].get("ability","")}
                     if isinstance(s.get("boss"),dict) else None),
        }

    def combat_of(room, uid=None) -> dict:
        c = room.combat
        if not c or not c.get("participants"):
            return None
        parts = c["participants"]
        idx = min(c.get("turn", 0), len(parts) - 1)
        out_parts = []
        for i, p in enumerate(parts):
            is_dead = bool(p.get("dead"))
            is_downed = bool(p.get("downed"))
            hp = p.get("hp", 0)
            max_hp = p.get("max_hp")
            if max_hp is None:
                # هیولاها HP اولیه خود را در _key/starting_hp ذخیره نکرده‌اند —
                # از hp اولیه در participant ساخته‌شده استفاده می‌کنیم.
                max_hp = max(p.get("hp", 1), 1)
                # به یاد داشته باش مقدار اولیه را در max_hp اولیه‌ی participant
                if not p.get("_max_hp_cached"):
                    p["_max_hp_cached"] = max_hp
                else:
                    max_hp = p["_max_hp_cached"]
            alive = (not is_dead) and p.get("alive", True) and hp > 0
            out_parts.append({
                "name": p["name"], "kind": p["kind"], "hp": hp, "max_hp": max_hp,
                "ac": p["ac"],
                "alive": alive, "downed": is_downed, "dead": is_dead,
                "init": p.get("init",0), "conditions": list(p.get("conditions",[])),
                "turn": i == idx,
                "acted": bool(p.get("acted", False)),
                "bonus_acted": bool(p.get("bonus_acted", False)),
                "uid": str(p.get("uid","")) if p.get("uid") is not None else None,
                "distance": p.get("distance", 0),
                "height": p.get("height", 0),
                "cover": p.get("cover", "none"),
                "surface": p.get("surface", "none"),
                "is_boss": bool(p.get("is_boss")),
                "emoji": p.get("emoji","👹" if p["kind"]=="monster" else "🧙"),
                "is_player": p["kind"] == "player",
                "is_me": p["kind"] == "player" and uid is not None and p.get("uid") == str(uid),
            })
        cur = parts[idx]
        return {
            "round": c.get("round", 1),
            "turn": idx,
            "current": cur["name"],
            "current_uid": str(cur.get("uid","")) if cur.get("uid") is not None else None,
            "current_is_player": cur["kind"] == "player",
            "is_my_turn": cur["kind"] == "player" and uid is not None and cur.get("uid") == str(uid),
            "participants": out_parts,
            "in_progress": True,
        }

    def build_state(room, user):
        uid = str(user.get("id"))
        member = uid in room.players
        players = []
        for u2, p in room.players.items():
            ch = p["char"]
            players.append({
                "uid": int(u2), "name": p["user"], "is_dm": int(u2) == room.dm_id,
                "char": None if not ch else {
                    "name": ch.name, "race": RACES[ch.race]["fa"],
                    "race_emoji": RACES[ch.race]["emoji"],
                    "cls": CLASSES[ch.cls]["fa"], "emoji": CLASSES[ch.cls]["emoji"],
                    "level": ch.level, "hp": ch.hp, "max_hp": ch.max_hp,
                    "ac": ch.ac, "alive": ch.hp > 0,
                },
            })
        my_sheet = None
        if member and room.get_char(user.get("id")):
            my_sheet = sheet_of(room.get_char(user.get("id")))
        world = getattr(room, "world", None) or {}
        return {
            "room": {
                "code": room.code, "name": room.name, "dm_name": room.dm_name,
                "dm_uid": room.dm_id, "state": room.state, "max_players": 8,
                "count": len(room.players), "char_count": room.char_count(),
                "is_member": member, "is_dm": member and room.dm_id == user.get("id"),
                "players": players,
                "location": world.get("location", ""),
                "locations": world.get("locations", []),
                "light": world.get("light", "dark"),
            },
            "me": {"uid": user.get("id"), "name": user.get("first_name", ""),
                   "is_member": member,
                   "has_char": member and room.get_char(user.get("id")) is not None,
                   "char": my_sheet},
            "scenario": scenario_view(room.scenario),
            "log": room.log[-40:],
            "combat": combat_of(room, user.get("id")),
        }

    def do_advance(room):
        """یک قدم نبرد + پایان خودکار وقتی همه دشمن‌ها مردند."""
        msgs = []
        if not room.combat:
            return msgs
        msgs.append(advance(room))
        if not room.combat:
            return msgs  # end_combat داخل advance ممکنه فراخوانی شده باشه
        # پایان خودکار نبرد اگر همه دشمن‌ها مردند
        monsters = [p for p in room.combat["participants"] if p["kind"] == "monster"]
        if monsters and all(not m.get("alive", False) for m in monsters):
            msgs.append(end_combat(room))
        return msgs

    # ---------- سلامت سرور (بدون احراز هویت — برای تونل و عیب‌یابی) ----------
    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "bot_token_set": bool(config.BOT_TOKEN),
                        "dev": config.WEBAPP_DEV, "rooms": len(_rooms)})

    # ---------- متادیتا ----------
    @app.get("/api/meta")
    def api_meta():
        return api_ok({
            "version": "2.59",
            "races": [{"key": k, "fa": v["fa"], "emoji": v["emoji"],
                       "bonus": ", ".join(f"{b:+d}" for b in v["bonus"].values())}
                      for k, v in RACES.items()],
            "classes": [{"key": k, "fa": v["fa"], "emoji": v["emoji"],
                         "hit_die": v["hit_die"], "weapons": v["weapons"]}
                        for k, v in CLASSES.items()],
            "weapons": {k: [{"key": w, "fa": WEAPONS[w]["fa"], "emoji": WEAPONS[w]["emoji"],
                             "dmg": WEAPONS[w]["dmg"]} for w in v["weapons"]]
                        for k, v in CLASSES.items()},
            "spells": [{"key": k, "fa": v["fa"], "emoji": v.get("emoji", "✨"),
                        "dmg": v.get("dmg", v.get("heal", "")),
                        "kind": v.get("kind", "utility"),
                        "level": v.get("level", 0),
                        "action": v.get("action", "main")} for k, v in SPELLS.items()],
            "monsters": [{"key": k, "fa": v["fa"], "emoji": v["emoji"]}
                         for k, v in MONSTERS.items()],
        })

    # ---------- اتاق ----------
    @app.post("/api/room/create")
    def api_room_create():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        name = _s(d.get("name"), "ماجرای جدید")[:40]
        room = Session(chat_id=_rand_chat_id(), name=name,
                       dm_id=user["id"], dm_name=user.get("first_name", "میزبان"))
        persist(room)
        return api_ok({"code": room.code, "state": build_state(room, user)})

    @app.post("/api/room/join")
    def api_room_join():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        code = d.get("code", "")
        room = room_of(code)
        if not room:
            return api_err("اتاق با این کد پیدا نشد!")
        if str(user["id"]) in room.players:
            return api_ok({"code": room.code, "state": build_state(room, user)})
        res = room.add_player(user["id"], user.get("first_name", "ماجراجو"))
        if res == "full":
            return api_err("اتاق پر است! (حداکثر ۸ بازیکن)")
        room.add_log("سیستم", f"{user.get('first_name','ماجراجو')} به اتاق پیوست")
        persist(room)
        return api_ok({"code": room.code, "state": build_state(room, user)})

    @app.get("/api/room/state")
    def api_room_state():
        user, err = need_user()
        if err:
            return err
        room = room_of(request.args.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        return api_ok(build_state(room, user))

    # ---------- کاراکتر ----------
    @app.post("/api/char/create")
    def api_char_create():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if str(user["id"]) not in room.players:
            return api_err("تو عضو این اتاق نیستی — اول با کد وارد شو.")
        if room.has_char(user["id"]):
            return api_err("قبلاً کاراکتر داری! (برای ساخت دوباره، اول با میزبان هماهنگ کن)")
        name = _s(d.get("name"), "بی‌نام")[:30]
        race = _s(d.get("race"))
        cls = _s(d.get("cls"))
        weapon = _s(d.get("weapon"))
        if race not in RACES:
            return api_err("نژاد نامعتبر است.")
        if cls not in CLASSES:
            return api_err("کلاس نامعتبر است.")
        if weapon not in CLASSES[cls]["weapons"]:
            return api_err("سلاح برای این کلاس نامعتبر است.")
        ch = Character(name=name, race=race, cls=cls, weapon=weapon)
        room.players[str(user["id"])]["char"] = ch
        if room.state == "lobby":
            room.state = "playing"
        room.add_log("سیستم", f"{ch.name} ({RACES[race]['fa']} {CLASSES[cls]['fa']}) به گروه پیوست")
        persist(room)
        return api_ok({"state": build_state(room, user)})

    @app.post("/api/char/levelup")
    def api_char_levelup():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        ch = room.get_char(user["id"])
        if not ch:
            return api_err("کاراکتر نداری!")
        if not ch.can_level_up():
            return api_err(f"هنوز XP کافی نداری ({ch.xp}/{ch.xp_needed_for(ch.level + 1)})")
        info = ch.level_up()
        room.add_log("سیستم", f"{ch.name} به سطح {info['new']} رسید! (+{info['hp_gain']} HP)")
        persist(room)
        return api_ok({"state": build_state(room, user), "level": info["new"]})

    # ---------- دانجن‌مستر ----------
    @app.post("/api/scenario")
    def api_scenario():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if room.dm_id != user["id"]:
            return api_err("فقط میزبان (DM) می‌تواند سناریو بسازد.")
        if room.char_count() < 1:
            return api_err("اول حداقل یک کاراکتر بسازید تا سناریو متناسب با گروه باشد.")
        req = _s(d.get("request"))
        scenario = narrator.scenario(room, req)
        room.scenario = scenario
        room.state = "playing"
        room.add_log("DM", f"سناریو ساخته شد: {scenario.get('title')}")
        persist(room)
        return api_ok({"state": build_state(room, user)})

    @app.post("/api/story")
    def api_story():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if str(user["id"]) not in room.players:
            return api_err("تو عضو این اتاق نیستی.")
        action = _s(d.get("action")) or "ادامه بده؛ چه اتفاقی می‌افتد؟"
        text = narrator.narrate(room, action)
        persist(room)
        return api_ok({"text": text, "state": build_state(room, user)})

    @app.post("/api/where")
    def api_where():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        text = narrator.recap(room)
        persist(room)
        return api_ok({"text": text, "state": build_state(room, user)})

    @app.post("/api/roll")
    def api_roll():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        expr = _s(d.get("expr"))
        if not expr:
            return api_err("مثل: 2d6+3 یا d20 یا adv")
        try:
            low = expr.lower()
            if low in ("adv", "advantage"):
                r = roll_advantage()
            elif low in ("dis", "disadvantage"):
                r = roll_disadvantage()
            else:
                r = roll_expression(expr)
        except DiceError as e:
            return api_err(str(e))
        room = room_of(d.get("room", ""))
        if room and str(user["id"]) in room.players:
            room.add_log(user.get("first_name", "بازیکن"),
                         f"تاس {expr}: {r['total']} ({r['breakdown']})")
            persist(room)
        crit = ""
        if low == "d20" or low.endswith("d20"):
            crit = " 🔥 بحرانی!" if r["total"] == 20 else (" 💔 شکست بحرانی!" if r["total"] == 1 else "")
        return api_ok({"result": r["total"], "breakdown": r["breakdown"], "crit": crit})

    # ---------- ماجراجویی خارج از نبرد ----------
    @app.post("/api/check")
    def api_check():
        user, err = need_user()
        if err: return err
        d = _json_body(); room = room_of(d.get("room", ""))
        if not room: return api_err("اتاق پیدا نشد!")
        if str(user["id"]) not in room.players: return api_err("تو عضو این اتاق نیستی.")
        try: dc = int(d.get("dc", 10))
        except (TypeError, ValueError): dc = 10
        text = skill_check(room, user["id"], _s(d.get("skill"), "perception"), dc, _s(d.get("mode"), "normal"))
        persist(room); return api_ok({"text": text, "state": build_state(room, user)})

    @app.post("/api/rest")
    def api_rest():
        user, err = need_user()
        if err: return err
        d = _json_body(); room = room_of(d.get("room", ""))
        if not room: return api_err("اتاق پیدا نشد!")
        text = rest(room, user["id"], _s(d.get("kind"), "short"))
        persist(room); return api_ok({"text": text, "state": build_state(room, user)})

    @app.post("/api/deathsave")
    def api_deathsave():
        """خارج از نبرد: درمان/احیای ساده. داخل نبرد: به هندلر نبرد ارجاع می‌شود."""
        user, err = need_user()
        if err: return err
        d = _json_body(); room = room_of(d.get("room", ""))
        if not room: return api_err("اتاق پیدا نشد!")
        ch = room.get_char(user["id"])
        if not ch: return api_err("کاراکتر نداری!")
        if room.combat:
            return api_combat_deathsave()
        text = death_save(room, user["id"])
        persist(room); return api_ok({"text": text, "state": build_state(room, user)})

    # ---------- حرکت/نقشه/محیط ----------
    @app.post("/api/move")
    def api_move():
        user, err = need_user()
        if err: return err
        d = _json_body(); room = room_of(d.get("room", ""))
        if not room: return api_err("اتاق پیدا نشد!")
        if room.combat: return api_err("در نبرد نمی‌توانی حرکت کنی.")
        direction = _s(d.get("direction") or d.get("text"), "جلو")
        from game.map import init_world
        init_world(room)
        text = move_to(room, direction)
        room.add_log(user.get("first_name","بازیکن"), f"حرکت: {direction}")
        persist(room)
        return api_ok({"text": text, "state": build_state(room, user)})

    @app.post("/api/where/look")
    @app.post("/api/look")
    def api_look():
        user, err = need_user()
        if err: return err
        d = _json_body(); room = room_of(d.get("room", ""))
        if not room: return api_err("اتاق پیدا نشد!")
        from game.map import init_world
        init_world(room)
        text = map_describe(room)
        return api_ok({"text": text, "state": build_state(room, user)})

    @app.post("/api/inventory")
    def api_inventory():
        user, err = need_user()
        if err: return err
        d = _json_body(); room = room_of(d.get("room", ""))
        if not room: return api_err("اتاق پیدا نشد!")
        ch = room.get_char(user["id"])
        if not ch: return api_err("کاراکتر نداری!")
        return api_ok({"text": inventory_text(ch), "state": build_state(room, user)})

    @app.get("/api/log")
    def api_debug_log():
        """لاگ‌های سمت سرور (حداکثر ۱۰۰ خط آخر) — برای عیب‌یابی مینی‌گیم."""
        try:
            log_path = os.path.join(
                os.environ.get("FILES_DIR", os.path.join(BASE_DIR, "data")), "bot.log")
            if not os.path.isfile(log_path):
                log_path = os.path.join(BASE_DIR, "bot.log")
            if os.path.isfile(log_path):
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                return jsonify({"ok": True, "log": "".join(lines[-200:])})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
        return jsonify({"ok": True, "log": ""})

    @app.post("/api/disarm")
    def api_disarm():
        user, err = need_user()
        if err: return err
        d = _json_body(); room = room_of(d.get("room", ""))
        if not room: return api_err("اتاق پیدا نشد!")
        ch = room.get_char(user["id"])
        if not ch: return api_err("کاراکتر نداری!")
        try: dc = int(d.get("dc", 0) or 0)
        except (TypeError, ValueError): dc = 0
        text = try_disarm_trap(room, ch, _s(d.get("name")), dc or None)
        persist(room)
        return api_ok({"text": text, "state": build_state(room, user)})

    @app.post("/api/inventory/use")
    def api_use_item():
        user, err = need_user()
        if err: return err
        d = _json_body(); room = room_of(d.get("room", ""))
        if not room: return api_err("اتاق پیدا نشد!")
        text = use_item(room, user["id"], _s(d.get("item")))
        persist(room); return api_ok({"text": text, "state": build_state(room, user)})

    # ---------- نبرد ----------
    @app.post("/api/combat/start")
    def api_combat_start():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if room.dm_id != user["id"]:
            return api_err("فقط میزبان می‌تواند نبرد را شروع کند.")
        if room.combat:
            return api_err("نبرد در جریان است!")
        msgs = [start_combat(room)]
        init_monster = run_initial_monsters(room)
        if init_monster:
            msgs.append(init_monster)
        persist(room)
        return api_ok({"messages": msgs, "state": build_state(room, user)})

    def _combat_action(action_fn, advance_after=True):
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if not room.combat:
            return api_err("نبردی در جریان نیست.")
        # اکشن‌های بونس‌اکشن بر اساس نام تابع تشخیص داده می‌شوند و نوبت را نمی‌سوزانند
        BONUS_FN_NAMES = {"rage", "bardic_inspiration", "offhand_attack", "divine_smite",
                         "cunning_action", "hellish_rebuke", "jump_action", "throw_action",
                         "dip_weapon", "help_up", "second_wind", "action_surge"}
        is_bonus = advance_after is False or getattr(action_fn, "__name__", "") in BONUS_FN_NAMES
        result_text = action_fn(room, user["id"])
        # پیام‌های خطا با این کلمات شروع می‌شوند → نوبت نسوزان
        error_prefixes = ("هنوز نوبت", "نمی‌توانی", "این قابلیت فقط", "تعداد", "هم‌گروهی",
                         "کاراکترت", "سلاح", "هدف پیدا نشد", "اکشن اصلی", "بونس‌اکشن",
                         "نبردی", "جایگاه", "نفس اژدها را", "فقط می‌توانی", "تو زمین",
                         "مردی", "نوبت تو نیست")
        success = bool(result_text) and not result_text.startswith(error_prefixes)
        if not is_bonus and success:
            msgs = [result_text] + do_advance(room)
        else:
            msgs = [result_text]
        persist(room)
        return api_ok({"messages": msgs, "state": build_state(room, user)})

    @app.post("/api/combat/attack")
    def api_combat_attack():
        d = _json_body()
        return _combat_action(lambda room, uid: attack(room, uid, _s(d.get("target"))))

    @app.post("/api/combat/cast")
    def api_combat_cast():
        d = _json_body()
        return _combat_action(lambda room, uid: cast(
            room, uid, _s(d.get("spell")), _s(d.get("target"))))

    @app.post("/api/combat/dodge")
    def api_combat_dodge():
        return _combat_action(lambda room, uid: dodge(room, uid))

    @app.post("/api/combat/dash")
    def api_combat_dash():
        return _combat_action(lambda room, uid: dash(room, uid))

    @app.post("/api/combat/disengage")
    def api_combat_disengage():
        return _combat_action(lambda room, uid: disengage(room, uid))

    @app.post("/api/combat/help")
    def api_combat_help():
        d = _json_body()
        return _combat_action(lambda room, uid: help_action(room, uid, _s(d.get("target"))))

    @app.post("/api/combat/hide")
    def api_combat_hide():
        return _combat_action(lambda room, uid: hide(room, uid))

    @app.post("/api/combat/shove")
    def api_combat_shove():
        d = _json_body()
        return _combat_action(lambda room, uid: shove(room, uid, _s(d.get("target"))))

    @app.post("/api/combat/secondwind")
    def api_combat_secondwind():
        return _combat_action(lambda room, uid: second_wind(room, uid))

    @app.post("/api/combat/actionsurge")
    def api_combat_actionsurge():
        return _combat_action(lambda room, uid: action_surge(room, uid))

    @app.post("/api/combat/rage")
    def api_combat_rage():
        return _combat_action(lambda room, uid: rage(room, uid))

    @app.post("/api/combat/inspire")
    def api_combat_inspire():
        d = _json_body()
        return _combat_action(lambda room, uid: bardic_inspiration(room, uid, _s(d.get("target"))))

    @app.post("/api/combat/move")
    def api_combat_move():
        d = _json_body()
        return _combat_action(lambda room, uid: move_action(room, uid, _s(d.get("where"), "near")))

    @app.post("/api/combat/offhand")
    def api_combat_offhand():
        d = _json_body()
        return _combat_action(lambda room, uid: offhand_attack(room, uid, _s(d.get("target"))))

    @app.post("/api/combat/smite")
    def api_combat_smite():
        d = _json_body()
        try: slot = int(d.get("slot", 1))
        except (TypeError, ValueError): slot = 1
        return _combat_action(lambda room, uid: divine_smite(room, uid, slot))

    @app.post("/api/combat/jump")
    def api_combat_jump():
        d = _json_body()
        return _combat_action(lambda room, uid: jump_action(room, uid, _s(d.get("where"), "near")))

    @app.post("/api/combat/helpup")
    def api_combat_helpup():
        d = _json_body()
        return _combat_action(lambda room, uid: help_up(room, uid, _s(d.get("target"))))

    @app.post("/api/combat/throw")
    def api_combat_throw():
        d = _json_body()
        item = _s(d.get("item"), "torch") or "torch"
        return _combat_action(lambda room, uid: throw_action(room, uid, item, _s(d.get("target"))))

    @app.post("/api/combat/dip")
    def api_combat_dip():
        d = _json_body()
        return _combat_action(lambda room, uid: dip_weapon(room, uid, _s(d.get("element"), "fire")))

    @app.post("/api/combat/cunning")
    def api_combat_cunning():
        d = _json_body()
        return _combat_action(lambda room, uid: cunning_action(room, uid, _s(d.get("what"), "disengage")))

    @app.post("/api/combat/rebuke")
    def api_combat_rebuke():
        return _combat_action(lambda room, uid: hellish_rebuke(room, uid))

    @app.post("/api/combat/deathsave")
    def api_combat_deathsave():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        ch = room.get_char(user["id"])
        if not ch or ch.hp > 0:
            return api_err("تو زمین‌گیر نیستی!")
        text = death_save(room, user["id"])
        msgs = [text]
        # بعد از مرگ‌سیو (چه موفق و چه ناموفق)، نوبت را جلو ببر
        # اگر در این مرگ‌سیو فوت کرده، جلو نرو
        failed = ch.death_saves.get("fail", 0) >= 3 or any(
            p.get("dead") for p in (room.combat or {}).get("participants", [])
            if p.get("kind") == "player" and p.get("uid") == str(user["id"])
        )
        if room.combat and not failed:
            msgs += do_advance(room)
        persist(room)
        return api_ok({"messages": msgs, "state": build_state(room, user)})

    @app.post("/api/combat/skip")
    def api_combat_skip():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if not room.combat:
            return api_err("نبردی در جریان نیست.")
        # در حالت DEV اجازه می‌دهیم با skip در نوبت دشمن هم جلو برویم (برای تست)
        if not config.WEBAPP_DEV and not is_player_turn(room, user["id"]):
            return api_err("هنوز نوبت تو نیست.")
        msgs = do_advance(room)
        persist(room)
        return api_ok({"messages": msgs, "state": build_state(room, user)})

    @app.post("/api/combat/end")
    def api_combat_end():
        user, err = need_user()
        if err:
            return err
        d = _json_body()
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if room.dm_id != user["id"]:
            return api_err("فقط میزبان می‌تواند نبرد را پایان دهد.")
        if not room.combat:
            return api_err("نبردی در جریان نیست.")
        msgs = [end_combat(room)]
        persist(room)
        return api_ok({"messages": msgs, "state": build_state(room, user)})

    # ---------- صفحه ----------
    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        return send_from_directory(WEB_DIR, filename)

    return app
