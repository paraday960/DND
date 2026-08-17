# -*- coding: utf-8 -*-
"""
🚀 اندروید: اجرای خودکار ربات D&D + مینی‌گیم + تونل امن — فقط با کتابخانه استاندارد پایتون.
این ماژول توسط BotService (Kotlin) صدا زده می‌شود: android_bot.main(files_dir)
"""
import hashlib
import hmac
import json
import os
import random
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FILES_DIR = ""
STOP_FILE = ""
CHAR_STATE = {}   # chat_id -> مرحله ساخت کاراکتر
_last_409_log = 0.0


# ==================== ابزار پایه ====================

def log(msg):
    try:
        with open(os.path.join(FILES_DIR, "bot.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def stopped():
    return os.path.exists(STOP_FILE)


def tunnel_url():
    try:
        with open(os.path.join(FILES_DIR, "tunnel_url.txt"), encoding="utf-8") as f:
            u = f.read().strip()
        return u if u.startswith("https://") else ""
    except Exception:
        return ""


# ==================== تلگرام ====================

def tg(method, payload=None, timeout=40):
    token = os.environ.get("BOT_TOKEN", "")
    url = "https://api.telegram.org/bot%s/%s" % (token, method)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        global _last_409_log
        if e.code == 409:
            now = time.time()
            if now - _last_409_log > 60:
                _last_409_log = now
                log("⚠️ خطای 409: نمونه دیگری از ربات با همین توکن در حال اجراست (در Termux، گوشی دیگر یا هاست). آن را متوقف کن — این نسخه خودکار ادامه می‌دهد")
            time.sleep(8)
        else:
            log("TG %s: %s" % (method, e))
        return None
    except Exception as e:
        log("TG %s: %s" % (method, e))
        return None


def send(chat_id, text, kb=None):
    p = {"chat_id": chat_id, "text": text}
    if kb:
        p["reply_markup"] = kb
    return tg("sendMessage", p)


def edit(chat_id, msg_id, text, kb=None):
    p = {"chat_id": chat_id, "message_id": msg_id, "text": text}
    if kb:
        p["reply_markup"] = kb
    return tg("editMessageText", p)


def ans_cb(cb_id, text=None):
    p = {"callback_query_id": cb_id}
    if text:
        p["text"] = text
    return tg("answerCallbackQuery", p)


def kb(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": c} for t, c in row] for row in rows]}


def webapp_kb(url):
    return {"inline_keyboard": [[{"text": "🎮 ورود به مینی‌گیم", "web_app": {"url": url}}]]}


WELCOME = ("🐉 به دانجن‌مستر هوشمند خوش اومدی!\n\n"
           "این ربات با هوش مصنوعی سناریو می‌سازه، روایت می‌کنه و دانجن‌مستری می‌کنه — تا ۸ بازیکن!\n\n"
           "🎮 همه‌چیز داخل مینی‌گیم انجام می‌شه: دکمه زیر رو بزن.\n"
           "🧙 یا با دستورها: /newgame → /newchar → /scenario → /story\n"
           "📚 راهنمای کامل: /help")

HELP = ("📚 راهنما:\n"
        "🎮 /newgame — اتاق بساز (کد می‌گیری)\n"
        "🔗 /join <کد> — با کد وارد شو\n"
        "🧙 /newchar — ساخت کاراکتر\n"
        "📜 /sheet — کاراکترت\n"
        "👥 /party — گروه\n"
        "🐉 /scenario — سناریوی AI (میزبان)\n"
        "📖 /story <اقدام> — روایت AI\n"
        "🗺️ /where — خلاصه ماجرا\n"
        "⚔️ /combat — شروع نبرد | /attack <دشمن> | /cast <طلسم> | /skip\n"
        "🎲 /roll 2d6+3 یا d20 یا adv\n"
        "⭐ /levelup | 💠 /xp\n\n"
        "🎮 برای مینی‌گیم گرافیکی: /start و دکمه ورود")


# ==================== دسترسی به ماژول‌های بازی ====================

def get_store():
    import config
    from game.store import Store
    return Store(config.DB_PATH)


def get_narrator():
    from game.narrator import Narrator
    return Narrator()


def room_of(store, chat_id):
    return store.load(chat_id)


def need_room(store, chat_id):
    s = room_of(store, chat_id)
    return s, (None if s else "❌ اول /newgame بزن (میزبان) یا /join <کد> (بقیه)")


def user_char(session, uid):
    return session.get_char(uid) if session else None


def is_dm(session, uid):
    return session.dm_id == uid


# ==================== دستورها ====================

def cmd_start(store, chat, uid, uname, args):
    url = tunnel_url()
    if url:
        send(chat, WELCOME, webapp_kb(url))
    else:
        send(chat, WELCOME)


def cmd_help(store, chat, uid, uname, args):
    send(chat, HELP)


def cmd_newgame(store, chat, uid, uname, args):
    from game.models import Session
    s = room_of(store, chat)
    if s and len(s.players) > 0:
        send(chat, "⚠️ تو این چت اتاقی با کد `%s` هست. برای ریست: /reset" % s.code)
        return
    s = Session(chat, "ماجرای " + (uname or "بی‌نام"), uid, uname or "میزبان")
    store.save(s)
    send(chat, "🎮 اتاق ساخته شد!\n🔑 کد: `%s`\n👥 ظرفیت ۸ نفر\n🧙 کاراکترت رو بساز: /newchar\n🐉 بعدش: /scenario" % s.code)


def cmd_reset(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    if not is_dm(s, uid):
        send(chat, "فقط میزبان می‌تونه.")
        return
    store.delete(chat)
    send(chat, "🗑️ اتاق ریست شد. /newgame")


def cmd_join(store, chat, uid, uname, args):
    code = (args[0] if args else "").strip().upper()
    if not code:
        send(chat, "مثل: /join K7Q2A")
        return
    s = store.find_by_code(code)
    if not s:
        send(chat, "اتاق با این کد پیدا نشد!")
        return
    if str(uid) in s.players:
        send(chat, "تو عضو این اتاقی! کاراکترت رو بساز: /newchar")
        return
    res = s.add_player(uid, uname or "ماجراجو")
    if res == "full":
        send(chat, "اتاق پر است (۸ نفر)!")
        return
    s.add_log("سیستم", "%s به اتاق پیوست" % (uname or "ماجراجو"))
    store.save(s)
    send(chat, "✅ به اتاق %s پیوستی! 🧙 /newchar" % s.code)


def cmd_sheet(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    ch = user_char(s, uid)
    if not ch:
        send(chat, "🧙 هنوز کاراکتر نداری: /newchar")
        return
    send(chat, ch.sheet_text())


def cmd_party(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    lines = ["👥 گروه (کد: `%s`)" % s.code, ""]
    for u2, p in s.players.items():
        ch = p["char"]
        role = "👑 DM" if int(u2) == s.dm_id else ""
        if ch:
            lines.append("• %s — %s %s لv%d ❤️%d/%d %s" % (ch.name, ch.race, ch.cls, ch.level, ch.hp, ch.max_hp, role))
        else:
            lines.append("• %s (بدون کاراکتر) %s" % (p["user"], role))
    lines.append("\n%d/۸ نفر — کاراکتر: %d" % (len(s.players), s.char_count()))
    send(chat, "\n".join(lines))


def cmd_roll(store, chat, uid, uname, args):
    from game.dice import roll_expression, roll_advantage, roll_disadvantage, DiceError
    expr = " ".join(args) if args else ""
    if not expr:
        send(chat, "🎲 مثل: /roll 2d6+3 یا /roll d20 یا /roll adv")
        return
    try:
        low = expr.lower()
        if low in ("adv", "advantage"):
            r = roll_advantage()
        elif low in ("dis", "disadvantage"):
            r = roll_disadvantage()
        else:
            r = roll_expression(expr)
    except DiceError as e:
        send(chat, "❌ " + str(e))
        return
    s = room_of(store, chat)
    if s:
        s.add_log(uname or "بازیکن", "تاس %s: %s (%s)" % (expr, r["total"], r["breakdown"]))
        store.save(s)
    crit = ""
    if low == "d20" or low.endswith("d20"):
        crit = "\n🔥 بحرانی!" if r["total"] == 20 else ("\n💔 شکست!" if r["total"] == 1 else "")
    send(chat, "🎲 %s تاس %s:\n**نتیجه: %s** (%s)%s" % (uname or "بازیکن", expr, r["total"], r["breakdown"], crit))


def cmd_scenario(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    if not is_dm(s, uid):
        send(chat, "🐉 فقط میزبان سناریو می‌سازه.")
        return
    if s.char_count() < 1:
        send(chat, "اول حداقل یه کاراکتر بسازید (/newchar).")
        return
    send(chat, "🧠 هوش مصنوعی داره سناریو می‌سازه... چند لحظه ⏳")

    def work():
        narrator = get_narrator()
        scenario = narrator.scenario(s, " ".join(args))
        s.scenario = scenario
        s.state = "playing"
        s.add_log("DM", "سناریو ساخته شد: %s" % scenario.get("title"))
        store.save(s)
        send(chat, "🐉 **سناریو:**\n\n" + s.scenario_text() + "\n\nحالا با /story شروع کن!")

    threading.Thread(target=work, daemon=True).start()


def cmd_story(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    action = " ".join(args) or "ادامه بده؛ چه اتفاقی می‌افته؟"
    send(chat, "📖 روایت در جریان است...")

    def work():
        narrator = get_narrator()
        text = narrator.narrate(s, action)
        store.save(s)
        send(chat, "📖 " + text)

    threading.Thread(target=work, daemon=True).start()


def cmd_where(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    send(chat, "🗺️ در حال مرور ذهن دانجن‌مستر...")

    def work():
        narrator = get_narrator()
        text = narrator.recap(s)
        store.save(s)
        send(chat, text)

    threading.Thread(target=work, daemon=True).start()


def cmd_combat(store, chat, uid, uname, args):
    from game.combat import start_combat, advance
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    if s.combat:
        from game.combat import order_text
        send(chat, order_text(s))
        return
    if not is_dm(s, uid):
        send(chat, "فقط میزبان نبرد رو شروع می‌کنه.")
        return
    if not s.scenario:
        send(chat, "🐉 اول /scenario تا دشمن‌ها معلوم شن (فعلاً پیش‌فرض).")
    text = start_combat(s)
    store.save(s)
    send(chat, text)
    if s.combat and s.combat["participants"][0]["kind"] == "monster":
        t2 = advance(s)
        store.save(s)
        send(chat, t2)


def cmd_attack(store, chat, uid, uname, args):
    from game.combat import attack, advance
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    if not s.combat:
        send(chat, "نبردی نیست. /combat")
        return
    target = " ".join(args)
    if not target:
        send(chat, "مثل: /attack گابلین")
        return
    result = attack(s, uid, target)
    store.save(s)
    send(chat, result)
    t2 = advance(s)
    store.save(s)
    send(chat, t2)


def cmd_cast(store, chat, uid, uname, args):
    from game.combat import cast, advance
    from game.rules import SPELLS
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    if not s.combat:
        send(chat, "نبردی نیست. /combat")
        return
    if not args:
        send(chat, "مثل: /cast firebolt گابلین\nطلسم‌ها: " + ", ".join("`%s`" % k for k in SPELLS))
        return
    result = cast(s, uid, args[0].lower(), " ".join(args[1:]))
    store.save(s)
    send(chat, result)
    t2 = advance(s)
    store.save(s)
    send(chat, t2)


def cmd_skip(store, chat, uid, uname, args):
    from game.combat import advance
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    if not s.combat:
        send(chat, "نبردی نیست.")
        return
    t = advance(s)
    store.save(s)
    send(chat, t)


def cmd_combatend(store, chat, uid, uname, args):
    from game.combat import end_combat
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    if not s.combat:
        send(chat, "نبردی نیست.")
        return
    if not is_dm(s, uid):
        send(chat, "فقط میزبان.")
        return
    t = end_combat(s)
    store.save(s)
    send(chat, t)


def cmd_levelup(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    ch = user_char(s, uid)
    if not ch:
        send(chat, "اول /newchar")
        return
    if not ch.can_level_up():
        send(chat, "XP کافی نداری (%d/%d)" % (ch.xp, ch.xp_needed_for(ch.level + 1)))
        return
    info = ch.level_up()
    store.save(s)
    send(chat, "🎉 %s به سطح %d رسید! (+%d HP)\n✨ %s" % (ch.name, info["new"], info["hp_gain"], "، ".join(info["features"])))


def cmd_xp(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    ch = user_char(s, uid)
    if not ch:
        send(chat, "اول /newchar")
        return
    nxt = ch.xp_needed_for(ch.level + 1) if ch.level < 20 else "—"
    send(chat, "⭐ %s: %d XP — سطح %d\nبرای سطح بعد: %s" % (ch.name, ch.xp, ch.level, nxt))


def cmd_newchar(store, chat, uid, uname, args):
    s, err = need_room(store, chat)
    if err:
        send(chat, err)
        return
    if user_char(s, uid):
        send(chat, "قبلاً کاراکتر داری (/sheet). برای ساخت دوباره با میزبان هماهنگ کن.")
        return
    CHAR_STATE[chat] = {"step": "name", "uid": uid}
    send(chat, "🧙 **ساخت کاراکتر**\nاسم شخصیتت رو بفرست (مثلاً: آرین)\nلغو: /cancel")


def _handle_natural(store, chat, uid, uname, text):
    """متن طبیعی فارسی را به اکشن بازی تبدیل می‌کند."""
    from game.nlp import parse_action
    from game.dice import roll_expression, DiceError
    s = room_of(store, chat)
    ch = user_char(s, uid) if s else None
    in_combat = bool(s and s.combat)
    mobs = []
    if in_combat:
        mobs = [p["name"] for p in s.combat["participants"]
                if p.get("kind") == "monster" and p.get("alive")]
    act = parse_action(text, in_combat=in_combat, has_char=bool(ch),
                        valid_monsters=mobs, is_dm=(s and is_dm(s, uid)))
    a = act.get("action")

    if a == "attack":
        if not in_combat:
            send(chat, "نبردی در جریان نیست. اول بگو «شروع نبرد».")
            return
        tgt = act.get("target") or (mobs[0] if mobs else "")
        from game.combat import attack, advance
        send(chat, attack(s, uid, tgt))
        store.save(s)
        t = advance(s)
        store.save(s)
        if t: send(chat, t)
        return
    if a == "cast":
        from game.combat import cast, advance
        send(chat, cast(s, uid, act.get("spell", "firebolt"), act.get("target", "")))
        store.save(s)
        t = advance(s)
        store.save(s)
        if t: send(chat, t)
        return
    if a == "dodge":
        from game.combat import dodge, advance
        send(chat, dodge(s, uid))
        store.save(s)
        t = advance(s)
        store.save(s)
        if t: send(chat, t)
        return
    if a == "skip":
        from game.combat import advance
        send(chat, advance(s))
        store.save(s)
        return
    if a == "deathsave":
        from game.adventure import death_save
        from game.combat import advance
        send(chat, death_save(s, uid))
        store.save(s)
        if s.combat:
            t = advance(s)
            store.save(s)
            if t: send(chat, t)
        return
    if a == "potion":
        from game.adventure import use_item
        send(chat, use_item(s, uid, "potion"))
        store.save(s)
        return
    if a == "roll":
        try:
            r = roll_expression(act.get("expr", "d20"))
            send(chat, "🎲 نتیجه %s: **%s** (%s)" % (act.get("expr"), r["total"], r["breakdown"]))
        except DiceError as e:
            send(chat, "❌ " + str(e))
        return
    if a == "rest":
        from game.adventure import rest
        send(chat, rest(s, uid, act.get("kind", "short")))
        store.save(s)
        return
    if a == "torch":
        from game.world import try_environment_action
        r = try_environment_action(s, ch, "مشعل روشن می‌کنم")
        if r:
            send(chat, r)
            store.save(s)
        else:
            cmd_story(store, chat, uid, uname, [text])
        return
    if a == "look":
        if in_combat:
            from game.combat import order_text
            send(chat, order_text(s))
        else:
            cmd_where(store, chat, uid, uname, [])
        return
    if a == "sheet":
        cmd_sheet(store, chat, uid, uname, [])
        return
    if a == "party":
        cmd_party(store, chat, uid, uname, [])
        return
    if a == "scenario":
        cmd_scenario(store, chat, uid, uname, [])
        return
    if a == "combat":
        cmd_combat(store, chat, uid, uname, [])
        return
    if a == "help":
        send(chat, HELP)
        return
    if a == "wait":
        send(chat, "⏳ چند لحظه صبر می‌کنی...")
        return
    if a == "talk":
        cmd_story(store, chat, uid, uname, [text])
        return
    cmd_story(store, chat, uid, uname, [act.get("text", text)])


def on_message(store, msg):
    chat = msg["chat"]["id"]
    uid = msg["from"]["id"]
    uname = msg["from"].get("first_name") or "بازیکن"
    text = msg.get("text", "")

    # مرحله ساخت کاراکتر (نام)
    st = CHAR_STATE.get(chat)
    if st and st.get("step") == "name" and not text.startswith("/"):
        st["name"] = text.strip()[:30]
        st["step"] = "race"
        from game.rules import RACES
        rows = [[("%s %s" % (RACES[k]["emoji"], RACES[k]["fa"]), "race:" + k)] for k in RACES]
        send(chat, "خوش اومدی **%s**! نژادت رو انتخاب کن:" % text.strip()[:30], kb(rows))
        return

    # متن طبیعی فارسی
    if text and not text.startswith("/"):
        try:
            _handle_natural(store, chat, uid, uname, text)
            return
        except Exception as e:
            log("natural handler: %s" % e)
            send(chat, "🤔 منظورت رو نفهمیدم. /help")
            return

    parts = text[1:].split()
    cmd = parts[0].lower()
    args = parts[1:]

    handlers = {
        "start": cmd_start, "help": cmd_help, "game": cmd_start,
        "newgame": cmd_newgame, "reset": cmd_reset, "join": cmd_join,
        "sheet": cmd_sheet, "party": cmd_party, "roll": cmd_roll,
        "scenario": cmd_scenario, "story": cmd_story, "where": cmd_where,
        "combat": cmd_combat, "attack": cmd_attack, "cast": cmd_cast,
        "skip": cmd_skip, "combatend": cmd_combatend,
        "levelup": cmd_levelup, "xp": cmd_xp, "newchar": cmd_newchar,
    }
    fn = handlers.get(cmd)
    if fn:
        try:
            fn(store, chat, uid, uname, args)
        except Exception as e:
            log("خطا در %s: %s" % (cmd, e))
            send(chat, "⚠️ خطایی رخ داد: %s" % e)
    else:
        send(chat, "🤔 دستور ناشناخته. /help")


def on_callback(store, cb):
    chat = cb["message"]["chat"]["id"]
    uid = cb["from"]["id"]
    msg_id = cb["message"]["message_id"]
    data = cb.get("data", "")

    st = CHAR_STATE.get(chat)

    if data.startswith("race:"):
        ans_cb(cb["id"])
        if not st:
            return
        race = data.split(":", 1)[1]
        st["race"] = race
        st["step"] = "class"
        from game.rules import CLASSES
        rows = [[("%s %s" % (CLASSES[k]["emoji"], CLASSES[k]["fa"]), "class:" + k)] for k in CLASSES]
        edit(chat, msg_id, "نژادت ثبت شد! کلاس رو انتخاب کن:", kb(rows))
        return

    if data.startswith("class:"):
        ans_cb(cb["id"])
        if not st:
            return
        cls = data.split(":", 1)[1]
        st["cls"] = cls
        st["step"] = "weapon"
        from game.rules import CLASSES, WEAPONS
        rows = [[("%s %s (%s)" % (WEAPONS[k]["emoji"], WEAPONS[k]["fa"], WEAPONS[k]["dmg"]), "weapon:" + k)]
                for k in CLASSES[cls]["weapons"]]
        edit(chat, msg_id, "کلاس ثبت شد! سلاحت رو انتخاب کن:", kb(rows))
        return

    if data.startswith("weapon:"):
        ans_cb(cb["id"])
        if not st:
            return
        weapon = data.split(":", 1)[1]
        from game.models import Character
        s = room_of(store, chat)
        if not s:
            edit(chat, msg_id, "اتاق پیدا نشد. /join")
            CHAR_STATE.pop(chat, None)
            return
        ch = Character(name=st.get("name", "بی‌نام"), race=st["race"], cls=st["cls"], weapon=weapon)
        s.players[str(uid)]["char"] = ch
        if s.state == "lobby":
            s.state = "playing"
        s.add_log("سیستم", "%s به گروه پیوست" % ch.name)
        store.save(s)
        CHAR_STATE.pop(chat, None)
        edit(chat, msg_id, "🎉 کاراکتر ساخته شد!\n\n" + ch.sheet_text() + "\n\n🐉 میزبان می‌تونه /scenario بزنه!")
        return


# ==================== حلقه ربات ====================

def bot_loop(store):
    offset = 0
    last_net_log = 0.0
    log("🚀 ربات آنلاین — منتظر پیام‌ها...")
    while not stopped():
        try:
            data = tg("getUpdates", {"offset": offset, "timeout": 10, "allowed_updates": ["message", "callback_query"]}, timeout=20)
            if not data or not data.get("ok"):
                time.sleep(3)
                continue
            for u in data.get("result", []):
                offset = max(offset, u["update_id"] + 1)
                try:
                    if "message" in u:
                        on_message(store, u["message"])
                    elif "callback_query" in u:
                        on_callback(store, u["callback_query"])
                except Exception as e:
                    log("خطای پردازش آپدیت: %s" % e)
        except Exception as e:
            now = time.time()
            if now - last_net_log > 30:
                last_net_log = now
                log("⚠️ اتصال به تلگرام برقرار نشد (%s) — وای‌فای/دیتا گوشی را بررسی کن؛ اگر شبکه‌ات تلگرام را مسدود می‌کند ابزار عبور را روشن کن" % e)
            time.sleep(5)
    log("حلقه ربات متوقف شد")


# ==================== سرور مینی‌گیم ====================

def validate_init_data(init_data, bot_token):
    # نکته مهم: هش تلگرام روی مقادیر «خام» (درصد-کد شده) محاسبه می‌شود.
    # parse_qsl مقادیر را decode می‌کند و برای نام فارسی/کاراکترهای خاص هش را خراب می‌کند.
    try:
        if not init_data or not bot_token:
            return None
        received = None
        fields = {}
        for part in init_data.split("&"):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            if k == "hash":
                received = v
            else:
                fields[k] = v
        if not received:
            return None
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        dcs = "\n".join("%s=%s" % (k, fields[k]) for k in sorted(fields))
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            return None
        return json.loads(urllib.parse.unquote(fields.get("user", "{}")))
    except Exception:
        return None


class ApiHandler(BaseHTTPRequestHandler):
    store = None
    narrator = None
    dev = False

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _user(self):
        init = self.headers.get("X-Init-Data") or ""
        if init:
            u = validate_init_data(init, os.environ.get("BOT_TOKEN", ""))
            if u:
                return u
        if self.dev:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            uid = (q.get("user_id") or [None])[0]
            if uid:
                return {"id": int(uid), "first_name": (q.get("user_name") or ["ماجراجوی آزمایشی"])[0]}
        return None

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(n).decode()) if n else {}
        except Exception:
            return {}

    def _room(self):
        body = self._body()
        code = (body.get("room") or body.get("code") or "").strip().upper()
        if not code:
            return None
        return self.store.find_by_code(code)

    def _save(self, s):
        self.store.save(s)

    # ---------- متادیتا ----------
    def _api_meta(self):
        from game.rules import RACES, CLASSES, WEAPONS, SPELLS, MONSTERS
        return {
            "races": [{"key": k, "fa": v["fa"], "emoji": v["emoji"],
                       "bonus": ", ".join("%+d" % b for b in v["bonus"].values())} for k, v in RACES.items()],
            "classes": [{"key": k, "fa": v["fa"], "emoji": v["emoji"], "hit_die": v["hit_die"],
                         "weapons": v["weapons"]} for k, v in CLASSES.items()],
            "weapons": {k: [{"key": w, "fa": WEAPONS[w]["fa"], "emoji": WEAPONS[w]["emoji"],
                             "dmg": WEAPONS[w]["dmg"]} for w in v["weapons"]] for k, v in CLASSES.items()},
            "spells": [{"key": k, "fa": v["fa"], "emoji": v["emoji"], "dmg": v["dmg"], "kind": v["kind"]}
                       for k, v in SPELLS.items()],
            "monsters": [{"key": k, "fa": v["fa"], "emoji": v["emoji"]} for k, v in MONSTERS.items()],
        }

    # ---------- وضعیت ----------
    def _sheet(self, ch):
        from game.rules import RACES, CLASSES, WEAPONS, ABILITIES, ABILITY_FA
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
            "abilities": [{"key": a, "fa": ABILITY_FA[a], "value": ch.abilities[a], "mod": ch.stat_mod(a)}
                          for a in ABILITIES],
            "features": ch.features(),
        }

    def _combat(self, s, uid):
        from game.rules import RACES
        c = s.combat
        if not c or not c.get("participants"):
            return None
        parts = c["participants"]
        idx = min(c.get("turn", 0), len(parts) - 1)
        out = []
        for i, p in enumerate(parts):
            out.append({
                "name": p["name"], "kind": p["kind"], "hp": p["hp"],
                "max_hp": p.get("max_hp", p["hp"]), "ac": p["ac"], "alive": p["alive"],
                "init": p["init"], "turn": i == idx,
                "is_player": p["kind"] == "player",
                "is_me": p["kind"] == "player" and uid is not None and p.get("uid") == str(uid),
            })
        cur = parts[idx]
        return {
            "round": c.get("round", 1),
            "current": cur["name"],
            "current_is_player": cur["kind"] == "player",
            "is_my_turn": cur["kind"] == "player" and uid is not None and cur.get("uid") == str(uid),
            "participants": out,
        }

    def _state(self, s, user):
        from game.rules import RACES, CLASSES
        uid = str(user.get("id"))
        players = []
        for u2, p in s.players.items():
            ch = p["char"]
            players.append({
                "uid": int(u2), "name": p["user"], "is_dm": int(u2) == s.dm_id,
                "char": None if not ch else {
                    "name": ch.name, "race": RACES[ch.race]["fa"], "cls": CLASSES[ch.cls]["fa"],
                    "emoji": CLASSES[ch.cls]["emoji"], "level": ch.level,
                    "hp": ch.hp, "max_hp": ch.max_hp, "ac": ch.ac, "alive": ch.hp > 0,
                },
            })
        my_sheet = self._sheet(s.get_char(user.get("id"))) if uid in s.players else None
        return {
            "room": {
                "code": s.code, "name": s.name, "dm_name": s.dm_name, "dm_uid": s.dm_id,
                "state": s.state, "max_players": 8, "count": len(s.players),
                "char_count": s.char_count(), "is_member": uid in s.players,
                "is_dm": uid in s.players and s.dm_id == user.get("id"),
                "players": players,
            },
            "me": {"uid": user.get("id"), "name": user.get("first_name", ""),
                   "is_member": uid in s.players,
                   "has_char": uid in s.players and s.get_char(user.get("id")) is not None,
                   "char": my_sheet},
            "scenario": s.scenario,
            "log": s.log[-40:],
            "combat": self._combat(s, user.get("id")),
        }

    # ---------- روتر ----------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            try:
                with open(os.path.join(FILES_DIR, "web", "index.html"), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self._json(500, {"ok": False, "error": "index not found"})
            return
        if path == "/api/meta":
            self._json(200, {"ok": True, "data": self._api_meta()})
            return
        if path == "/api/room/state":
            user = self._user()
            if not user:
                self._json(401, {"ok": False, "error": "شناسایی نشدی"})
                return
            body = self._body()
            code = (body.get("room") or urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query).get("room", [""])[0]).strip().upper()
            s = self.store.find_by_code(code) if code else None
            if not s:
                self._json(404, {"ok": False, "error": "اتاق پیدا نشد"})
                return
            self._json(200, {"ok": True, "data": self._state(s, user)})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        user = self._user()
        if not user:
            self._json(401, {"ok": False, "error": "شناسایی نشدی — از داخل تلگرام باز کن."})
            return
        body = self._body()
        code = (body.get("room") or body.get("code") or "").strip().upper()

        if path == "/api/room/create":
            from game.models import Session
            name = (body.get("name") or "ماجرای جدید").strip()[:40]
            s = Session(chat_id=random.randint(10**9, 2 * 10**9), name=name,
                        dm_id=user["id"], dm_name=user.get("first_name", "میزبان"))
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"code": s.code, "state": self._state(s, user)}})
            return

        if path == "/api/room/join":
            s = self.store.find_by_code(code) if code else None
            if not s:
                self._json(404, {"ok": False, "error": "اتاق با این کد پیدا نشد!"})
                return
            if str(user["id"]) not in s.players:
                res = s.add_player(user["id"], user.get("first_name", "ماجراجو"))
                if res == "full":
                    self._json(400, {"ok": False, "error": "اتاق پر است! (۸ نفر)"})
                    return
                s.add_log("سیستم", "%s به اتاق پیوست" % user.get("first_name", "ماجراجو"))
                self.store.save(s)
            self._json(200, {"ok": True, "data": {"code": s.code, "state": self._state(s, user)}})
            return

        s = self.store.find_by_code(code) if code else None
        if not s:
            self._json(404, {"ok": False, "error": "اتاق پیدا نشد!"})
            return
        if str(user["id"]) not in s.players and path not in ("/api/roll",):
            self._json(403, {"ok": False, "error": "تو عضو این اتاق نیستی."})
            return

        if path == "/api/char/create":
            from game.models import Character
            from game.rules import RACES, CLASSES
            if s.has_char(user["id"]):
                self._json(400, {"ok": False, "error": "قبلاً کاراکتر داری."})
                return
            name = (body.get("name") or "بی‌نام").strip()[:30]
            race, cls, weapon = body.get("race", ""), body.get("cls", ""), body.get("weapon", "")
            if race not in RACES or cls not in CLASSES or weapon not in CLASSES[cls]["weapons"]:
                self._json(400, {"ok": False, "error": "مقادیر نامعتبر."})
                return
            ch = Character(name=name, race=race, cls=cls, weapon=weapon)
            s.players[str(user["id"])]["char"] = ch
            if s.state == "lobby":
                s.state = "playing"
            s.add_log("سیستم", "%s (%s %s) به گروه پیوست" % (ch.name, RACES[race]["fa"], CLASSES[cls]["fa"]))
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"state": self._state(s, user)}})
            return

        if path == "/api/char/levelup":
            ch = s.get_char(user["id"])
            if not ch or not ch.can_level_up():
                self._json(400, {"ok": False, "error": "XP کافی نداری."})
                return
            info = ch.level_up()
            s.add_log("سیستم", "%s به سطح %d رسید!" % (ch.name, info["new"]))
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"state": self._state(s, user), "level": info["new"]}})
            return

        if path == "/api/scenario":
            if s.dm_id != user["id"]:
                self._json(403, {"ok": False, "error": "فقط میزبان."})
                return
            if s.char_count() < 1:
                self._json(400, {"ok": False, "error": "اول یک کاراکتر بسازید."})
                return
            scenario = self.narrator.scenario(s, (body.get("request") or "").strip())
            s.scenario = scenario
            s.state = "playing"
            s.add_log("DM", "سناریو ساخته شد: %s" % scenario.get("title"))
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"state": self._state(s, user)}})
            return

        if path == "/api/story":
            action = (body.get("action") or "").strip() or "ادامه بده"
            text = self.narrator.narrate(s, action)
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"text": text, "state": self._state(s, user)}})
            return

        if path == "/api/where":
            text = self.narrator.recap(s)
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"text": text, "state": self._state(s, user)}})
            return

        if path == "/api/roll":
            from game.dice import roll_expression, roll_advantage, roll_disadvantage, DiceError
            expr = (body.get("expr") or "").strip()
            try:
                low = expr.lower()
                if low in ("adv", "advantage"):
                    r = roll_advantage()
                elif low in ("dis", "disadvantage"):
                    r = roll_disadvantage()
                else:
                    r = roll_expression(expr)
            except DiceError as e:
                self._json(400, {"ok": False, "error": str(e)})
                return
            if str(user["id"]) in s.players:
                s.add_log(user.get("first_name", "بازیکن"), "تاس %s: %s" % (expr, r["total"]))
                self.store.save(s)
            crit = ""
            if low == "d20" or low.endswith("d20"):
                crit = " 🔥 بحرانی!" if r["total"] == 20 else (" 💔 شکست!" if r["total"] == 1 else "")
            self._json(200, {"ok": True, "data": {"result": r["total"], "breakdown": r["breakdown"], "crit": crit}})
            return

        if path == "/api/combat/start":
            from game.combat import start_combat, advance
            if s.dm_id != user["id"]:
                self._json(403, {"ok": False, "error": "فقط میزبان."})
                return
            if s.combat:
                self._json(400, {"ok": False, "error": "نبرد در جریان است."})
                return
            msgs = [start_combat(s)]
            if s.combat and s.combat["participants"][0]["kind"] == "monster":
                msgs.append(advance(s))
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(s, user)}})
            return

        if path in ("/api/combat/attack", "/api/combat/cast", "/api/combat/skip"):
            from game.combat import attack, cast, advance
            if not s.combat:
                self._json(400, {"ok": False, "error": "نبردی نیست."})
                return
            msgs = []
            if path == "/api/combat/attack":
                msgs.append(attack(s, user["id"], body.get("target", "")))
            elif path == "/api/combat/cast":
                msgs.append(cast(s, user["id"], body.get("spell", ""), body.get("target", "")))
            else:
                msgs.append(advance(s))
            if s.combat:
                msgs.append(advance(s))
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(s, user)}})
            return

        if path == "/api/combat/end":
            from game.combat import end_combat
            if s.dm_id != user["id"]:
                self._json(403, {"ok": False, "error": "فقط میزبان."})
                return
            if not s.combat:
                self._json(400, {"ok": False, "error": "نبردی نیست."})
                return
            msgs = [end_combat(s)]
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(s, user)}})
            return

        self._json(404, {"ok": False, "error": "not found"})


