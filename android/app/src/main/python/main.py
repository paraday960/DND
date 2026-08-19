# -*- coding: utf-8 -*-
"""نقطه ورود ربات — اجرا: python main.py"""
import asyncio
import logging
import os
import subprocess
import threading
import time

import requests
from telegram import BotCommand, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

import config
from bot import conv, handlers
from game.narrator import Narrator
from game.store import Store


# ---- پایداری شبکه: اجبار IPv4 برای api.telegram.org (جلوگیری از timeout IPv6) ----
import socket as _socket
_orig_getaddrinfo = _socket.getaddrinfo
def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        if host in ("api.telegram.org", "149.154.167.220") and family == 0:
            family = _socket.AF_INET
    except Exception:
        pass
    return _orig_getaddrinfo(host, port, family, type, proto, flags)
_socket.getaddrinfo = _patched_getaddrinfo
# ---- END پایداری ----

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# لوپ رویداد پایدار برای اپلیکیشن تلگرام (در یک نخ جداگانه — هیچ‌وقت بسته نمی‌شود)
TEL_LOOP = asyncio.new_event_loop()


def _tel_loop_thread():
    asyncio.set_event_loop(TEL_LOOP)
    TEL_LOOP.run_forever()


threading.Thread(target=_tel_loop_thread, daemon=True, name="tg-loop").start()


def run_on_tel_loop(coro, timeout=90):
    """اجرای یک کوروتین روی لوپ پایدار تلگرام و گرفتن نتیجه."""
    fut = asyncio.run_coroutine_threadsafe(coro, TEL_LOOP)
    return fut.result(timeout=timeout)


def start_web(store, narrator, telegram_app=None):
    """وب‌سرور مینی‌گیم را در یک نخ جداگانه راه می‌اندازد."""
    try:
        from webapp import build_app
        from werkzeug.serving import make_server
        app = build_app(store, narrator, telegram_app=telegram_app, loop=TEL_LOOP)
        port = int(config.PORT)
        srv = make_server("0.0.0.0", port, app, threaded=True)
        threading.Thread(target=srv.serve_forever, daemon=True, name="webapp").start()
        logger.info("🌐 مینی‌گیم روی پورت %s فعال شد (حالت آزمایشی: %s)",
                    port, "بله" if config.WEBAPP_DEV else "خیر")
    except Exception as e:
        logger.error("❌ راه‌اندازی وب‌سرور مینی‌گیم ناموفق: %s", e)


async def _activate_webhook(app: Application, url: str) -> bool:
    """تلگرام را روی وب‌هوک تنظیم می‌کند — آپدیت‌ها مستقیم پوش می‌شوند."""
    await app.initialize()
    try:
        await app.bot.set_my_commands(COMMANDS)
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)
    ok = await app.bot.set_webhook(
        url=f"{url.rstrip('/')}/webhook/{config.BOT_TOKEN.split(':')[0]}",
        allowed_updates=Update.ALL_TYPES,
        max_connections=40,
    )
    # دکمه منوی کنار باکس پیام را همیشه به مینی‌گیم وصل کن
    try:
        await app.bot.set_chat_menu_button(
            menu_button={"type": "web_app", "text": "🎮 مینی‌گیم D&D",
                         "web_app": {"url": url.rstrip('/') + "/"}}
        )
    except Exception as e:
        logger.warning("set_chat_menu_button failed: %s", e)
    await app.start()
    return bool(ok)


def run_webhook_mode(app: Application) -> bool:
    """حالت وب‌هوک — برای محیط‌هایی که long-polling گیر می‌کند (مثل این سندباکس)."""
    url = config.webapp_url()
    if not url:
        return False
    try:
        ok = run_on_tel_loop(_activate_webhook(app, url), timeout=60)
        logger.info("🔔 وب‌هوک فعال شد: %s/webhook/... (%s)", url, "OK" if ok else "FAIL")
        return bool(ok)
    except Exception as e:
        logger.error("❌ فعال‌سازی وب‌هوک ناموفق: %s", e)
        return False


