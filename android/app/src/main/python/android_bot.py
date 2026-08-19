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

# پایداری شبکه: اجبار IPv4 (الان مشکل اصلی timeout IPv6 است)
_orig_getaddrinfo = socket.getaddrinfo

def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        if host == "api.telegram.org" and family == 0:
            family = socket.AF_INET
    except Exception:
        pass
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _patched_getaddrinfo

# یک opener سراسری با SSL پیش‌فرض (timeout روی باز کردن درخواست تنظیم می‌شود)
import ssl as _ssl
_ssl_ctx = _ssl.create_default_context()
try:
    _tg_opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ssl_ctx)
    )
except Exception:
    _tg_opener = urllib.request.build_opener()


def tg(method, payload=None, timeout=25, retries=2):
    """درخواست به Bot API با retry، تایم‌اوت کوتاه و IPv4-only."""
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        return None
    url = "https://api.telegram.org/bot%s/%s" % (token, method)
    data = json.dumps(payload).encode() if payload is not None else None
    last_err = None
    for attempt in range(retries + 1):
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "DND-Bot-Android/2.42",
                "Connection": "close",
            }
            req = urllib.request.Request(url, data=data, headers=headers)
            with _tg_opener.open(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except Exception:
                last_err = "invalid json"
                continue
        except urllib.error.HTTPError as e:
            if e.code == 409:
                return None
            if e.code in (500, 502, 503, 504, 429):
                last_err = "HTTP %s" % e.code
                time.sleep(1 + attempt * 2)
                continue
            return None
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 + attempt * 2)
                continue
            # فقط در صورت تکرار مداوم لاگ کن
            return None
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
            from game.nlp import parse_action
            s = room_of(store, chat)
            ch = user_char(s, uid) if s else None
            in_combat = bool(s and s.combat)
            mobs = [p["name"] for p in (s.combat or {}).get("participants", [])
                    if p.get("kind") == "monster" and p.get("alive")] if in_combat else []
            act = parse_action(text, in_combat=in_combat, has_char=bool(ch),
                                valid_monsters=mobs,
                                is_dm=(s and is_dm(s, uid)))
            a = act.get("action")
            if a in ("attack", "cast", "dodge", "skip", "deathsave",
                     "potion", "roll", "rest", "torch", "look", "sheet",
                     "party", "scenario", "combat", "help", "wait", "talk",
                     "narrate", "shop", "buy", "sell", "campaign"):
                # اکشن‌های طبیعی اینجا پردازش می‌شوند
                if a == "attack" and in_combat:
                    tgt = act.get("target") or (mobs[0] if mobs else "")
                    from game.combat import attack, advance
                    send(chat, attack(s, uid, tgt))
                    store.save(s)
                    t = advance(s)
                    store.save(s)
                    if t: send(chat, t)
                    return
                if a == "cast" and in_combat:
                    from game.combat import cast, advance
                    send(chat, cast(s, uid, act.get("spell","firebolt"), act.get("target","")))
                    store.save(s)
                    t = advance(s)
                    store.save(s)
                    if t: send(chat, t)
                    return
                if a == "dodge" and in_combat:
                    from game.combat import dodge, advance
                    send(chat, dodge(s, uid))
                    store.save(s)
                    t = advance(s); store.save(s)
                    if t: send(chat, t)
                    return
                if a == "skip" and in_combat:
                    from game.combat import advance
                    send(chat, advance(s)); store.save(s); return
                if a == "deathsave" and in_combat:
                    from game.adventure import death_save
                    from game.combat import advance
                    send(chat, death_save(s, uid)); store.save(s)
                    if s.combat:
                        t = advance(s); store.save(s)
                        if t: send(chat, t)
                    return
                if a == "potion":
                    from game.shop import use_item
                    send(chat, use_item(ch, "potion")); store.save(s); return
                if a == "roll":
                    from game.dice import roll_expression
                    r = roll_expression(act.get("expr","d20"))
                    send(chat, "🎲 %s: **%s** (%s)" % (act.get("expr"), r["total"], r["breakdown"]))
                    return
                if a == "rest":
                    from game.adventure import rest
                    send(chat, rest(s, uid, act.get("kind","short"))); store.save(s); return
                if a == "torch":
                    from game.world import try_environment_action
                    r = try_environment_action(s, ch, "مشعل روشن می‌کنم")
                    if r: send(chat, r); store.save(s); return
                if a == "look":
                    if in_combat:
                        from game.combat import order_text
                        send(chat, order_text(s))
                    else:
                        cmd_where(store, chat, uid, uname, [])
                    return
                if a == "sheet":
                    cmd_sheet(store, chat, uid, uname, []); return
                if a == "party":
                    cmd_party(store, chat, uid, uname, []); return
                if a == "scenario" and is_dm(s, uid):
                    cmd_scenario(store, chat, uid, uname, []); return
                if a == "combat" and is_dm(s, uid):
                    cmd_combat(store, chat, uid, uname, []); return
                if a == "help":
                    send(chat, HELP); return
                if a == "wait":
                    send(chat, "⏳ چند لحظه صبر می‌کنی..."); return
                if a == "shop":
                    from game.shop import shop_text
                    send(chat, shop_text(s)); return
                if a == "buy":
                    from game.shop import buy
                    if not act.get("item"):
                        send(chat, "چی بخرم؟"); return
                    send(chat, buy(ch, act["item"])); store.save(s); return
                if a == "sell":
                    from game.shop import sell
                    if not act.get("item"):
                        send(chat, "چی بفروشم؟"); return
                    send(chat, sell(ch, act["item"])); store.save(s); return
                if a == "campaign" and is_dm(s, uid):
                    from game.campaign import make_campaign, start_chapter
                    if not s.campaign:
                        s.campaign = make_campaign()
                    sc = start_chapter(s.campaign, s, get_narrator())
                    if sc:
                        s.scenario = sc
                        store.save(s)
                        send(chat, "📖 %s\n\n%s\n_%s_" % (sc.get("chapter_title",""), sc.get("title"), sc.get("hook")))
                    return
                # talk / narrate
                cmd_story(store, chat, uid, uname, [text])
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
    fail_streak = 0
    last_net_log = 0.0
    log("🚀 ربات آنلاین — منتظر پیام‌ها (IPv4-only)...")
    while not stopped():
        try:
            # long-poll تلگرام: timeout=15 روی سرور تلگرام، سوکت ۲۵ ثانیه می‌ماند
            data = tg("getUpdates", {"offset": offset, "timeout": 15,
                                     "allowed_updates": ["message", "callback_query"]},
                     timeout=25)
            if not data or not data.get("ok"):
                fail_streak += 1
                # sleep نمایی کوتاه (بدون لاگ اسپم)
                time.sleep(min(1 + fail_streak * 0.5, 8))
                continue
            # موفق — شمارنده صفر شود
            if fail_streak > 0:
                if fail_streak >= 3:
                    log("✅ اتصال به تلگرام دوباره برقرار شد (بعد از %d خطا)" % fail_streak)
                fail_streak = 0
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
            fail_streak += 1
            now = time.time()
            wait = min(2 + fail_streak, 20)
            # فقط هر ۶۰ ثانیه یک‌بار لاگ قطعی بده
            if (fail_streak == 1) or (now - last_net_log > 90):
                last_net_log = now
                log("⚠️ اتصال به تلگرام نامطمئن (خطای %dم: %s) — در حال تلاش مجدد..."
                    % (fail_streak, str(e)[:100]))
            time.sleep(wait)
    log("حلقه ربات متوقف شد")


