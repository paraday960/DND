# -*- coding: utf-8 -*-
"""هندلرهای اصلی ربات — همه دستورات بازی."""
import logging

from telegram import Update
from telegram.ext import ContextTypes

import config
from game.combat import (
    attack, cast, dodge, dash, disengage, help_action, hide, shove,
    second_wind, action_surge, rage, bardic_inspiration, move_action,
    offhand_attack, divine_smite, jump_action, help_up, throw_action,
    dip_weapon, cunning_action, hellish_rebuke,
    end_combat, start_combat, advance, is_player_turn,
)
from game.adventure import death_save, inventory_text, rest, skill_check, use_item
from game.dice import DiceError, roll_disadvantage, roll_expression, roll_advantage, roll_d20
from game.models import Session
from game.rules import ABILITIES, ability_mod, level_from_xp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from .keyboards import main_menu

logger = logging.getLogger(__name__)

WELCOME = """🐉 **به دانجن‌مستر هوشمند خوش اومدی!**

اینجا می‌تونی با حداکثر ۸ نفر D&D حرفه‌ای بازی کنی؛ هوش مصنوعی سناریو می‌سازه، روایت می‌کنه و دانجن‌مستری رو بر عهده می‌گیره.

📌 **شروع سریع:**
۱. یه **گروه تلگرامی** بساز و ربات رو اضافه کن
۲. میزبان: `/newgame` — بقیه: `/join <کد>`
۳. همه `/newchar` — کاراکترشون رو بسازن
۴. میزبان: `/scenario` — هوش مصنوعی سناریو می‌سازه
۵. `/story اقدام‌تو` — ماجرا شروع می‌شه! ⚔️

راهنمای کامل دستورات: `/help`
"""

HELP = """📚 **راهنمای کامل دستورات — قوانین D&D 5e با الهام از Baldur's Gate 3**

🎮 **جلسه و بازیکن‌ها:**
• `/newgame` — ساختن اتاق بازی (میزبان)
• `/join <کد>` — پیوستن به اتاق با کد
• `/newchar` — ساخت کاراکتر جدید (۱۲ کلاس، ۸ نژاد)
• `/sheet` — نمایش کاراکتر
• `/party` — لیست گروه

🐉 **دانجن‌مستر هوشمند:**
• `/scenario` — ساخت سناریو با AI (میزبان)
• `/story <اقدام>` — روایت اکشن با AI
• `/where` — خلاصه وضعیت ماجرا

⚔️ **اکشن‌های اصلی نبرد (هر نوبت ۱ اکشن اصلی):**
• `/combat` — شروع نبرد (initiative خودکار)
• `/attack <دشمن>` — حمله با سلاح (Extra Attack، Sneak Attack، Smite، خشم، کریت، پوشش، ارتفاع)
• `/cast <طلسم> <هدف>` — انداختن طلسم
• `/dash` — 🏃 دویدن (حرکت مضاعف، بدون حمله فرصت)
• `/disengage` — 🚪 عقب‌نشینی امن (بدون حمله فرصت)
• `/dodge` — 🛡️ دفاع فعال (حملات به تو با ضعف)
• `/help_act <هم‌گروهی>` — 🤝 کمک (حمله بعدی هدف مزیت می‌گیرد)
• `/hide` — 🙈 پنهان شدن (حمله بعدی با مزیت)
• `/shove <دشمن>` — 💪 هل دادن (انداختن به زمین/پرتگاه/آتش!)
• `/secondwind` — 💨 نفس دوم جنگجو (التیم نفس، یک‌بار در استراحت کوتاه)
• `/actionsurge` — ⚡ اکشن اضافه جنگجو
• `/combatend` — پایان دستی نبرد

✨ **بونس‌اکشن‌ها:**
• `/rage` — 🪓 خشم بربر (مقاومت فیزیکی + آسیب اضافه)
• `/inspire <هم‌گروهی>` — 🎻 الهام بَرد (یک دی الهام به رول دوست)
• `/offhand <هدف>` — 🗡️ حمله دست دوم با سلاح سبک
• `/jump [high/far]` — 🦘 پرش (بدون حمله فرصت، پرش به بلندی)
• `/throw <item> [هدف]` — 🧪 پرتاب آیتم (معجون شفا، مشعل، روغن)
• `/dip [fire/poison]` — 🔥 فرو کردن سلاح در آتش/سم (1d4 آسیب اضافه)
• `/cunning [dash/hide/disengage]` — 🗡️ Cunning Action راگ
• `/cast healingword <هدف>` — 💚 شفا به عنوان بونس‌اکشن
• `/smite [level]` — ✨ Divine Smite پالادین

🛡️ **واکنش‌ها (Reaction):**
• حمله فرصت — وقتی کسی بدون Disengage از کنارت دور شود، **خودکار** حمله می‌زنی!
• `/cast shield` — 🛡️ سپر جادویی (۵+ AC)
• `/rebuke` — 😈 Hellish Rebuke تیفلینگ (2d10 آتش در پاسخ)

🗺️ **حرکت و موقعیت (الهام از BG3):**
• `/move near` — جلو به خط مقدم
• `/move far` — عقب (برای کمان/طلسم)
• `/move flee` — فرار
• `/move high` — ⛰️ بلندی (High Ground: +2 به حمله)
• `/move low` — پایین آمدن
• `/move cover` — 🛡️ نیم‌پوشش (+2 AC)
• `/move full` — 🧱 پوشش کامل (حملات اصابت نمی‌کنند)
• `/move open` — خروج از پوشش

💀 **وضعیت‌های بحرانی:**
• `/deathsave` — نجات از مرگ
• `/helpup <هم‌گروهی>` — 🤝 بلند کردن دوست از زمین (1 HP)

🏅 **قابلیت‌های نژادی:**
• 🍀 شانس هالفلینگ: رول ۱ دوباره می‌افتد
• 💪 پافشاری نیمه‌اورک: یک‌بار از مرگ با ۱ HP برمی‌گردی
• 🐲 نفس اژدها (اژدهازاده): `/cast dragonbreath`
• 😈 سرزنش جهنمی (تیفلینگ): `/rebuke`

🎲 **متفرقه:**
• `/roll 2d6+3` — تاس
• `/roll adv|dis` — با برتری/ضعف
• `/check <skill> <dc>` — آزمون مهارت
• `/rest short|long` — استراحت کوتاه/طولانی
• `/inventory` — موجودی
• `/use <item>` — استفاده از آیتم

💬 متن‌های فارسی طبیعی هم پشتیبانی می‌شوند (مثلاً «حمله به گابلین» یا «دفاع کن»)
"""


