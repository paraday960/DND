# -*- coding: utf-8 -*-
"""کیبوردهای شیشه‌ای (Inline) ربات."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from game.rules import CLASSES, RACES, WEAPONS


def main_menu() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🎮 بازی جدید", callback_data="menu:newgame"),
         InlineKeyboardButton("👥 پیوستن", callback_data="menu:join")],
        [InlineKeyboardButton("🧙 ساخت کاراکتر", callback_data="menu:newchar"),
         InlineKeyboardButton("📜 کاراکتر من", callback_data="menu:sheet")],
        [InlineKeyboardButton("🐉 سناریوی هوش مصنوعی", callback_data="menu:scenario"),
         InlineKeyboardButton("📖 روایت داستان", callback_data="menu:story")],
        [InlineKeyboardButton("⚔️ شروع نبرد", callback_data="menu:combat"),
         InlineKeyboardButton("👥 گروه", callback_data="menu:party")],
        [InlineKeyboardButton("❓ راهنما", callback_data="menu:help")],
    ]
    return InlineKeyboardMarkup(kb)


def race_keyboard() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(
        f"{RACES[k]['emoji']} {RACES[k]['fa']} (+{', '.join(f'{v}' for v in RACES[k]['bonus'].values())})",
        callback_data=f"race:{k}")] for k in RACES]
    return InlineKeyboardMarkup(kb)


def class_keyboard() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(
        f"{CLASSES[k]['emoji']} {CLASSES[k]['fa']}",
        callback_data=f"class:{k}")] for k in CLASSES]
    return InlineKeyboardMarkup(kb)


def weapon_keyboard(cls_key: str) -> InlineKeyboardMarkup:
    allowed = CLASSES[cls_key]["weapons"]
    kb = [[InlineKeyboardButton(
        f"{WEAPONS[k]['emoji']} {WEAPONS[k]['fa']} ({WEAPONS[k]['dmg']})",
        callback_data=f"weapon:{k}")] for k in allowed]
    return InlineKeyboardMarkup(kb)
