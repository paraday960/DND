# -*- coding: utf-8 -*-
"""هندلرهای اصلی ربات — همه دستورات بازی."""
import logging

from telegram import Update
from telegram.ext import ContextTypes

import config
from game.combat import attack, cast, end_combat, start_combat, advance
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

HELP = """📚 **راهنمای کامل دستورات**

🎮 **جلسه و بازیکن‌ها:**
• `/newgame` — ساختن اتاق بازی (میزبان)
• `/join <کد>` — پیوستن به اتاق با کد
• `/newchar` — ساخت کاراکتر جدید (نژاد، کلاس، سلاح)
• `/sheet` — نمایش کاراکتر
• `/party` — لیست گروه
• `/levelup` — ارتقای سطح (وقتی XP کافی داری)
• `/xp` — وضعیت تجربه

🐉 **دانجن‌مستر هوشمند:**
• `/scenario <توضیح>` — ساخت سناریو کامل با AI (فقط میزبان)
• `/story <اقدام>` — هر اقدامت رو بگو تا AI روایت کنه
• `/where` — خلاصه وضعیت فعلی ماجرا

⚔️ **نبرد:**
• `/combat` — شروع نبرد (نوبت‌بندی خودکار)
• `/attack <دشمن>` — حمله با سلاح
• `/cast <طلسم> <هدف>` — طلسم (firebolt, magicmissile, curewounds, ...)
• `/skip` — رد کردن نوبت
• `/combatend` — پایان نبرد و توزیع XP

🎲 **تاس:**
• `/roll 2d6+3` — هر ترکیبی: `d20`، `2d8`، `1d20+5`
• `/roll adv` یا `/roll dis` — با برتری / ضعف

💡 نکته: دشمن‌ها هوشمندند و در نوبت خودشون حمله می‌کنن!
"""


# ---------- ابزارهای کمکی ----------
def _session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["store"].load(update.effective_chat.id)


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
    text = start_combat(session)
    _save(update, context, session)
    await update.effective_message.reply_text(text)
    # اگر اولین نوبت مال دشمن بود، خودکار اجرا می‌شه
    if session.combat and session.combat["participants"][0]["kind"] == "monster":
        text2 = advance(session)
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
    result = attack(session, update.effective_user.id, target)
    _save(update, context, session)
    await update.message.reply_text(result)
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
    result = cast(session, update.effective_user.id, spell_key, target)
    _save(update, context, session)
    await update.message.reply_text(result)
    await _maybe_advance(update, context, session)


async def skip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, err = _need_session(update, context)
    if err:
        await update.message.reply_text(err)
        return
    if not session.combat:
        await update.message.reply_text("⚔️ نبردی در جریان نیست.")
        return
    text = advance(session)
    _save(update, context, session)
    await update.message.reply_text(text)


async def _maybe_advance(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    """بعد از هر اقدام بازیکن، نوبت به بعدی می‌رود؛ دشمن‌ها خودکار عمل می‌کنند."""
    if not session.combat:
        return
    text = advance(session)
    _save(update, context, session)
    await update.message.reply_text(text)


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


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("خطا در هندلر: %s", context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ خطای غیرمنتظره‌ای رخ داد. دوباره تلاش کن.")
    except Exception:
        pass