def _restart_tunnel():
    """تلاش برای بالا آوردن دوباره تونل (روی گوشی با Termux کار می‌کند)."""
    try:
        subprocess.Popen(
            ["bash", os.path.join(BASE_DIR, "termux", "tunnel.sh")],
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def watchdog(app: Application):
    """هر ۴۵ ثانیه سلامت تونل را می‌سنجد؛ اگر مرد، دوباره بالا می‌آورد و وب‌هوک را دوباره می‌بندد."""
    last_url = config.webapp_url()
    while True:
        time.sleep(45)
        url = config.webapp_url()
        try:
            r = requests.get(url, timeout=8)
            healthy = r.status_code == 200
        except Exception:
            healthy = False
        if not healthy:
            logger.error("⚠️ تونل مینی‌گیم در دسترس نیست — تلاش برای بازیابی...")
            _restart_tunnel()
            time.sleep(20)
            url2 = config.webapp_url()
            if url2 and url2 != url:
                try:
                    run_on_tel_loop(_activate_webhook(app, url2), timeout=60)
                    logger.info("🔔 وب‌هوک روی آدرس جدید تنظیم شد: %s", url2)
                except Exception as e:
                    logger.error("تنظیم مجدد وب‌هوک ناموفق: %s", e)
        elif url != last_url:
            last_url = url
            try:
                run_on_tel_loop(_activate_webhook(app, url), timeout=60)
                logger.info("🔔 وب‌هوک روی آدرس جدید تنظیم شد: %s", url)
            except Exception as e:
                logger.error("تنظیم مجدد وب‌هوک ناموفق: %s", e)

COMMANDS = [
    BotCommand("newgame", "🎮 ساخت اتاق بازی"),
    BotCommand("join", "🔗 پیوستن به اتاق"),
    BotCommand("newchar", "🧙 ساخت کاراکتر"),
    BotCommand("sheet", "📜 کاراکتر من"),
    BotCommand("party", "👥 گروه"),
    BotCommand("roll", "🎲 تاس: /roll 2d6+3"),
    BotCommand("scenario", "🐉 ساخت سناریو با AI"),
    BotCommand("story", "📖 روایت با AI"),
    BotCommand("where", "🗺️ وضعیت ماجرا"),
    BotCommand("combat", "⚔️ شروع نبرد"),
    BotCommand("attack", "🎯 حمله: /attack <دشمن>"),
    BotCommand("cast", "✨ طلسم"),
    BotCommand("dash", "🏃 دویدن/حرکت مضاعف"),
    BotCommand("disengage", "🚪 عقب‌نشینی امن"),
    BotCommand("dodge", "🛡️ دفاع فعال"),
    BotCommand("help_act", "🤝 کمک به هم‌گروهی"),
    BotCommand("hide", "🙈 پنهان شدن"),
    BotCommand("shove", "💪 هل دادن دشمن"),
    BotCommand("secondwind", "💨 نفس دوم جنگجو"),
    BotCommand("actionsurge", "⚡ اکشن اضافه جنگجو"),
    BotCommand("rage", "🪓 خشم بربر"),
    BotCommand("inspire", "🎻 الهام بارد"),
    BotCommand("smite", "✨ Divine Smite پالادین"),
    BotCommand("offhand", "🗡️ حمله دست دوم"),
    BotCommand("move", "🚶 حرکت در نبرد"),
    BotCommand("jump", "🦘 پرش (بونس‌اکشن)"),
    BotCommand("helpup", "🤝 بلند کردن دوست"),
    BotCommand("throw", "🧪 پرتاب آیتم"),
    BotCommand("dip", "🔥 فروبردن سلاح در آتش"),
    BotCommand("cunning", "🗡️ Cunning Action راگ"),
    BotCommand("rebuke", "😈 Hellish Rebuke تیفلینگ"),
    BotCommand("skip", "⏭️ رد نوبت"),
    BotCommand("deathsave", "💀 نجات از مرگ"),
    BotCommand("combatend", "🏁 پایان نبرد"),
    BotCommand("check", "🎲 آزمایش مهارت"),
    BotCommand("rest", "🔥 استراحت"),
    BotCommand("inventory", "🎒 موجودی"),
    BotCommand("use", "🧪 استفاده از آیتم"),
    BotCommand("help", "📚 راهنما"),
]


def build_app(store=None, narrator=None) -> Application:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "❌ BOT_TOKEN تنظیم نشده!\n"
            "فایل .env را بساز (کپی .env.example) و توکن را از @BotFather بگیر."
        )

    store = store or Store(config.DB_PATH)
    narrator = narrator or Narrator()
    if narrator.available:
        logger.info("🤖 هوش مصنوعی فعال: %s", config.AI_PROVIDER)
    else:
        logger.warning("⚠️ کلید هوش مصنوعی تنظیم نشده — حالت آفلاین (fallback)")

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .connect_timeout(8)
        .read_timeout(20)
        .write_timeout(15)
        .get_updates_read_timeout(20)
        .get_updates_connect_timeout(10)
        .pool_timeout(5)
        .build()
    )
    app.bot_data["store"] = store
    app.bot_data["narrator"] = narrator

    # دستورات پایه
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("game", handlers.game_cmd))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("newgame", handlers.newgame_cmd))
    app.add_handler(CommandHandler("join", handlers.join_cmd))
    app.add_handler(CommandHandler("reset", handlers.reset_cmd))
    app.add_handler(CommandHandler("sheet", handlers.sheet_cmd))
    app.add_handler(CommandHandler("party", handlers.party_cmd))
    app.add_handler(CommandHandler("roll", handlers.roll_cmd))
    app.add_handler(CommandHandler("scenario", handlers.scenario_cmd))
    app.add_handler(CommandHandler("story", handlers.story_cmd))
    app.add_handler(CommandHandler("where", handlers.where_cmd))
    app.add_handler(CommandHandler("combat", handlers.combat_cmd))
    app.add_handler(CommandHandler("attack", handlers.attack_cmd))
    app.add_handler(CommandHandler("cast", handlers.cast_cmd))
    app.add_handler(CommandHandler("dash", handlers.dash_cmd))
    app.add_handler(CommandHandler("disengage", handlers.disengage_cmd))
    app.add_handler(CommandHandler("help_act", handlers.help_action_cmd))
    app.add_handler(CommandHandler("hide", handlers.hide_cmd))
    app.add_handler(CommandHandler("shove", handlers.shove_cmd))
    app.add_handler(CommandHandler("dodge", handlers.dodge_cmd))
    app.add_handler(CommandHandler("move", handlers.move_cmd))
    app.add_handler(CommandHandler("rage", handlers.rage_cmd))
    app.add_handler(CommandHandler("inspire", handlers.inspire_cmd))
    app.add_handler(CommandHandler("secondwind", handlers.secondwind_cmd))
    app.add_handler(CommandHandler("actionsurge", handlers.actionsurge_cmd))
    app.add_handler(CommandHandler("offhand", handlers.offhand_cmd))
    app.add_handler(CommandHandler("smite", handlers.smite_cmd))
    app.add_handler(CommandHandler("jump", handlers.jump_cmd))
    app.add_handler(CommandHandler("helpup", handlers.help_up_cmd))
    app.add_handler(CommandHandler("throw", handlers.throw_cmd))
    app.add_handler(CommandHandler("dip", handlers.dip_cmd))
    app.add_handler(CommandHandler("cunning", handlers.cunning_cmd))
    app.add_handler(CommandHandler("rebuke", handlers.rebuke_cmd))
    app.add_handler(CommandHandler("skip", handlers.skip_cmd))
    app.add_handler(CommandHandler("deathsave", handlers.deathsave_cmd))
    app.add_handler(CommandHandler("combatend", handlers.combatend_cmd))
    app.add_handler(CommandHandler("levelup", handlers.levelup_cmd))
    app.add_handler(CommandHandler("xp", handlers.xp_cmd))
    app.add_handler(CommandHandler("check", handlers.check_cmd))
    app.add_handler(CommandHandler("rest", handlers.rest_cmd))
    app.add_handler(CommandHandler("inventory", handlers.inventory_cmd))
    app.add_handler(CommandHandler("use", handlers.use_cmd))

    # ساخت کاراکتر (گفت‌وگو) — در گروه جداگانه تا دستورهای دیگر را مسدود نکند
    app.add_handler(conv.conv_character, group=1)

    # منوی شیشه‌ای و دستورات ناشناخته
    app.add_handler(CallbackQueryHandler(handlers.menu_callback, pattern=r"^menu:"))
    # متن فارسی طبیعی (بدون اسلش) → پارسر زبان طبیعی
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.natural_text), group=2)
    app.add_handler(MessageHandler(filters.COMMAND, handlers.unknown_cmd))
    app.add_error_handler(handlers.error_handler)
    return app


