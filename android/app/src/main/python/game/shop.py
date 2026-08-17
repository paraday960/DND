# -*- coding: utf-8 -*-
"""سیستم مغازه و خرید/فروش آیتم بین نبردها."""
import random

# آیتم‌های قابل خرید
SHOP_ITEMS = {
    "potion": {
        "fa": "معجون شفا", "price": 25, "emoji": "🧪",
        "desc": "۲تا۱۰ امتیاز سلامتی را بازمی‌گرداند.",
    },
    "torch": {"fa": "مشعل", "price": 5, "emoji": "🔥", "desc": "تاریکی را روشن می‌کند."},
    "rope": {"fa": "طناب", "price": 10, "emoji": "🪢", "desc": "برای صعود و تله‌ها."},
    "great_potion": {
        "fa": "معجون بزرگ شفا", "price": 75, "emoji": "🧪",
        "desc": "۸ تا۲۰ امتیاز سلامتی را بازمی‌گرداند.",
    },
    "antidote": {
        "fa": "پادزهر", "price": 40, "emoji": "💚",
        "desc": "مسمومیت را درمان می‌کند.",
    },
}

# قیمت فروش: نصف قیمت خرید
SELL_RATIO = 0.5


def shop_text(session) -> str:
    lines = ["🏪 **مغازه**", f"سکه‌های تو: **{sum(p['char'].gold for p in session.players.values() if p.get('char'))}**", ""]
    for key, it in SHOP_ITEMS.items():
        lines.append(f"{it['emoji']} **{it['fa']}** — {it['price']} سکه")
        lines.append(f"   _{it['desc']}_")
    lines.append("")
    lines.append("برای خرید: «بخر معجون» یا «خرید معجون»")
    lines.append("برای فروش: «بفروش طناب»")
    return "\n".join(lines)


def buy(ch, item_key: str, qty: int = 1) -> str:
    item = SHOP_ITEMS.get(item_key)
    if not item:
        return f"چنین آیتمی در مغازه نیست. {', '.join(SHOP_ITEMS)}"
    total = item["price"] * qty
    if ch.gold < total:
        return f"سکه کافی نداری. نیاز: {total}، داری: {ch.gold}"
    ch.gold -= total
    ch.inventory[item_key] = ch.inventory.get(item_key, 0) + qty
    return f"✅ {qty}× {item['fa']} خریدی. مانده سکه: {ch.gold}"


def sell(ch, item_key: str, qty: int = 1) -> str:
    have = ch.inventory.get(item_key, 0)
    if have <= 0:
        return "این آیتم را نداری."
    qty = min(qty, have)
    item = SHOP_ITEMS.get(item_key, {"price": 5, "fa": item_key})
    gain = int(item["price"] * SELL_RATIO) * qty
    ch.inventory[item_key] -= qty
    if ch.inventory[item_key] <= 0:
        ch.inventory.pop(item_key, None)
    ch.gold += gain
    return f"💰 {qty}× {item.get('fa', item_key)} فروختی. سکه فعلی: {ch.gold}"


def use_item(ch, item_key: str):
    if item_key == "potion":
        before = ch.hp
        ch.hp = min(ch.max_hp, ch.hp + random.randint(2, 10) + 2)
        ch.inventory["potion"] -= 1
        if ch.inventory["potion"] <= 0:
            ch.inventory.pop("potion", None)
        return f"🧪 معجون نوشیدی: +{ch.hp - before} HP (اکنون {ch.hp}/{ch.max_hp})"
    if item_key == "great_potion":
        before = ch.hp
        ch.hp = min(ch.max_hp, ch.hp + random.randint(8, 20) + 4)
        ch.inventory["great_potion"] -= 1
        if ch.inventory["great_potion"] <= 0:
            ch.inventory.pop("great_potion", None)
        return f"🧪 معجون بزرگ: +{ch.hp - before} HP (اکنون {ch.hp}/{ch.max_hp})"
    return "این آیتم هنوز قابل استفاده نیست."
