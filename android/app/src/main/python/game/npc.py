# -*- coding: utf-8 -*-
"""گفتگوی NPC با حافظه — پاسخ‌های منسجم بر اساس تاریخچه گفتگو."""
import time


def talk_to(session, npc_name: str, player_says: str, narrator) -> str:
    """با یک NPC صحبت می‌کند؛ تاریخچه را در session.npc_memory نگه می‌دارد."""
    if not hasattr(session, "npc_memory") or session.npc_memory is None:
        session.npc_memory = {}
    mem = session.npc_memory.setdefault(npc_name, {"history": [], "first_met": time.time()})
    # خلاصه تاریخچه
    recent = mem["history"][-6:]  # آخر ۶ پیام
    history_text = "\n".join(
        f"{'بازیکن' if i%2==0 else npc_name}: {m}"
        for i, m in enumerate(recent)
    )
    prompt = (
        f"تو در نقش {npc_name} در یک بازی D&D هستی. "
        f"مکان: {session.world.get('location', 'نامعلوم')}. "
        f"در ۱-۲ جمله کوتاه فارسی با لحنی مناسب پاسخ بده.\n\n"
        f"تاریخچه گفتگو:\n{history_text or '(اولین دیدار)'}\n\n"
        f"بازیکن می‌گوید: {player_says}"
    )
    try:
        reply = narrator._call(prompt, "", max_tokens=200) or "..."
    except Exception:
        reply = "..."
    mem["history"].append(player_says)
    mem["history"].append(reply)
    # محدود کردن تاریخچه
    if len(mem["history"]) > 20:
        mem["history"] = mem["history"][-20:]
    return f"🗣️ {npc_name}: {reply}"