async def _post_init(app: Application):
    try:
        await app.bot.set_my_commands(COMMANDS)
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)
    # اگر مینی‌گیم آدرس دارد، دکمه منو را هم وصل کن
    url = config.webapp_url()
    if url:
        try:
            await app.bot.set_chat_menu_button(
                menu_button={"type": "web_app", "text": "🎮 مینی‌گیم D&D",
                             "web_app": {"url": url.rstrip('/') + "/"}}
            )
        except Exception as e:
            logger.warning("set_chat_menu_button failed: %s", e)


def main():
    store = Store(config.DB_PATH)
    narrator = Narrator()
    app = build_app(store, narrator)

    url = config.webapp_url()
    if url and run_webhook_mode(app):
        # حالت وب‌هوک: تلگرام پیام‌ها را مستقیم پوش می‌کند — بدون polling
        start_web(store, narrator, telegram_app=app)
        threading.Thread(target=watchdog, args=(app,), daemon=True, name="watchdog").start()
        logger.info("🚀 ربات در حالت وب‌هوک فعال است (پیام‌ها فوری می‌رسند)")
        threading.Event().wait()  # برای همیشه زنده بمان
    else:
        # حالت polling (پشتیبان وقتی تونلی نیست)
        logger.warning("⚠️ تونلی در دسترس نیست — حالت polling (ممکن است تأخیر داشته باشد)")
        start_web(store, narrator)
        app.post_init = _post_init
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            timeout=5,
            bootstrap_retries=-1,
        )


if __name__ == "__main__":
    main()
