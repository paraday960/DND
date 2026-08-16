# -*- coding: utf-8 -*-
"""گفت‌وگوی ساخت کاراکتر — نام → نژاد → کلاس → سلاح."""
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters,
)

from game.models import Character
from game.rules import CLASSES, RACES, WEAPONS

from .keyboards import class_keyboard, race_keyboard, weapon_keyboard

NAME, RACE, CLASS, WEAPON_CHOICE = range(4)


def _get_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store = context.bot_data["store"]
    return store.load(update.effective_chat.id)


async def _start_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورودی مشترک برای /newchar و /join — بررسی جلسه و شروع ساخت کاراکتر."""
    session = _get_session(update, context)
    if not session:
        await update.message.reply_text(
            "❌ اول باید یک جلسه بازی باشه!\n"
            "🎮 اگر خودت میزبان هستی: `/newgame`\n"
            "🔗 اگر دعوت شده‌ای: `/join <کد>` (کد را از میزبان بگیر)"
        )
        return ConversationHandler.END
    if len(session.players) >= 8 and not session.has_char(update.effective_user.id):
        await update.message.reply_text("❌ ظرفیت جلسه پر است (حداکثر ۸ بازیکن).")
        return ConversationHandler.END
    if session.has_char(update.effective_user.id):
        await update.message.reply_text(
            "🧙 تو قبلاً کاراکتر داری. با `/newchar` می‌تونی از اول بسازی.\n"
            "برای دیدنش: `/sheet`"
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "🧙 **ساخت کاراکتر جدید**\n\n"
        "قانون: ۳۰ ثانیه فکر کن، اسمت رو بفرست!\n"
        "مثلاً: «آرین»\n\n"
        "برای انصراف: /cancel"
    )
    return NAME


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["char_name"] = update.message.text.strip()[:30]
    await update.message.reply_text(
        f"خوش اومدی، **{context.user_data['char_name']}**! 👋\n\n"
        "حالا نژادت رو انتخاب کن:",
        reply_markup=race_keyboard(),
    )
    return RACE


async def race_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    race_key = query.data.split(":", 1)[1]
    context.user_data["char_race"] = race_key
    race = RACES[race_key]
    await query.edit_message_text(
        f"{race['emoji']} **نژاد: {race['fa']}**\n"
        f"بونوس‌ها: {', '.join(f'{k} +{v}' for k, v in race['bonus'].items())}\n"
        f"ویژگی: {', '.join(race['features'])}\n\n"
        "حالا کلاس رو انتخاب کن:",
        reply_markup=class_keyboard(),
    )
    return CLASS


async def class_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    class_key = query.data.split(":", 1)[1]
    context.user_data["char_class"] = class_key
    cls = CLASSES[class_key]
    await query.edit_message_text(
        f"{cls['emoji']} **کلاس: {cls['fa']}** (HP پایه: {cls['hit_die']})\n"
        f"ویژگی‌ها: {', '.join(cls['features'])}\n\n"
        "سلاحت رو انتخاب کن:",
        reply_markup=weapon_keyboard(class_key),
    )
    return WEAPON_CHOICE


async def weapon_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    weapon_key = query.data.split(":", 1)[1]
    session = _get_session(update, context)
    if not session:
        await query.edit_message_text("❌ جلسه پیدا نشد. دوباره `/join` بزن.")
        return ConversationHandler.END

    name = context.user_data.get("char_name", "بی‌نام")
    race = context.user_data.get("char_race")
    cls = context.user_data.get("char_class")
    character = Character(name=name, race=race, cls=cls, weapon=weapon_key)
    session.players[str(update.effective_user.id)]["char"] = character
    session.state = "playing" if session.state == "lobby" and session.char_count() >= 1 else session.state
    session.add_log("سیستم", f"{name} به گروه پیوست ({race}/{cls})")
    context.bot_data["store"].save(session)

    await query.edit_message_text(
        f"🎉 **کاراکتر ساخته شد!**\n\n{character.sheet_text()}\n\n"
        "هر وقت آماده بودید DM می‌تونه با `/scenario` سناریو بسازه و ماجرا شروع شه. 🐉"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 ساخت کاراکتر لغو شد.")
    return ConversationHandler.END


conv_character = ConversationHandler(
    entry_points=[
        CommandHandler("newchar", _start_flow),
        CommandHandler("join", _start_flow),
    ],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
        RACE: [CallbackQueryHandler(race_chosen, pattern=r"^race:")],
        CLASS: [CallbackQueryHandler(class_chosen, pattern=r"^class:")],
        WEAPON_CHOICE: [CallbackQueryHandler(weapon_chosen, pattern=r"^weapon:")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_chat=True,
    conversation_timeout=600,  # اگر ۱۰ دقیقه بی‌فعالیت بماند خودکار بسته می‌شود
)