def http_server_loop(store, narrator, port):
    ApiHandler.store = store
    ApiHandler.narrator = narrator
    ApiHandler.dev = os.environ.get("WEBAPP_DEV", "0") == "1"
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), ApiHandler)
    except OSError as e:
        if getattr(e, "errno", None) == 98:
            log("⚠️ پورت %d اشغال است — نسخه دیگری از ربات هنوز فعال است. دکمه «توقف» را بزن، چند ثانیه صبر کن و دوباره شروع کن" % port)
        else:
            log("خطای سرور وب: %s" % e)
        return
    log("🌐 مینی‌گیم روی پورت %d فعال شد" % port)

    def serve():
        try:
            srv.serve_forever(poll_interval=0.5)
        except Exception:
            pass

    threading.Thread(target=serve, daemon=True).start()
    while not stopped():
        time.sleep(1)
    try:
        srv.shutdown()
        srv.server_close()
    except Exception:
        pass
    log("🌐 وب‌سرور مینی‌گیم متوقف شد")


# ==================== تونل امن ====================

# روی اندروید مدرن (targetSdk 29+) اجرای فایل از پوشه‌ی داده اپ ممنوع است (W^X)؛
# راه‌حل: cloudflared به‌صورت libcloudflared.so داخل APK قرار می‌گیرد و از
# nativeLibraryDir (قابل اجرا) اجرا می‌شود. DNS هم از پایتون گرفته می‌شود چون
# باینری Go روی اندروید /etc/resolv.conf ندارد.

