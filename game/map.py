# -*- coding: utf-8 -*-
"""سیستم مکان‌گردی ساده — رفتن بین مناطق سناریو."""

# مکان‌های پیش‌فرض بر اساس سناریو
DEFAULT_LOCATIONS = [
    "ورودی",
    "تالار اصلی",
    "راهروی تاریک",
    "اتاق گنج",
    "پناهگاه هیولا",
]

# جهت‌ها
OPPOSITE = {"شمال": "جنوب", "جنوب": "شمال", "شرق": "غرب", "غرب": "شرق",
            "جلو": "عقب", "عقب": "جلو", "بالا": "پایین", "پایین": "بالا"}


def init_world(session):
    """موقعیت شروع را در دنیا ثبت می‌کند."""
    if not hasattr(session, "world") or session.world is None:
        session.world = {"light": "dark", "location": "", "flags": {}}
    locs = DEFAULT_LOCATIONS
    if session.scenario and session.scenario.get("locations"):
        locs = session.scenario["locations"]
    if not session.world.get("location"):
        session.world["location"] = locs[0] if locs else "ورودی"
    session.world["locations"] = locs
    session.world["visited"] = list(set([session.world["location"]]))


def current_location(session) -> str:
    init_world(session)
    return session.world.get("location", "نامعلوم")


def move_to(session, direction_or_place: str) -> str:
    """بین مکان‌ها جابجا می‌شود. خروجی: پیام توصیف."""
    init_world(session)
    locs = session.world.get("locations", DEFAULT_LOCATIONS)
    cur = session.world["location"]
    cur_idx = locs.index(cur) if cur in locs else 0

    # تشخیص جهت
    place = direction_or_place.strip()
    next_idx = cur_idx
    for d in ["شمال", "جلو", "بالا", "شرق"]:
        if d in place:
            next_idx = min(len(locs) - 1, cur_idx + 1)
            break
    for d in ["جنوب", "عقب", "پایین", "غرب"]:
        if d in place:
            next_idx = max(0, cur_idx - 1)
            break
    # اگر یک مکان مشخص گفت
    for i, loc in enumerate(locs):
        if loc in place:
            next_idx = i
            break

    new_loc = locs[next_idx]
    if new_loc == cur:
        return f"در «{cur}» هستی. راه دیگری نیست."
    session.world["location"] = new_loc
    session.world.setdefault("visited", [])
    if new_loc not in session.world["visited"]:
        session.world["visited"].append(new_loc)
    session.add_log("سیستم", f"به {new_loc} رفت")
    # اگر این مکان یک رویارویی است نبرد را آماده کن
    encounter_here = any(
        new_loc in str(e.get("name", "")) for e in
        (session.scenario or {}).get("encounters", [])
    )
    msg = f"🚶 به «{new_loc}» می‌روی."
    if encounter_here:
        msg += "\nبوی خطر می‌آید..."
    return msg


def describe(session) -> str:
    init_world(session)
    loc = session.world["location"]
    visited = session.world.get("visited", [loc])
    light = session.world.get("light", "dark")
    light_fa = {"dark": "تاریک", "torch": "روشن با مشعل"}.get(light, light)
    locs = session.world.get("locations", DEFAULT_LOCATIONS)
    idx = locs.index(loc) if loc in locs else 0
    exits = []
    if idx > 0:
        exits.append("عقب")
    if idx < len(locs) - 1:
        exits.append("جلو")
    exit_str = ", ".join(exits) if exits else "بن‌بست"
    return (f"📍 مکان: **{loc}**\n"
            f"💡 نور: {light_fa}\n"
            f"🚪 خروجی‌ها: {exit_str}\n"
            f"👣 بازدید‌شده: {', '.join(visited)}")