# ---------- ابزارهای کمکی ----------

def _save(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    context.bot_data["store"].save(session)


def _need_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = _session(update, context)
    if not session:
        return None, "❌ هنوز اتاق بازی ساخته نشده.\nمیزبان: `/newgame` — بقیه: `/join <کد>`"
    return session, None


def _is_dm(session: Session, update: Update) -> bool:
    return session.dm_id == update.effective_user.id


def _user_char(session: Session, update: Update):
    return session.get_char(update.effective_user.id)


# ---------- دستورات پایه ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = main_menu()
    url = config.webapp_url()
    if url:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎮 ورود به مینی‌گیم", web_app=WebAppInfo(url=url))]]
            + list(kb.inline_keyboard)
        )
    await update.message.reply_text(
        WELCOME + "\n\n🎮 **مینی‌گیم:** همه‌چیز داخل بازی — اتاق، کاراکتر، سناریو، نبرد! دکمه زیر را بزن.",
        reply_markup=kb,
    )


async def game_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = config.webapp_url()
    if not url:
        await update.message.reply_text(
            "❌ آدرس مینی‌گیم تنظیم نشده!\n"
            "روی گوشی: `bash termux/tunnel.sh`\n"
            "یا در `.env` مقدار `WEBAPP_URL` را بگذار."
        )
        return
    await update.message.reply_text(
        "🎮 **مینی‌گیم D&D** — داخل بازی همه‌چیز انجام می‌شود!",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎮 باز کردن مینی‌گیم", web_app=WebAppInfo(url=url))]]
        ),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)