CF_URLS = {
    "aarch64": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64",
    "armv7l": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm",
    "x86_64": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
}


def ensure_cloudflared(native_dir=None):
    # ۱) باینری داخل APK — از پوشه کتابخانه‌های native قابل اجراست
    if native_dir:
        p = os.path.join(native_dir, "libcloudflared.so")
        if os.path.exists(p):
            try:
                os.chmod(p, 0o755)
            except Exception:
                pass
            return p
    # ۲) روش قدیمی (فقط برای بیلدهای بدون باینری داخل APK)
    p = os.path.join(FILES_DIR, "cloudflared")
    if os.path.exists(p):
        return p
    log("📦 دانلود cloudflared (اولین بار)...")
    try:
        url = CF_URLS.get(getattr(os.uname(), "machine", ""))
        if not url:
            return None
        urllib.request.urlretrieve(url, p + ".tmp")
        os.chmod(p + ".tmp", 0o755)
        os.rename(p + ".tmp", p)
        return p
    except Exception as e:
        log("دانلود cloudflared ناموفق: %s" % e)
        return None


def register_quick_tunnel():
    req = urllib.request.Request(
        "https://api.trycloudflare.com/tunnel",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DND-Bot-Android/2.3",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    res = d.get("result") or {}
    if not (res.get("hostname") and res.get("id") and res.get("secret")):
        raise RuntimeError("پاسخ نامعتبر از trycloudflare: %s" % str(d)[:200])
    return res


def resolve_edge_ips():
    ips = []
    for host in ("region1.v2.argotunnel.com", "region2.v2.argotunnel.com"):
        try:
            for a in socket.getaddrinfo(host, 7844, socket.AF_INET):
                ip = a[4][0]
                if ip not in ips:
                    ips.append(ip)
        except Exception:
            pass
    return ips


def tunnel_loop(port, native_dir=None):
    while not stopped():
        proc = None
        log("🌐 شروع تونل امن مینی‌گیم...")
        try:
            info = register_quick_tunnel()
            url = "https://" + info["hostname"]
            creds_path = os.path.join(FILES_DIR, "cf_creds.json")
            cfg_path = os.path.join(FILES_DIR, "cf_config.yml")
            with open(creds_path, "w", encoding="utf-8") as f:
                json.dump({"AccountTag": info["account_tag"],
                           "TunnelID": info["id"],
                           "TunnelSecret": info["secret"]}, f)
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(
                    "tunnel: %s\n"
                    "credentials-file: %s\n"
                    "protocol: http2\n"
                    "no-autoupdate: true\n"
                    "ingress:\n"
                    "  - hostname: %s\n"
                    "    service: http://127.0.0.1:%d\n"
                    "  - service: http_status:404\n"
                    % (info["id"], creds_path, info["hostname"], port)
                )
            edges = resolve_edge_ips()
            if not edges:
                log("⚠️ DNS در دسترس نیست — اینترنت گوشی را بررسی کن")
                time.sleep(20)
                continue
            cf = ensure_cloudflared(native_dir)
            if not cf:
                time.sleep(30)
                continue
            cmd = [cf, "tunnel", "--config", cfg_path,
                   "--edge-ip-version", "4", "--no-autoupdate"]
            for ip in edges[:4]:
                cmd += ["--edge", "%s:7844" % ip]
            cmd += ["run", info["id"]]
            cf_log = open(os.path.join(FILES_DIR, "cf.log"), "ab")
            proc = subprocess.Popen(
                cmd, stdout=cf_log, stderr=subprocess.STDOUT,
                env={"HOME": FILES_DIR, "PATH": "/system/bin:/system/xbin"})
            with open(os.path.join(FILES_DIR, "tunnel_url.txt"), "w", encoding="utf-8") as f:
                f.write(url)
            log("✅ آدرس مینی‌گیم: " + url)
            while not stopped() and proc.poll() is None:
                time.sleep(5)
            if not stopped():
                log("⚠️ تونل قطع شد — اتصال مجدد...")
        except Exception as e:
            log("خطای تونل: %s" % e)
        finally:
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        time.sleep(15)


# ==================== نقطه ورود ====================

def main(files_dir, native_lib_dir=None):
    global FILES_DIR, STOP_FILE
    FILES_DIR = files_dir
    STOP_FILE = os.path.join(files_dir, "stop")
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)

    try:
        cfg = json.load(open(os.path.join(files_dir, "bot_config.json"), encoding="utf-8"))
    except Exception:
        cfg = {}

    os.environ["BOT_TOKEN"] = cfg.get("BOT_TOKEN", "")
    os.environ["AI_PROVIDER"] = cfg.get("AI_PROVIDER", "mistral")
    os.environ["MISTRAL_API_KEY"] = cfg.get("AI_KEY", "")
    os.environ["MISTRAL_MODEL"] = cfg.get("AI_MODEL", "mistral-small-latest")
    os.environ["PORT"] = str(cfg.get("PORT", 8080))
    os.environ["DB_PATH"] = os.path.join(files_dir, "dnd.db")
    os.environ["WEBAPP_DEV"] = "1" if cfg.get("DEV") else "0"

    import config
    if not config.BOT_TOKEN:
        log("❌ توکن ربات خالی است — در اپ تنظیم کن و دوباره شروع کن")
        return

    store = get_store()
    narrator = get_narrator()
    if not narrator.available:
        log("⚠️ کلید AI خالی است — حالت آفلاین (روایت قالب‌بندی‌شده)")

    # اگر نسخه Termux/هاست قبلاً روی این بات webhook ست کرده باشد،
    # حالت polling با خطای 409 Conflict مواجه می‌شود — آن را پاک می‌کنیم
    try:
        info = tg("getWebhookInfo", timeout=15)
        wh = (info or {}).get("result") or {}
        if wh.get("url"):
            log("🔔 وب‌هوک قدیمی شناسایی شد — در حال حذف...")
            tg("deleteWebhook", {"drop_pending_updates": True}, timeout=15)
            log("✅ وب‌هوک حذف شد — حالت polling فعال است")
        else:
            log("✅ حالت polling آماده است")
    except Exception as e:
        log("بررسی وب‌هوک ناموفق: %s" % e)

    port = int(os.environ.get("PORT", "8080"))
    threading.Thread(target=tunnel_loop, args=(port, native_lib_dir), daemon=True).start()
    threading.Thread(target=http_server_loop, args=(store, narrator, port), daemon=True).start()

    bot_loop(store)
    log("🛑 سرور متوقف شد")