# ==================== سرور مینی‌گیم ====================

def validate_init_data(init_data, bot_token):
    # مطابق مستندات رسمی تلگرام: parse_qsl مقادیر را URL-decode می‌کند
    # (این رفتار صحیح برای محاسبه هش است).
    try:
        if not init_data or not bot_token:
            return None
        fields = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received = fields.pop("hash", None)
        if not received:
            return None
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        dcs = "\n".join("%s=%s" % (k, fields[k]) for k in sorted(fields))
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            return None
        user_str = fields.get("user", "{}")
        try:
            return json.loads(user_str)
        except Exception:
            return {"id": 0, "first_name": "بازیکن"}
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
        init = (self.headers.get("X-Init-Data")
                or urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(
                    "init_data", [None])[0]
                or urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(
                    "tgWebAppData", [None])[0]
                or "")
        if init:
            u = validate_init_data(init, os.environ.get("BOT_TOKEN", ""))
            if u:
                return u
        # init_data در body (برای iframe/webview خاص)
        try:
            body_init = (self._body() or {}).get("init_data", "")
            if body_init:
                u = validate_init_data(body_init, os.environ.get("BOT_TOKEN", ""))
                if u:
                    return u
        except Exception:
            pass
        if self.dev:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            uid_raw = (q.get("user_id") or [None])[0]
            try:
                uid = int(uid_raw) if uid_raw and uid_raw != "None" else 900000001
            except (TypeError, ValueError):
                uid = 900000001
            return {"id": uid, "first_name": (q.get("user_name") or ["ماجراجوی آزمایشی"])[0]}
        return None

    _body_cache = None

    def _body(self):
        if self._body_cache is not None:
            return self._body_cache
        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n else b""
            self._body_cache = json.loads(raw.decode()) if raw else {}
        except Exception:
            self._body_cache = {}
        return self._body_cache

    def _reset_body_cache(self):
        # برای هر درخواست جدید کش را خالی کن (BaseHTTPRequestHandler یک‌بارمصرف است
        # ولی محض اطمینان فراخوانی می‌شود)
        self._body_cache = None

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
            "spells": [{"key": k, "fa": v["fa"], "emoji": v.get("emoji", "✨"),
                        "dmg": v.get("dmg", v.get("heal", "")), "kind": v.get("kind", "utility"),
                        "level": v.get("level", 0), "action": v.get("action", "main")}
                       for k, v in SPELLS.items()],
            "monsters": [{"key": k, "fa": v["fa"], "emoji": v["emoji"]} for k, v in MONSTERS.items()],
        }

    # ---------- وضعیت ----------
    def _sheet(self, ch):
        from game.rules import RACES, CLASSES, WEAPONS, ABILITIES, ABILITY_FA
        if not ch:
            return None
        try:
            profs = list(ch.proficiencies)
        except Exception:
            profs = []
        try:
            inv = dict(ch.inventory)
        except Exception:
            inv = {}
        try:
            conds = list(ch.conditions)
        except Exception:
            conds = []
        try:
            feats = ch.features()
        except Exception:
            feats = []
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
            "weapon_dmg": WEAPONS[ch.weapon]["dmg"], "attack_bonus": ch.attack_bonus(),
            "abilities": [{"key": a, "fa": ABILITY_FA[a], "value": ch.abilities[a], "mod": ch.stat_mod(a)}
                          for a in ABILITIES],
            "features": feats,
            "proficiencies": profs,
            "inventory": inv,
            "conditions": conds,
            "inspiration": bool(getattr(ch, "inspiration", False)),
        }

    def _combat(self, s, uid):
        c = s.combat
        if not c or not c.get("participants"):
            return None
        parts = c["participants"]
        idx = min(c.get("turn", 0), len(parts) - 1)
        out = []
        for i, p in enumerate(parts):
            is_dead = bool(p.get("dead"))
            is_downed = bool(p.get("downed"))
            hp = p.get("hp", 0)
            max_hp = p.get("max_hp")
            if max_hp is None:
                max_hp = max(hp, 1)
                if not p.get("_max_hp_cached"):
                    p["_max_hp_cached"] = max_hp
                else:
                    max_hp = p["_max_hp_cached"]
            alive = (not is_dead) and p.get("alive", True) and hp > 0
            out.append({
                "name": p["name"], "kind": p["kind"], "hp": hp,
                "max_hp": max_hp, "ac": p.get("ac", 10),
                "alive": alive, "downed": is_downed, "dead": is_dead,
                "init": p.get("init", 0), "turn": i == idx,
                "acted": bool(p.get("acted", False)),
                "bonus_acted": bool(p.get("bonus_acted", False)),
                "uid": str(p.get("uid", "")) if p.get("uid") is not None else None,
                "distance": p.get("distance", 0),
                "height": p.get("height", 0),
                "cover": p.get("cover", "none"),
                "surface": p.get("surface", "none"),
                "is_boss": bool(p.get("is_boss")),
                "emoji": p.get("emoji", "👹" if p["kind"]=="monster" else "🧙"),
                "is_player": p["kind"] == "player",
                "is_me": p["kind"] == "player" and uid is not None and p.get("uid") == str(uid),
                "conditions": list(p.get("conditions", [])),
            })
        cur = parts[idx]
        return {
            "round": c.get("round", 1),
            "turn": idx,
            "current": cur["name"],
            "current_uid": str(cur.get("uid", "")) if cur.get("uid") is not None else None,
            "current_is_player": cur["kind"] == "player",
            "is_my_turn": cur["kind"] == "player" and uid is not None and cur.get("uid") == str(uid),
            "participants": out,
            "in_progress": True,
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
            from game.combat import start_combat, advance, run_initial_monsters
            if s.dm_id != user["id"]:
                self._json(403, {"ok": False, "error": "فقط میزبان."})
                return
            if s.combat:
                self._json(400, {"ok": False, "error": "نبرد در جریان است."})
                return
            msgs = [start_combat(s)]
            im = run_initial_monsters(s)
            if im:
                msgs.append(im)
            self.store.save(s)
            self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(s, user)}})
            return

        if path in ("/api/combat/attack", "/api/combat/cast", "/api/combat/skip"):
            from game.combat import attack, cast, advance
            if not s.combat:
                self._json(400, {"ok": False, "error": "نبردی نیست."})
                return
            def _s2(v, default=""):
                try: return str(v).strip() if v is not None else default
                except Exception: return default
            msgs = []
            try:
                if path == "/api/combat/attack":
                    msgs.append(attack(s, user["id"], _s2(body.get("target"))))
                elif path == "/api/combat/cast":
                    msgs.append(cast(s, user["id"], _s2(body.get("spell")), _s2(body.get("target"))))
                else:
                    msgs.append(advance(s))
                    self.store.save(s)
                    self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(s, user)}})
                    return
            except Exception as e:
                self._json(400, {"ok": False, "error": str(e)[:120]})
                return
            # بعد از اکشن اصلی (attack/cast) نوبت را جلو ببر — فقط اگر نبرد هنوز جاری است
            if s.combat:
                nxt = advance(s)
                if nxt:
                    msgs.append(nxt)
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
    """راه‌اندازی سرور وب مینی‌گیم — اول Flask (اصلی) سعی می‌شود،
    در صورت خطا (pip چاکوپی، missing dep و...) به ApiHandler استاندارد برمی‌گردد."""
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)

    # مطمئن شویم که پوشه web در دسترس است (فایل‌های استاتیک index.html/icon.png)
    # چاکوپی هم فایل‌های assets را به assets می‌ریزد هم پایتون را به python —
    # هر دوی این‌ها در همان _here هستند.
    web_dir = os.path.join(_here, "web")
    # در چاکوپی، assets/ در همان ریشه‌ی _here (python/) اکستراکت می‌شود
    # و ممکن است پوشه web کنار کد نباشد اما در assets/ قابل دسترسی باشد.
    candidates = [
        web_dir,
        os.path.join(os.path.dirname(_here), "assets", "web"),
        os.path.join(os.path.dirname(_here), "..", "assets", "web"),
        os.path.join(FILES_DIR, "web"),
    ]
    chosen_web = None
    for cand in candidates:
        try:
            if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, "index.html")):
                chosen_web = os.path.normpath(cand)
                break
        except Exception:
            pass
    if chosen_web is None:
        chosen_web = web_dir
    web_dir = chosen_web
    log("📂 پوشه web مینی‌گیم: %s (exists=%s)" % (web_dir, os.path.isdir(web_dir)))

    use_flask = False
    srv = None
    try:
        from webapp import build_app
        from werkzeug.serving import make_server
        app = build_app(store, narrator)
        srv = make_server("0.0.0.0", port, app, threaded=True)
        use_flask = True
        log("🌐 مینی‌گیم روی پورت %d فعال شد (Flask)" % port)
    except Exception as e:
        log("⚠️ Flask آماده نبود (%s) — استفاده از سرور استاندارد کتابخانه" % e)
        use_flask = False

    if use_flask:
        def serve():
            try:
                srv.serve_forever()
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
        return

    # ---------- Fallback: سرور ساده استاندارد (اگر Flask در دسترس نبود) ----------
    # ApiHandler ای که در بالای همین فایل تعریف شده، برای ۳ GET و ۷ POST کافی است،
    # اما برای اینکه مینی‌گیم جدید (که endpointهای move/look/check/rest/inventory/...
    # می‌خواهد) هم کار کند، همین‌جا ورک‌های لازم را اضافه می‌کنیم.
    import mimetypes

    dev_fallback = (os.environ.get("WEBAPP_DEV", "0") == "1")

    # در بدنه کلاس پایتون، «store = store» سمت راست را در اسکوپ خود کلاس
    # جست‌وجو می‌کند و متغیر enclosing را نمی‌بیند. از alias محلی استفاده می‌کنیم.
    _s = store
    _n = narrator
    _d = dev_fallback
    _wd = web_dir

    class FullApiHandler(ApiHandler):
        """ApiHandler کامل‌تر: استاتیک + endpointهای جدید مینی‌گیم."""
        store = _s
        narrator = _n
        dev = _d
        web_dir = _wd

        def _send_file(self, path, ctype=None):
            try:
                with open(path, "rb") as f:
                    body = f.read()
            except Exception:
                self._json(404, {"ok": False, "error": "not found"})
                return
            self.send_response(200)
            ct = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            # پاسخ سبُک preflight برای CORS
            self.send_response(204)
            self.send_header("Allow", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Init-Data")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            from urllib.parse import urlparse
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send_file(os.path.join(self.web_dir, "index.html"), "text/html; charset=utf-8")
                return
            # فایل استاتیک (icon.png, css/js و...)
            safe_path = path.lstrip("/")
            static_candidate = os.path.normpath(os.path.join(self.web_dir, safe_path))
            if (static_candidate.startswith(self.web_dir)
                    and os.path.isfile(static_candidate)):
                self._send_file(static_candidate)
                return
            if path == "/healthz":
                self._json(200, {"ok": True, "fallback": True})
                return
            # بقیه GET ها از parent
            super().do_GET()

        def do_POST(self):
            from urllib.parse import urlparse
            path = urlparse(self.path).path
            user = self._user()
            if not user:
                self._json(401, {"ok": False, "error": "شناسایی نشدی"})
                return
            body = self._body()
            def _s(v, default=""):
                try:
                    return str(v).strip() if v is not None else default
                except Exception:
                    return default

            code = _s(body.get("room") or body.get("code")).upper()
            s = self.store.find_by_code(code) if code else None

            def need_room_and_char():
                if not s:
                    self._json(404, {"ok": False, "error": "اتاق پیدا نشد"})
                    return None, None
                ch = s.get_char(user["id"])
                if not ch:
                    self._json(400, {"ok": False, "error": "کاراکتر نداری"})
                    return s, None
                return s, ch

            if path == "/api/check":
                from game.adventure import skill_check
                r, ch = need_room_and_char()
                if not r: return
                try: dc = int(body.get("dc", 10))
                except: dc = 10
                msg = skill_check(r, user["id"], body.get("skill", "perception"),
                                  dc, body.get("mode", "normal"))
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"text": msg, "state": self._state(r, user)}})
                return

            if path == "/api/rest":
                from game.adventure import rest
                r, ch = need_room_and_char()
                if not r: return
                msg = rest(r, user["id"], _s(body.get("kind"), "short"))
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"text": msg, "state": self._state(r, user)}})
                return

            if path == "/api/move":
                r, ch = need_room_and_char()
                if not r: return
                if r.combat:
                    self._json(400, {"ok": False, "error": "در نبرد نمی‌توانی حرکت کنی"})
                    return
                direction = _s(body.get("direction") or body.get("text"), "جلو")
                from game.map import move_to, init_world
                init_world(r)
                msg = move_to(r, direction)
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"text": msg, "state": self._state(r, user)}})
                return

            if path in ("/api/look", "/api/where/look"):
                r, ch = need_room_and_char()
                if not r: return
                from game.map import describe, init_world
                init_world(r)
                msg = describe(r)
                self._json(200, {"ok": True, "data": {"text": msg, "state": self._state(r, user)}})
                return

            if path == "/api/inventory":
                from game.adventure import inventory_text
                r, ch = need_room_and_char()
                if not r: return
                msg = inventory_text(ch)
                self._json(200, {"ok": True, "data": {"text": msg, "state": self._state(r, user)}})
                return

            if path == "/api/disarm":
                from game.world import try_disarm_trap
                r, ch = need_room_and_char()
                if not r: return
                try: dc = int(body.get("dc", 0) or 0)
                except: dc = 0
                msg = try_disarm_trap(r, ch, _s(body.get("name")), dc or None)
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"text": msg, "state": self._state(r, user)}})
                return

            if path == "/api/inventory/use":
                from game.adventure import use_item
                r, ch = need_room_and_char()
                if not r: return
                msg = use_item(r, user["id"], _s(body.get("item")))
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"text": msg, "state": self._state(r, user)}})
                return

            if path == "/api/deathsave":
                from game.adventure import death_save
                r, ch = need_room_and_char()
                if not r: return
                msg = death_save(r, user["id"])
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"text": msg, "state": self._state(r, user)}})
                return

            if path == "/api/combat/dodge":
                from game.combat import dodge, advance, end_combat
                r, ch = need_room_and_char()
                if not r: return
                if not r.combat:
                    self._json(400, {"ok": False, "error": "نبردی در جریان نیست"})
                    return
                msgs = [dodge(r, user["id"])]
                if r.combat:
                    nxt = advance(r)
                    if nxt: msgs.append(nxt)
                    if r.combat:
                        mons = [p for p in r.combat["participants"] if p["kind"]=="monster"]
                        if mons and all(not m.get("alive",False) for m in mons):
                            end = end_combat(r)
                            if end: msgs.append(end)
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(r, user)}})
                return

            if path == "/api/combat/skip":
                from game.combat import advance, end_combat
                r, ch = need_room_and_char()
                if not r: return
                if not r.combat:
                    self._json(400, {"ok": False, "error": "نبردی در جریان نیست"})
                    return
                msgs = [advance(r)]
                if r.combat:
                    mons = [p for p in r.combat["participants"] if p["kind"]=="monster"]
                    if mons and all(not m.get("alive",False) for m in mons):
                        end = end_combat(r)
                        if end: msgs.append(end)
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(r, user)}})
                return

            if path == "/api/combat/deathsave":
                from game.adventure import death_save
                from game.combat import advance
                r, ch = need_room_and_char()
                if not r: return
                if not r.combat:
                    self._json(400, {"ok": False, "error": "نبردی در جریان نیست"})
                    return
                if not ch or ch.hp > 0:
                    self._json(400, {"ok": False, "error": "تو زمین‌گیر نیستی!"})
                    return
                msgs = [death_save(r, user["id"])]
                # مرگ/زنده شدن را چک کن؛ اگر هنوز در نبرد هستی نوبت بچرخد
                failed = ch.death_saves.get("fail", 0) >= 3
                if r.combat and not failed:
                    nxt = advance(r)
                    if nxt: msgs.append(nxt)
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(r, user)}})
                return

            # --- هندلر عمومی اکشن‌های نبرد (BG3) ---
            COMBAT_SIMPLE = {
                "/api/combat/dash": ("dash", None),
                "/api/combat/disengage": ("disengage", None),
                "/api/combat/hide": ("hide", None),
                "/api/combat/secondwind": ("second_wind", None),
                "/api/combat/actionsurge": ("action_surge", None),
                "/api/combat/rage": ("rage", None),
                "/api/combat/rebuke": ("hellish_rebuke", None),
            }
            BONUS_FN = {"rage","bardic_inspiration","offhand_attack","divine_smite",
                        "cunning_action","hellish_rebuke","jump_action","throw_action",
                        "dip_weapon","help_up"}
            ERROR_PREFIXES = ("هنوز نوبت","نمی‌توانی","این قابلیت فقط","تعداد","هم‌گروهی",
                              "کاراکترت","سلاح","هدف پیدا نشد","اکشن اصلی","بونس‌اکشن",
                              "نبردی","جایگاه","نفس اژدها را","فقط می‌توانی","تو زمین",
                              "مردی","نوبت تو نیست")
            def _combat_call(fn_name, fn_call, target_needed=False, advance_after=True):
                from game import combat as C
                r, ch = need_room_and_char()
                if not r: return
                if not r.combat:
                    self._json(400, {"ok": False, "error": "نبردی در جریان نیست"})
                    return
                fn = getattr(C, fn_name, None)
                if not fn:
                    self._json(500, {"ok": False, "error": "تابع پیدا نشد: "+fn_name})
                    return
                try:
                    msg = fn_call(r, C, fn)
                except Exception as e:
                    self._json(500, {"ok": False, "error": str(e)})
                    return
                is_bonus = fn_name in BONUS_FN or not advance_after
                success = bool(msg) and not str(msg).startswith(ERROR_PREFIXES)
                msgs = [msg]
                if success and not is_bonus and r.combat:
                    nxt = C.advance(r)
                    if nxt: msgs.append(nxt)
                    # پایان خودکار
                    if r.combat:
                        mons = [p for p in r.combat["participants"] if p["kind"]=="monster"]
                        if mons and all(not m.get("alive",False) for m in mons):
                            end = C.end_combat(r)
                            if end: msgs.append(end)
                self.store.save(r)
                self._json(200, {"ok": True, "data": {"messages": msgs, "state": self._state(r, user)}})

            if path in COMBAT_SIMPLE:
                fn_name, _ = COMBAT_SIMPLE[path]
                _combat_call(fn_name, lambda r,C,fn: fn(r, user["id"]))
                return

            if path == "/api/combat/help":
                _combat_call("help_action",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("target"))),
                             target_needed=True)
                return
            if path == "/api/combat/shove":
                _combat_call("shove",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("target"))),
                             target_needed=True)
                return
            if path == "/api/combat/inspire":
                _combat_call("bardic_inspiration",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("target"))),
                             target_needed=True, advance_after=False)
                return
            if path == "/api/combat/move":
                _combat_call("move_action",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("where"), "near")),
                             advance_after=False)
                return
            if path == "/api/combat/offhand":
                _combat_call("offhand_attack",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("target"))),
                             target_needed=True, advance_after=False)
                return
            if path == "/api/combat/smite":
                try: slot = int(body.get("slot", 1) or 1)
                except (TypeError, ValueError): slot = 1
                _combat_call("divine_smite",
                             lambda r,C,fn: fn(r, user["id"], slot),
                             advance_after=False)
                return
            if path == "/api/combat/jump":
                _combat_call("jump_action",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("where"), "near")),
                             advance_after=False)
                return
            if path == "/api/combat/helpup":
                _combat_call("help_up",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("target"))),
                             target_needed=True, advance_after=False)
                return
            if path == "/api/combat/throw":
                item = _s(body.get("item"), "torch") or "torch"
                _combat_call("throw_action",
                             lambda r,C,fn: fn(r, user["id"], item, _s(body.get("target"))),
                             target_needed=True, advance_after=False)
                return
            if path == "/api/combat/dip":
                _combat_call("dip_weapon",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("element"), "fire")),
                             advance_after=False)
                return
            if path == "/api/combat/cunning":
                _combat_call("cunning_action",
                             lambda r,C,fn: fn(r, user["id"], _s(body.get("what"), "disengage")),
                             advance_after=False)
                return

            # پیش‌فرض هندلرهای parent (attack/cast/skip/story/roll/scenario/char/create و...)
            super().do_POST()

    # fallback state: حالت scenario_view (فیلتر اسپویل)
    def _safe_scenario(sc):
        if not sc: return None
        def _ln(l):
            if isinstance(l, dict):
                return {"name": l.get("name", str(l)),
                        "description": l.get("description", ""),
                        "encounter_hint": l.get("encounter_hint", "")}
            return {"name": str(l)}
        return {
            "title": sc.get("title"), "hook": sc.get("hook"), "goal": sc.get("goal"),
            "locations": [_ln(l) for l in (sc.get("locations") or [])],
            "npcs": [{"name": (n.get("name") if isinstance(n, dict) else str(n)),
                      "role": (n.get("role") if isinstance(n, dict) else "")}
                     for n in (sc.get("npcs") or [])],
            "encounters": [{"name": e.get("name","؟"), "count": e.get("count",1),
                            "ac": e.get("ac"), "hp": e.get("hp"), "xp": e.get("xp"),
                            "is_boss": bool(e.get("is_boss")),
                            "location": e.get("location","")}
                           for e in (sc.get("encounters") or [])],
            "treasure": sc.get("treasure"),
            "traps": [{"name": t.get("name",""), "location": t.get("location",""),
                       "detect_dc": t.get("detect_dc",13)}
                      for t in (sc.get("traps") or []) if not t.get("triggered")],
            "branches": sc.get("branches") or [],
            "boss": ({"name": sc["boss"].get("name",""),
                      "ability": sc["boss"].get("ability","")}
                     if isinstance(sc.get("boss"), dict) else None),
        }

    FullApiHandler._state_orig = FullApiHandler._state
    def _state_full(self, s, user):
        d = self._state_orig(s, user)
        d["scenario"] = _safe_scenario(getattr(s, "scenario", None))
        world = getattr(s, "world", None) or {}
        d["room"]["location"] = world.get("location", "")
        d["room"]["locations"] = world.get("locations", [])
        d["room"]["light"] = world.get("light", "dark")
        return d
    FullApiHandler._state = _state_full

    class ThreadingServer(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    try:
        httpd = ThreadingServer(("0.0.0.0", port), FullApiHandler)
    except OSError as e:
        log("خطا در bind پورت %d: %s" % (port, e))
        return
    log("🌐 مینی‌گیم (fallback) روی پورت %d فعال شد" % port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    while not stopped():
        time.sleep(1)
    httpd.shutdown()
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