async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال لینک قابل‌کپی مینی‌گیم."""
    url = config.webapp_url()
    if not url:
        await update.message.reply_text("❌ تونل مینی‌گیم هنوز آماده نیست.")
        return
    await update.message.reply_text(
        "🔗 **لینک مینی‌گیم (v2.52):**\n\n" + url + "\n\n"
        "_اگر در تلگرام باز نشد در مرورگر کپی و باز کنید._",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎮 باز کردن مینی‌گیم", web_app=WebAppInfo(url=url))
        ]]),
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وضعیت زنده بات."""
    import sys, platform
    url = config.webapp_url()
    lines = ["📊 **وضعیت بات D&D v2.52**", ""]
    lines.append("🌐 مینی‌گیم: " + ("✅ " + url if url else "❌ آماده نیست"))
    healthy = False
    if url:
        try:
            r = __import__("requests").get(url + "/healthz", timeout=5)
            healthy = r.status_code == 200
            lines.append("🔌 healthz: " + ("✅ %d" % r.status_code if healthy else "❌ %d" % r.status_code))
        except Exception as e:
            lines.append("🔌 healthz: ❌ %s" % str(e)[:60])
    lines.append("💬 پایتون: " + sys.version.split()[0])
    lines.append("📱 پلتفرم: " + platform.machine())
    await update.message.reply_text("\n".join(lines))


async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤔 دستور ناشناخته‌ست. `/help` بزن.")


# ---------- منوی شیشه‌ای ----------
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    texts = {
        "help": HELP,
        "join": "🔗 برای پیوستن کد میزبان رو بگیر و بفرست: `/join <کد>`",
    }
    if action == "newgame":
        await newgame_cmd(update, context, from_callback=True)
        return
    if action == "newchar":
        await query.message.reply_text("🧙 `/newchar` رو بفرست تا ساخت کاراکتر شروع بشه.")
        return
    if action == "sheet":
        await sheet_cmd(update, context, from_callback=True)
        return
    if action == "party":
        await party_cmd(update, context, from_callback=True)
        return
    if action == "scenario":
        await scenario_cmd(update, context, from_callback=True)
        return
    if action == "story":
        await query.message.reply_text(
            "📖 هر اقدامت رو بنویس و بفرست:\n`/story من درِ کهنه رو باز می‌کنم`")
        return
    if action == "combat":
        await combat_cmd(update, context, from_callback=True)
        return
    await query.message.reply_text(texts.get(action, "🧭 منو"), reply_markup=main_menu())


# ---------- جلسه ----------
async def newgame_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    chat = update.effective_chat
    user = update.effective_user
    store = context.bot_data["store"]
    session = store.load(chat.id)
    if session and len(session.players) > 0 and session.state != "lobby":
        text = (f"⚠️ در این چت قبلاً اتاقی با کد **{session.code}** ساخته شده!\n"
                f"اگه می‌خوای از نو شروع کنی: `/reset`")
        if from_callback:
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)
        return
    if session:
        store.delete(chat.id)

    session = Session(chat.id, "ماجرای " + (user.first_name or "بی‌نام"), user.id,
                      user.first_name or "میزبان")
    store.save(session)
    text = (
        f"🎮 **اتاق بازی ساخته شد!**\n\n"
        f"🔑 کد اتاق: `{session.code}`\n"
        f"👑 میزبان: {user.first_name}\n"
        f"👥 ظرفیت: ۸ نفر\n\n"
        f"بقیه با `/join {session.code}` ملحق می‌شن.\n"
        f"🧙 خودت اول کاراکترت رو بساز: `/newchar`\n"
        f"🐉 بعدش سناریو بساز: `/scenario`"
    )
    if from_callback:
        await update.callback_query.message.reply_text(text)
    else:
        await update.message.reply_text(text)


