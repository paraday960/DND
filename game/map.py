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


def _loc_name(loc):
    """نام مکان را از dict یا str استخراج می‌کند."""
    if isinstance(loc, dict):
        return loc.get("name", str(loc))
    return str(loc)


def _loc_list(raw):
    """لیست نام مکان‌ها (رشته) را از ورودی dict یا str برمی‌گرداند."""
    if not raw:
        return list(DEFAULT_LOCATIONS)
    return [_loc_name(l) for l in raw]


def init_world(session):
    """موقعیت شروع را در دنیا ثبت می‌کند."""
    if not hasattr(session, "world") or session.world is None:
        session.world = {"light": "dark", "location": "", "flags": {}}
    locs = _loc_list((session.scenario or {}).get("locations")) if session.scenario else list(DEFAULT_LOCATIONS)
    if not session.world.get("location"):
        session.world["location"] = locs[0] if locs else "ورودی"
    # اگر location یک dict ذخیره شده بود به str تبدیل کن
    session.world["location"] = _loc_name(session.world["location"])
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
    is_new = new_loc not in session.world["visited"]
    if is_new:
        session.world["visited"].append(new_loc)
    session.add_log("سیستم", f"به {new_loc} رفت")

    # توصیف مکان از سناریو
    loc_desc = ""
    loc_hint = ""
    if session.scenario:
        for l in (session.scenario.get("locations") or []):
            if _loc_name(l) == new_loc and isinstance(l, dict):
                loc_desc = l.get("description", "")
                loc_hint = l.get("encounter_hint", "")
                break

    # بررسی تله در مکان جدید
    trap_msg = _check_move_trap(session, new_loc)

    # بررسی رویارویی در این مکان
    enc_here = [e for e in ((session.scenario or {}).get("encounters") or [])
                if _loc_matches(e.get("location", ""), new_loc) and not e.get("defeated")]

    msg = f"🚶 به «{new_loc}» می‌روی."
    if loc_desc and is_new:
        msg += f"\n_{loc_desc}_"
    if trap_msg:
        msg += "\n\n" + trap_msg
    if enc_here:
        total = sum(e.get("count", 1) for e in enc_here)
        b = any(e.get("is_boss") for e in enc_here)
        msg += f"\n⚠️ {'باس فایت!' if b else 'کمین!'} حدود {total} دشمن در اینجا حضور دارند! با «شروع نبرد» یا «حمله» وارد شوید."
    elif loc_hint and is_new:
        msg += f"\n👁 {loc_hint}"
    return msg


def _loc_matches(loc_field: str, target: str) -> bool:
    """آیا لوکیشن یک encounter با مکان فعلی می‌خواند؟"""
    if not loc_field:
        return False
    return target in loc_field or loc_field in target


def _check_move_trap(session, new_loc: str) -> str:
    """هنگام ورود به مکان جدید، تله‌های آن مکان را بررسی می‌کند (اولین قدم = تریگر)."""
    from .world import _check_trap_trigger  # واردکردن تأخیری برای جلوگیری از circular
    fake_action = f"ورود به {new_loc}"
    msg = _check_trap_trigger(session, None, fake_action, here_override=new_loc)
    return msg or ""


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
