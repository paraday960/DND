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
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory

import config
from game.combat import advance, attack, cast, end_combat, start_combat
from game.dice import (
    DiceError, roll_advantage, roll_disadvantage, roll_expression,
)
from game.models import Character, Session
from game.rules import ABILITIES, CLASSES, MONSTERS, RACES, SPELLS, WEAPONS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

_rooms = {}  # cache: code -> Session


def _rand_chat_id() -> int:
    return random.randint(10**9, 2 * 10**9)


def validate_init_data(init_data: str):
    """اعتبارسنجی initData تلگرام — کلید مخفی از توکن ربات ساخته می‌شود."""
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
        received = params.pop("hash", None)
        if not received or not config.BOT_TOKEN:
            return None
        secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            return None
        return json.loads(params.get("user", "{}"))
    except Exception:
        return None


def build_app(store, narrator, telegram_app=None, loop=None):
    app = Flask(__name__)

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

    def get_user():
        init = request.headers.get("X-Init-Data") or request.args.get("init_data") or ""
        if init:
            user = validate_init_data(init)
            if user:
                return user
        if config.WEBAPP_DEV:
            uid = request.args.get("user_id") or request.headers.get("X-User-Id")
            name = (request.args.get("user_name")
                    or request.headers.get("X-User-Name")
                    or "ماجراجوی آزمایشی")
            if uid:
                return {"id": int(uid), "first_name": name}
            return {"id": 900000001, "first_name": "ماجراجوی آزمایشی"}
        return None

    def need_user():
        u = get_user()
        if not u:
            return None, api_err("شناسایی نشدی — مینی‌گیم را از داخل تلگرام باز کن.", 401)
        return u, None

    def room_of(code):
        code = (code or "").strip().upper()
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
            "level": ch.level, "xp": ch.xp,
            "xp_next": ch.xp_needed_for(ch.level + 1) if ch.level < 20 else None,
            "can_level_up": ch.can_level_up(),
            "hp": ch.hp, "max_hp": ch.max_hp, "ac": ch.ac, "gold": ch.gold,
            "weapon": WEAPONS[ch.weapon]["fa"], "weapon_emoji": WEAPONS[ch.weapon]["emoji"],
            "weapon_dmg": WEAPONS[ch.weapon]["dmg"], "attack_bonus": ch.attack_bonus(),
            "abilities": [{"key": a, "fa": ABILITIES_FA[a], "value": ch.abilities[a],
                           "mod": ch.stat_mod(a)} for a in ABILITIES],
            "features": ch.features(),
        }

    from game.rules import ABILITY_FA as ABILITIES_FA

    def combat_of(room, uid=None) -> dict:
        c = room.combat
        if not c or not c.get("participants"):
            return None
        parts = c["participants"]
        idx = min(c.get("turn", 0), len(parts) - 1)
        out_parts = []
        for i, p in enumerate(parts):
            out_parts.append({
                "name": p["name"], "kind": p["kind"], "hp": p["hp"],
                "max_hp": p.get("max_hp", p["hp"]), "ac": p["ac"],
                "alive": p["alive"], "init": p["init"], "turn": i == idx,
                "is_player": p["kind"] == "player",
                "is_me": p["kind"] == "player" and uid is not None and p.get("uid") == str(uid),
            })
        cur = parts[idx]
        return {
            "round": c.get("round", 1),
            "current": cur["name"],
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
                    "cls": CLASSES[ch.cls]["fa"], "emoji": CLASSES[ch.cls]["emoji"],
                    "level": ch.level, "hp": ch.hp, "max_hp": ch.max_hp,
                    "ac": ch.ac, "alive": ch.hp > 0,
                },
            })
        my_sheet = None
        if member and room.get_char(user.get("id")):
            my_sheet = sheet_of(room.get_char(user.get("id")))
        return {
            "room": {
                "code": room.code, "name": room.name, "dm_name": room.dm_name,
                "dm_uid": room.dm_id, "state": room.state, "max_players": 8,
                "count": len(room.players), "char_count": room.char_count(),
                "is_member": member, "is_dm": member and room.dm_id == user.get("id"),
                "players": players,
            },
            "me": {"uid": user.get("id"), "name": user.get("first_name", ""),
                   "is_member": member,
                   "has_char": member and room.get_char(user.get("id")) is not None,
                   "char": my_sheet},
            "scenario": room.scenario,
            "log": room.log[-40:],
            "combat": combat_of(room, user.get("id")),
        }

    def do_advance(room):
        """یک قدم نبرد + پایان خودکار وقتی همه دشمن‌ها مردند."""
        msgs = []
        if not room.combat:
            return msgs
        msgs.append(advance(room))
        monsters = [p for p in room.combat["participants"] if p["kind"] == "monster"]
        if monsters and all(not m["alive"] for m in monsters):
            msgs.append(end_combat(room))
        return msgs

    # ---------- متادیتا ----------
    @app.get("/api/meta")
    def api_meta():
        return api_ok({
            "races": [{"key": k, "fa": v["fa"], "emoji": v["emoji"],
                       "bonus": ", ".join(f"{b:+d}" for b in v["bonus"].values())}
                      for k, v in RACES.items()],
            "classes": [{"key": k, "fa": v["fa"], "emoji": v["emoji"],
                         "hit_die": v["hit_die"], "weapons": v["weapons"]}
                        for k, v in CLASSES.items()],
            "weapons": {k: [{"key": w, "fa": WEAPONS[w]["fa"], "emoji": WEAPONS[w]["emoji"],
                             "dmg": WEAPONS[w]["dmg"]} for w in v["weapons"]]
                        for k, v in CLASSES.items()},
            "spells": [{"key": k, "fa": v["fa"], "emoji": v["emoji"],
                        "dmg": v["dmg"], "kind": v["kind"]} for k, v in SPELLS.items()],
            "monsters": [{"key": k, "fa": v["fa"], "emoji": v["emoji"]}
                         for k, v in MONSTERS.items()],
        })

    # ---------- اتاق ----------
    @app.post("/api/room/create")
    def api_room_create():
        user, err = need_user()
        if err:
            return err
        d = request.json or {}
        name = (d.get("name") or "ماجرای جدید").strip()[:40]
        room = Session(chat_id=_rand_chat_id(), name=name,
                       dm_id=user["id"], dm_name=user.get("first_name", "میزبان"))
        persist(room)
        return api_ok({"code": room.code, "state": build_state(room, user)})

    @app.post("/api/room/join")
    def api_room_join():
        user, err = need_user()
        if err:
            return err
        code = (request.json or {}).get("code", "")
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
        d = request.json or {}
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if str(user["id"]) not in room.players:
            return api_err("تو عضو این اتاق نیستی — اول با کد وارد شو.")
        if room.has_char(user["id"]):
            return api_err("قبلاً کاراکتر داری! (برای ساخت دوباره، اول با میزبان هماهنگ کن)")
        name = (d.get("name") or "بی‌نام").strip()[:30]
        race = d.get("race", "")
        cls = d.get("cls", "")
        weapon = d.get("weapon", "")
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
        d = request.json or {}
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
        d = request.json or {}
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if room.dm_id != user["id"]:
            return api_err("فقط میزبان (DM) می‌تواند سناریو بسازد.")
        if room.char_count() < 1:
            return api_err("اول حداقل یک کاراکتر بسازید تا سناریو متناسب با گروه باشد.")
        req = (d.get("request") or "").strip()
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
        d = request.json or {}
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if str(user["id"]) not in room.players:
            return api_err("تو عضو این اتاق نیستی.")
        action = (d.get("action") or "").strip() or "ادامه بده؛ چه اتفاقی می‌افتد؟"
        text = narrator.narrate(room, action)
        persist(room)
        return api_ok({"text": text, "state": build_state(room, user)})

    @app.post("/api/where")
    def api_where():
        user, err = need_user()
        if err:
            return err
        d = request.json or {}
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
        d = request.json or {}
        expr = (d.get("expr") or "").strip()
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

    # ---------- نبرد ----------
    @app.post("/api/combat/start")
    def api_combat_start():
        user, err = need_user()
        if err:
            return err
        d = request.json or {}
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if room.dm_id != user["id"]:
            return api_err("فقط میزبان می‌تواند نبرد را شروع کند.")
        if room.combat:
            return api_err("نبرد در جریان است!")
        msgs = [start_combat(room)]
        if room.combat and room.combat["participants"][0]["kind"] == "monster":
            msgs += do_advance(room)
        persist(room)
        return api_ok({"messages": msgs, "state": build_state(room, user)})

    def _combat_action(action_fn):
        user, err = need_user()
        if err:
            return err
        d = request.json or {}
        room = room_of(d.get("room", ""))
        if not room:
            return api_err("اتاق پیدا نشد!")
        if not room.combat:
            return api_err("نبردی در جریان نیست.")
        msgs = [action_fn(room, user["id"])]
        msgs += do_advance(room)
        persist(room)
        return api_ok({"messages": msgs, "state": build_state(room, user)})

    @app.post("/api/combat/attack")
    def api_combat_attack():
        d = request.json or {}
        return _combat_action(lambda room, uid: attack(room, uid, d.get("target", "")))

    @app.post("/api/combat/cast")
    def api_combat_cast():
        d = request.json or {}
        return _combat_action(lambda room, uid: cast(
            room, uid, d.get("spell", ""), d.get("target", "")))

    @app.post("/api/combat/skip")
    def api_combat_skip():
        return _combat_action(lambda room, uid: advance(room))

    @app.post("/api/combat/end")
    def api_combat_end():
        user, err = need_user()
        if err:
            return err
        d = request.json or {}
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

    return app