async def join_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیوستن به یک اتاق با کد — /join K7Q2A"""
    store = context.bot_data["store"]
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "🔗 مثال: `/join K7Q2A`\n"
            "کد اتاق را از میزبان بگیر."
        )
        return
    code = args[0].strip().upper()
    target = store.find_by_code(code)
    if not target:
        await update.message.reply_text("❌ اتاقی با این کد پیدا نشد!")
        return

    # هر چتِ دعوت‌شونده، یک جلسه محلی مختص همان چت می‌سازد که به همان کد وصل است.
    # اما مدل داده فعلی «یک جلسه = یک چت» است؛ پس /join در همان چت میزبان معنی دارد
    # (یا در چت خصوصی میزبان/بازیکن در همان اتاق). برای سادگی، اگر کاربر از قبل
    # در همان چتِ میزبان است فقط عضو می‌شود؛ در غیر این صورت اطلاع می‌دهد.
    session = store.load(update.effective_chat.id)
    if session and session.code != code:
        await update.message.reply_text(
            f"⚠️ در این چت اتاق دیگری با کد {session.code} فعال است.\n"
            "اگر می‌خواهی به این اتاق بپیوندی، اول `/reset` بزن."
        )
        return

    user = update.effective_user
    if not session:
        # این چت همان چت میزبان است که اتاق را دارد
        session = target
    res = session.add_player(user.id, user.first_name or "ماجراجو")
    if res == "already":
        await update.message.reply_text(f"✅ تو قبلاً در اتاق {code} عضو هستی. حالا `/newchar` بزن!")
        return
    if res == "full":
        await update.message.reply_text("❌ اتاق پر است! (حداکثر ۸ بازیکن)")
        return
    session.add_log("سیستم", f"{user.first_name} به اتاق پیوست")
    store.save(session)
    await update.message.reply_text(
        f"🎉 **به اتاق {code} خوش اومدی!**\n"
        f"👥 گروه: {session.name} (میزبان: {session.dm_name})\n\n"
        f"🧙 حالا کاراکترت رو بساز: `/newchar`"
    )


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store = context.bot_data["store"]
    session = store.load(update.effective_chat.id)
    if not session:
        await update.message.reply_text("اتاقی وجود نداره که ریست بشه.")
        return
    if not _is_dm(session, update):
        await update.message.reply_text("فقط میزبان می‌تونه اتاق رو ریست کنه.")
        return
    store.delete(update.effective_chat.id)
    await update.message.reply_text("🗑️ اتاق ریست شد. با `/newgame` از نو بساز.")


# ---------- کاراکتر و گروه ----------
async def sheet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    session, err = _need_session(update, context)
    if err:
        await update.effective_message.reply_text(err)
        return
    ch = _user_char(session, update)
    if not ch:
        await update.effective_message.reply_text(
            "🧙 هنوز کاراکتر نداری! بسازش: `/newchar`")
        return
    await update.effective_message.reply_text(ch.sheet_text())


async def party_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    session, err = _need_session(update, context)
    if err:
        await update.effective_message.reply_text(err)
        return
    lines = [f"👥 **گروه ماجراجو** (کد: `{session.code}`)", ""]
    for uid, p in session.players.items():
        ch = p["char"]
        role = "👑 DM" if int(uid) == session.dm_id else ""
        if ch:
            lines.append(f"• {ch.name} — {ch.race} {ch.cls} لvl{ch.level} ❤️{ch.hp}/{ch.max_hp} {role}")
        else:
            lines.append(f"• {p['user']} — (بدون کاراکتر) {role}")
    lines.append(f"\n{len(session.players)}/۸ نفر — کاراکتر ساخته‌شده: {session.char_count()}")
    await update.effective_message.reply_text("\n".join(lines))


# ---------- تاس ----------
async def roll_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "🎲 مثل: `/roll 2d6+3` یا `/roll d20` یا `/roll adv` (با برتری)")
        return
    expr = " ".join(args)
    try:
        if expr.lower() in ("adv", "advantage"):
            r = roll_advantage()
        elif expr.lower() in ("dis", "disadvantage"):
            r = roll_disadvantage()
        else:
            r = roll_expression(expr)
    except DiceError as e:
        await update.message.reply_text(f"❌ {e}")
        return

    session = _session(update, context)
    user = update.effective_user
    if session:
        session.add_log(user.first_name or "بازیکن", f"تاس {expr}: {r['total']} ({r['breakdown']})")
        _save(update, context, session)

    crit = ""
    if expr.lower().strip().endswith("d20") or expr.lower() == "d20":
        if r["total"] == 20:
            crit = "\n🔥 **بحرانی!**"
        elif r["total"] == 1:
            crit = "\n💔 **شکست بحرانی!**"
    await update.message.reply_text(
        f"🎲 {user.first_name} تاس {expr} انداخت:\n"
        f"**نتیجه: {r['total']}** ({r['breakdown']}){crit}"
    )


# ---------- دانجن‌مستر هوشمند ----------
async def scenario_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    session, err = _need_session(update, context)
    if err:
        await update.effective_message.reply_text(err)
        return
    if not _is_dm(session, update):
        await update.effective_message.reply_text("🐉 فقط میزبان می‌تونه سناریو بسازه.")
        return
    if session.char_count() < 1:
        await update.effective_message.reply_text(
            "اول حداقل یه کاراکتر بساز (`/newchar`) تا سناریو متناسب با گروه باشه.")
        return

    request = " ".join(context.args or [])
    narrator = context.bot_data["narrator"]
    msg = await update.effective_message.reply_text(
        "🧠 هوش مصنوعی داره سناریو می‌سازه... چند لحظه صبر کن ⏳")
    scenario = narrator.scenario(session, request)
    session.scenario = scenario
    session.state = "playing"
    session.add_log("DM", f"سناریو ساخته شد: {scenario.get('title')}")
    _save(update, context, session)
    try:
        await msg.edit_text(
            "🐉 **سناریوی ساخته‌شده توسط هوش مصنوعی:**\n\n" + session.scenario_text() +
            "\n\nحالا ماجرا رو با `/story` شروع کن!"
        )
    except Exception:
        await update.effective_message.reply_text(session.scenario_text())


async def story_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    action = " ".join(context.args) or "ادامه بده؛ چه اتفاقی می‌افته؟"
    narrator = context.bot_data["narrator"]
    msg = await update.message.reply_text("📖 روایت در جریان است...")
    try:
        text = narrator.narrate(session, action)
    except Exception:
        text = "❌ خطا در اتصال به هوش مصنوعی. دوباره تلاش کن."
    _save(update, context, session)
    try:
        await msg.edit_text("📖 " + text)
    except Exception:
        await update.message.reply_text("📖 " + text)


async def where_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    narrator = context.bot_data["narrator"]
    msg = await update.message.reply_text("🗺️ در حال مرور ذهن دانجن‌مستر...")
    try:
        text = narrator.recap(session)
    except Exception:
        text = session.log_text(10)
    try:
        await msg.edit_text(text)
    except Exception:
        await update.message.reply_text(text)


# ---------- نبرد ----------
async def combat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    session, err = _need_session(update, context)
    if err:
        await update.effective_message.reply_text(err)
        return
    if session.combat:
        from game.combat import order_text
        await update.effective_message.reply_text(order_text(session))
        return
    if not session.scenario:
        await update.effective_message.reply_text(
            "🐉 اول سناریو بساز تا دشمن‌ها معلوم شن:\n`/scenario`\n"
            "(فعلاً با دشمن‌های پیش‌فرض شروع می‌کنم...)")
    from game.combat import run_initial_monsters
    text = start_combat(session)
    _save(update, context, session)
    await update.effective_message.reply_text(text)
    # اگر اولین نوبت مال دشمن بود، خودکار اجرا می‌شه
    text2 = run_initial_monsters(session)
    if text2:
        _save(update, context, session)
        await update.effective_message.reply_text(text2)


async def attack_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست. `/combat` بزن.")
        return
    target = " ".join(context.args)
    if not target:
        await update.message.reply_text("🎯 مثل: `/attack گابلین`")
        return
    before = len(session.log)
    result = attack(session, update.effective_user.id, target)
    _save(update, context, session)
    await update.message.reply_text(result)
    if len(session.log) > before:
        await _maybe_advance(update, context, session)


async def cast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست. `/combat` بزن.")
        return
    args = context.args or []
    if not args:
        from game.rules import SPELLS
        await update.message.reply_text(
            "✨ مثل: `/cast firebolt گابلین`\nطلسم‌ها: " +
            ", ".join(f"`{k}`" for k in SPELLS))
        return
    spell_key = args[0].lower()
    target = " ".join(args[1:])
    before = len(session.log)
    result = cast(session, update.effective_user.id, spell_key, target)
    _save(update, context, session)
    await update.message.reply_text(result)
    if len(session.log) > before:
        await _maybe_advance(update, context, session)


async def deathsave_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    text = death_save(session, update.effective_user.id)
    _save(update, context, session); await update.message.reply_text(text)


async def dodge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    text = dodge(session, update.effective_user.id)
    _save(update, context, session); await update.message.reply_text(text)
    if "دفاع کرد" in text:
        await _maybe_advance(update, context, session)


async def skip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست.")
        return
    if not is_player_turn(session, update.effective_user.id):
        await update.message.reply_text("هنوز نوبت تو نیست.")
        return
    text = advance(session)
    _save(update, context, session)
    await update.message.reply_text(text)


async def _maybe_advance(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    """بعد از هر اقدام معتبر بازیکن، نوبت را جلو می‌برد و پیروزی را خودکار ثبت می‌کند."""
    if not session.combat:
        return
    text = advance(session)
    await update.message.reply_text(text)
    monsters = [p for p in session.combat["participants"] if p["kind"] == "monster"]
    if monsters and all(not m["alive"] for m in monsters):
        result = end_combat(session)
        await update.message.reply_text(result)
    _save(update, context, session)


async def combatend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست.")
        return
    result = end_combat(session)
    _save(update, context, session)
    await update.message.reply_text(result)


# ---------- اکشن‌های جدید نبرد ----------
async def dash_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    text = dash(session, update.effective_user.id)
    _save(update, context, session)
    await update.message.reply_text(text)


async def disengage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    text = disengage(session, update.effective_user.id)
    _save(update, context, session)
    await update.message.reply_text(text)


async def help_action_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    target = " ".join(context.args or [])
    text = help_action(session, update.effective_user.id, target)
    _save(update, context, session)
    await update.message.reply_text(text)
    await _maybe_advance(update, context, session)


async def hide_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    text = hide(session, update.effective_user.id)
    _save(update, context, session)
    await update.message.reply_text(text)
    await _maybe_advance(update, context, session)


async def shove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    target = " ".join(context.args or [])
    text = shove(session, update.effective_user.id, target)
    _save(update, context, session)
    await update.message.reply_text(text)
    await _maybe_advance(update, context, session)


async def secondwind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    text = second_wind(session, update.effective_user.id)
    _save(update, context, session)
    await update.message.reply_text(text)
    await _maybe_advance(update, context, session)


async def actionsurge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    text = action_surge(session, update.effective_user.id)
    _save(update, context, session)
    await update.message.reply_text(text)


async def rage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    text = rage(session, update.effective_user.id)
    _save(update, context, session)
    await update.message.reply_text(text)


async def inspire_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    target = " ".join(context.args or [])
    text = bardic_inspiration(session, update.effective_user.id, target)
    _save(update, context, session)
    await update.message.reply_text(text)


async def move_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست."); return
    where = (context.args[0] if context.args else "near")
    text = move_action(session, update.effective_user.id, where)
    _save(update, context, session)
    await update.message.reply_text(text)


async def offhand_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    target = " ".join(context.args or [])
    text = offhand_attack(session, update.effective_user.id, target)
    _save(update, context, session)
    await update.message.reply_text(text)
    if "نابود شد" in text:
        await _maybe_advance(update, context, session)


async def smite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    slot = 1
    if context.args:
        try:
            slot = int(context.args[0])
        except ValueError:
            slot = 1
    text = divine_smite(session, update.effective_user.id, slot)
    _save(update, context, session)
    await update.message.reply_text(text)
    if "نابود شد" in text:
        await _maybe_advance(update, context, session)


async def jump_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    where = context.args[0] if context.args else "near"
    text = jump_action(session, update.effective_user.id, where)
    _save(update, context, session)
    await update.message.reply_text(text)


async def help_up_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    target = " ".join(context.args or [])
    text = help_up(session, update.effective_user.id, target)
    _save(update, context, session)
    await update.message.reply_text(text)
    await _maybe_advance(update, context, session)


async def throw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    args = context.args or []
    if not args:
        await update.message.reply_text("مثل: `/throw potion` یا `/throw torch گابلین`")
        return
    item = args[0]
    target = " ".join(args[1:])
    text = throw_action(session, update.effective_user.id, item, target)
    _save(update, context, session)
    await update.message.reply_text(text)
    if "نابود شد" in text:
        await _maybe_advance(update, context, session)


async def dip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    elem = context.args[0] if context.args else "fire"
    text = dip_weapon(session, update.effective_user.id, elem)
    _save(update, context, session)
    await update.message.reply_text(text)


async def cunning_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    what = context.args[0] if context.args else "disengage"
    text = cunning_action(session, update.effective_user.id, what)
    _save(update, context, session)
    await update.message.reply_text(text)


async def rebuke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    text = hellish_rebuke(session, update.effective_user.id)
    _save(update, context, session)
    await update.message.reply_text(text)
    if "نابود شد" in text:
        await _maybe_advance(update, context, session)


# ---------- تجربه و سطح ----------
async def xp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    ch = _user_char(session, update)
    if not ch:
        await update.message.reply_text("اول کاراکتر بساز: `/newchar`")
        return
    if ch.can_level_up():
        await update.message.reply_text(
            f"⭐ {ch.name}: {ch.xp} XP — سطح {ch.level}\n"
            f"🎉 **XP کافی برای ارتقا داری!** `/levelup` بزن.")
    else:
        await update.message.reply_text(
            f"⭐ {ch.name}: {ch.xp} XP — سطح {ch.level}\n"
            f"برای سطح بعد: {ch.xp_needed_for(ch.level + 1)} XP")


async def levelup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    ch = _user_char(session, update)
    if not ch:
        await update.message.reply_text("اول کاراکتر بساز: `/newchar`")
        return
    if not ch.can_level_up():
        await update.message.reply_text(
            f"هنوز XP کافی نداری ({ch.xp}/{ch.xp_needed_for(ch.level + 1)})")
        return
    info = ch.level_up()
    _save(update, context, session)
    await update.message.reply_text(
        f"🎉 **{ch.name} به سطح {info['new']} رسید!**\n"
        f"❤️ HP: +{info['hp_gain']}\n"
        f"✨ ویژگی‌ها: {', '.join(info['features'])}")


async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    args = context.args or []
    if not args:
        await update.message.reply_text("🎲 مثال: `/check stealth 15` یا `/check perception 12 adv`"); return
    try: dc = int(args[1]) if len(args) > 1 else 10
    except ValueError: dc = 10
    mode = args[2].lower() if len(args) > 2 else "normal"
    text = skill_check(session, update.effective_user.id, args[0], dc, mode)
    _save(update, context, session); await update.message.reply_text(text)


async def rest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    kind = (context.args[0] if context.args else "short")
    text = rest(session, update.effective_user.id, kind)
    _save(update, context, session); await update.message.reply_text(text)


async def inventory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    ch = _user_char(session, update)
    await update.message.reply_text("🎒 موجودی: " + (inventory_text(ch) if ch else "کاراکتر نداری"))


async def use_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err); return
    text = use_item(session, update.effective_user.id, " ".join(context.args or []))
    _save(update, context, session); await update.message.reply_text(text)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("خطا در هندلر: %s", context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ خطای غیرمنتظره‌ای رخ داد. دوباره تلاش کن.")
    except Exception:
        pass


# ==================== دستورات طبیعی فارسی ====================

async def natural_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """متن فارسی بدون اسلش را به اکشن بازی تبدیل می‌کند."""
    from game.nlp import parse_action
    session = _session(update, context)
    text = (update.message.text or "").strip()
    if not text or len(text) > 300:
        return
    ch = _user_char(session, update) if session else None
    in_combat = bool(session and session.combat)
    mobs = []
    if in_combat:
        mobs = [p["name"] for p in session.combat["participants"]
                if p.get("kind") == "monster"]
    is_dm = bool(session and _is_dm(session, update))
    downed = False
    if in_combat and ch:
        me = next((p for p in session.combat["participants"]
                   if p.get("kind") == "player" and p.get("uid") == str(update.effective_user.id)), None)
        downed = bool(me and (me.get("downed") or me.get("hp", 1) <= 0))

    act = parse_action(text, in_combat=in_combat, has_char=bool(ch),
                       valid_monsters=mobs, is_dm=is_dm, downed=downed)
    a = act.get("action")

    if a == "attack":
        target = act.get("target") or ""
        if not target:
            await update.message.reply_text("🎯 به چی حمله کنم؟ مثلاً: «حمله به گابلین»")
            return
        context.args = [target]
        await attack_cmd(update, context)
    elif a == "cast":
        context.args = [act.get("spell", "firebolt"), act.get("target", "")]
        await cast_cmd(update, context)
    elif a == "dodge":
        await dodge_cmd(update, context)
    elif a == "skip":
        await skip_cmd(update, context)
    elif a == "deathsave":
        await deathsave_cmd(update, context)
    elif a == "rest":
        context.args = [act.get("kind", "short")]
        await rest_cmd(update, context)
    elif a == "torch":
        if not ch:
            await update.message.reply_text("اول کاراکترت رو بساز.")
            return
        from game.world import try_environment_action
        env = try_environment_action(session, ch, "مشعل روشن می‌کنم")
        if env:
            _save(update, context, session)
            await update.message.reply_text(env)
        else:
            context.args = [text]
            await story_cmd(update, context)
    elif a == "look":
        if in_combat:
            from game.combat import order_text
            await update.message.reply_text(order_text(session))
        else:
            await where_cmd(update, context)
    elif a == "sheet":
        await sheet_cmd(update, context)
    elif a == "party":
        await party_cmd(update, context)
    elif a == "scenario":
        if not is_dm:
            await update.message.reply_text("فقط میزبان می‌تونه سناریو بسازه.")
            return
        context.args = []
        await scenario_cmd(update, context)
    elif a == "combat":
        context.args = []
        await combat_cmd(update, context)
    elif a == "help":
        await help_cmd(update, context)
    elif a == "narrate":
        context.args = [act.get("text", text)]
        await story_cmd(update, context)
    elif a == "potion":
        context.args = ["potion"]
        await use_cmd(update, context)
    elif a == "roll":
        context.args = [act.get("expr", "d20")]
        await roll_cmd(update, context)
    elif a == "shop":
        from game.shop import shop_text
        await update.message.reply_text(shop_text(session))
    elif a == "buy":
        item = act.get("item", "")
        if not item:
            await update.message.reply_text("چی بخرم؟ مثلاً «بخر معجون»")
            return
        from game.shop import buy
        ch = _user_char(session, update)
        result = buy(ch, item)
        _save(update, context, session)
        await update.message.reply_text(result)
    elif a == "sell":
        item = act.get("item", "")
        if not item:
            await update.message.reply_text("چی بفروشم؟ مثلاً «بفروش طناب»")
            return
        from game.shop import sell
        ch = _user_char(session, update)
        result = sell(ch, item)
        _save(update, context, session)
        await update.message.reply_text(result)
    elif a == "campaign":
        from game.campaign import make_campaign, start_chapter, advance_chapter
        if not session.campaign:
            session.campaign = make_campaign()
        if session.combat:
            await update.message.reply_text("اول نبرد فعلی رو تمام کن.")
            return
        sc = start_chapter(session.campaign, session, context.bot_data["narrator"])
        session.scenario = sc
        _save(update, context, session)
        await update.message.reply_text(
            f"📖 **{sc.get('chapter_title', 'فصل جدید')}**\n\n{sc.get('title')}\n_{sc.get('hook')}_\n\nبرای نبرد: «شروع نبرد»"
        )
    elif a == "talk":
        context.args = [text]
        await story_cmd(update, context)
    elif a == "wait":
        await update.message.reply_text("⏳ چند لحظه صبر می‌کنی... هوا سنگین‌تر می‌شود.")
    elif a == "move":
        from game.map import move_to
        result = move_to(session, act.get("text", "جلو"))
        _save(update, context, session)
        await update.message.reply_text(result)
    elif a == "where":
        from game.map import describe
        await update.message.reply_text(describe(session))
    elif a == "equip":
        from game.equipment import equip_weapon, equip_armor
        ch = _user_char(session, update)
        if not ch:
            await update.message.reply_text("اول کاراکتر بساز.")
            return
        if act.get("kind") == "armor":
            result = equip_armor(ch, act.get("item"))
        else:
            # برای تجهیز سلاح، باید سلاح در موجودی باشد
            wkey = act.get("item", "")
            if wkey not in ch.inventory or ch.inventory.get(wkey, 0) <= 0:
                # برای راحتی، اگر سلاح انتخابیِ کلاس است اضافه کن
                from game.rules import WEAPONS, CLASSES
                if wkey in WEAPONS and wkey in CLASSES.get(ch.cls, {}).get("weapons", []):
                    ch.inventory[wkey] = 1
                    result = equip_weapon(ch, wkey)
                else:
                    result = f"سلاح {wkey} را نداری."
            else:
                result = equip_weapon(ch, wkey)
        _save(update, context, session)
        await update.message.reply_text("🗡️ " + result)
