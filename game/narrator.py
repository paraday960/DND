# -*- coding: utf-8 -*-
"""دانجن‌مستر هوشمند — اتصال به هوش مصنوعی رایگان (Mistral / Gemini / Groq / OpenRouter)
با fallback آفلاین تا بازی حتی بدون اینترنت AI هم متوقف نشود.
فقط از کتابخانه استاندارد استفاده می‌کند (urllib) — هم روی سرور، هم روی اندروید کار می‌کند."""
import json
import re
import urllib.error
import urllib.request

import config
from .models import Session

SYSTEM_PROMPT = """تو «دانجن مستر» یک بازی نقش‌آفرینی D&D 5e هستی. وظیفه‌ات روایت داستان، توصیف محیط، کنترل NPCها و دشمنان و داوری قوانین است.
قوانین تو:
- همیشه به فارسی روان، حماسی و سینمایی پاسخ بده.
- فقط بر اساس اتفاقات و متن «بافت بازی» ادامه بده؛ چیزی از خودت اختراع نکن که با بافت در تضاد باشد.
- اگر نتیجه تاس یا عددی داده شد، حتماً در روایت منعکسش کن.
- خطر و مرگ جدی اما منصفانه باشد؛ بازیکنان را بی‌دلیل نکش.
- حداکثر ۳ پاراگراف کوتاه و پرتنش بنویس.
- هرگز نگو «من یک هوش مصنوعی هستم».
- وقتی بازیکن درخواست یک اکشن ساده مثل باز کردن در یا روشن کردن مشعل می‌ده، آن را در روایت تایید کن."""

SCENARIO_PROMPT = """تو یک طراح سناریوی حرفه‌ای D&D 5e هستی. یک سناریوی کامل، سینمایی، جذاب و قابل‌بازی برای گروهی {players} نفره با سطح {level} طراحی کن.

⚠️ قوانین سخت‌گیرانه بالانس:
- فقط از این دشمنان استفاده کن: goblin, wolf, bandit, skeleton, zombie (ضعیف)، orc, giant_spider, harpy (متوسط)، troll (سخت)، dragon_young (باس آخر).
- برای گروه سطح ۱: حداکثر ۶ دشمن ضعیف یا ۲ متوسط، و اصلاً troll/dragon/harpy.
- برای سطح ۲-۳: حداکثر ۵ دشمن متوسط یا یک troll.
- برای سطح ۵+: می‌توان از troll و dragon_young فقط در فینال (Boss) استفاده کرد.
- مجموع count همه encounterها باید کمتر یا مساوی ۶ برای سطح ۱ باشد.

🎭 قوانین طراحی جذاب:
- عنوان باید کوتاه، حماسی و یادماندنی باشد.
- hook (قلاب) با یک صحنه سینمایی شروع شود — حس بو، صدا، نور، اضطراب را توصیف کن.
- goal هدف گروه را واضح و احساسی بیان کند (نفر را نجات دهید، طلسم را بشکنید، از نفرین جان سالم به در ببرید).
- locations حداقل ۳ تا ۵ مکان باشد که هر کدام حس و چالش متفاوتی دارند.
- npcs حداقل ۲ تا ۴ شخصیت زنده با نام و انگیزه (پیرمرد ترسیده، کودک گمشده، تاجر فریب‌کار، نگهبان زخمی).
- treasure شامل ۲ تا ۴ آیتم باشد: سکه، معجون شفا، مشعل، طناب، سلاح/زره ساده + شاید یک آیتم جادویی کوچک.
- 🪤 traps (تله‌ها) اجباری است: ۱ تا ۳ تله با توصیف عامل راه‌انداز، DC تشخیص، DC خنثی‌سازی، و آسیب.
- 🔀 branches (شاخه‌ها) اجباری است: ۲ تا ۳ انتخاب با عواقب متفاوت (مثلاً درِ چوبی vs راه مخفی، مذاکره با NPC vs حمله، میانبر خطرناک vs راه امن).
- 🌀 twist (پیچ داستانی) اجباری است: یک برگشت پیش‌بینی‌نشده (خیانت NPC، نفرین باستانی، متحد واقعی که دشمن بود).
- 👑 boss (باس فایت) اجباری است در آخرین مکان — یک دشمن قوی‌تر با ۱ یا ۲ همراه یا قابلیت ویژه.

خروجی فقط و فقط یک JSON معتبر فارسی باشد — بدون هیچ توضیح اضافه یا متن قبل/بعد. ساختار دقیق JSON:
{{
  "title": "عنوان حماسی کوتاه",
  "hook": "توصیف سینمایی شروع ماجرا در 2-3 جمله",
  "goal": "هدف نهایی گروه در 1 جمله",
  "locations": [
    {{"name": "نام مکان", "description": "توصیف حس، بو، صدا", "encounter_hint": "چه تهدیدی در آن کمین کرده"}},
    ...
  ],
  "npcs": [
    {{"name": "نام", "role": "نقش", "secret": "انگیزه یا راز پنهان"}},
    ...
  ],
  "encounters": [
    {{"name": "goblin", "count": 2, "ac": 15, "hp": 7, "dmg": "1d6+2", "xp": 50, "location": "نام مکان"}},
    ...
  ],
  "treasure": [
    {{"item": "gold", "qty": 150, "description": "کیسه سکه‌های قدیمی"}},
    {{"item": "potion", "qty": 2, "description": "دو معجون شفای شیشه‌ای در جیب مرده"}},
    ...
  ],
  "traps": [
    {{"name": "نام تله", "location": "نام مکان", "trigger": "عامل راه‌انداز", "detect_dc": 13, "disarm_dc": 12, "damage": "1d6+2", "effect": "توصیف فعال شدن"}},
    ...
  ],
  "branches": [
    {{"text": "توضیح انتخاب (مثلاً: از در اصلی وارد شویم)", "consequence": "عواقب کوتاه"}},
    {{"text": "انتخاب دیگر", "consequence": "عواقب"}},
    ...
  ],
  "twist": "پیچ داستانی در ۱ جمله",
  "boss": {{"name": "goblin", "count": 1, "ac": 15, "hp": 7, "dmg": "1d6+2", "xp": 50, "ability": "قابلیت ویژه باس در 1 جمله", "location": "نام مکان نهایی"}}
}}
نام دشمنان دقیقاً از این لیست انتخاب شود: goblin, orc, skeleton, zombie, wolf, bandit, harpy, troll, giant_spider, dragon_young."""


def _post_json(url: str, body: dict, headers: dict = None, timeout: int = 45) -> str:
    """درخواست POST ساده با کتابخانه استاندارد — بدون نیاز به requests."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]}") from e


def _extract_json(text: str) -> dict:
    """سخت‌گیرانه‌ترین پارس JSON: بلوک بین { } را پیدا و تلاش می‌کند."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    for candidate in (match.group(0), text.strip()):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _normalize_scenario(data: dict, MONSTERS: dict, players: int, level: int) -> dict:
    """سناریوی دریافتی از AI را به فرمت داخلی یکدست تبدیل می‌کند."""
    # Normalize locations
    raw_locs = data.get("locations") or []
    locations = []
    if isinstance(raw_locs, list):
        for l in raw_locs:
            if isinstance(l, dict):
                locations.append(l)
            else:
                locations.append({"name": str(l), "description": "", "encounter_hint": ""})
    # Normalize NPCs
    raw_npcs = data.get("npcs") or []
    npcs = []
    for n in raw_npcs:
        if isinstance(n, dict):
            npcs.append(n)
        else:
            npcs.append({"name": str(n), "role": "", "secret": ""})
    # Clean encounters
    # سقف تعداد دشمن متناسب با سطح (سخت‌گیری برای سطح پایین)
    if level <= 1:
        max_monsters = 6
    elif level <= 3:
        max_monsters = 7
    elif level <= 5:
        max_monsters = 8
    else:
        max_monsters = 6 + level
    clean = []
    total_count = 0
    for e in (data.get("encounters") or []):
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "")).lower().strip()
        if name not in MONSTERS:
            continue
        base = MONSTERS[name]
        # بالانس: دشمن خیلی قوی برای سطح پایین مجاز نیست
        if level <= 2 and name in ("troll", "dragon_young", "harpy"):
            continue
        try:
            count = max(1, min(6, int(e.get("count", 1))))
            ac = max(8, min(25, int(e.get("ac", base["ac"]))))
            hp = max(1, min(400, int(e.get("hp", base["hp"]))))
            xp = max(1, int(e.get("xp", base["xp"])))
        except (TypeError, ValueError):
            count, ac, hp, xp = 1, base["ac"], base["hp"], base["xp"]
        if total_count + count > max_monsters:
            count = max(0, max_monsters - total_count)
        if count <= 0:
            break
        entry = {"name": name, "count": count, "ac": ac, "hp": hp,
                 "dmg": e.get("dmg", base["dmg"]), "xp": xp, "cr": base.get("cr", 0.25)}
        if e.get("location"):
            entry["location"] = str(e["location"])
        clean.append(entry)
        total_count += count
        if total_count >= max_monsters:
            break
    # Boss (متناسب با سطح)
    boss = data.get("boss")
    boss_entry = None
    if isinstance(boss, dict):
        name = str(boss.get("name", "")).lower().strip()
        if name in MONSTERS:
            base = MONSTERS[name]
            # محدودیت انتخاب باس بر اساس سطح
            forbidden_for_level = []
            if level <= 1:
                forbidden_for_level = ["troll", "dragon_young", "harpy", "giant_spider", "orc"]
            elif level <= 2:
                forbidden_for_level = ["troll", "dragon_young", "harpy"]
            elif level <= 4:
                forbidden_for_level = ["dragon_young"]
            if name not in forbidden_for_level and total_count < max_monsters:
                try:
                    bac = max(8, min(28, int(boss.get("ac", base["ac"] + max(1, level - 1)))))
                    bhp = max(1, min(500, int(boss.get("hp", base["hp"] + level*6))))
                    bxp = max(1, int(boss.get("xp", base["xp"] * max(2, level))))
                    bc = 1
                    boss_entry = {"name": name, "count": bc, "ac": bac, "hp": bhp,
                                  "dmg": boss.get("dmg", base["dmg"]), "xp": bxp,
                                  "cr": base.get("cr", 0.25), "is_boss": True,
                                  "ability": boss.get("ability", "ضربه سخت")}
                    if boss.get("location"):
                        boss_entry["location"] = str(boss["location"])
                except (TypeError, ValueError):
                    boss_entry = None
    if boss_entry:
        clean.append(boss_entry)
        total_count += 1
        data["boss"] = boss_entry
    else:
        data["boss"] = None
    data["encounters"] = clean
    # Normalize treasure
    raw_t = data.get("treasure")
    if isinstance(raw_t, str):
        treasure_list = [{"item": "gold", "qty": 50 + level*30, "description": raw_t}]
    elif isinstance(raw_t, list):
        treasure_list = []
        for t in raw_t:
            if isinstance(t, dict) and t.get("item"):
                treasure_list.append(t)
    else:
        treasure_list = [{"item": "gold", "qty": 50 + level*30, "description": "سکه‌های قدیمی"}]
    data["treasure"] = treasure_list
    # Normalize traps
    raw_traps = data.get("traps")
    traps = []
    if isinstance(raw_traps, list):
        for t in raw_traps:
            if isinstance(t, dict) and t.get("name"):
                try:
                    traps.append({
                        "name": str(t.get("name")),
                        "location": str(t.get("location", "")),
                        "trigger": str(t.get("trigger", "قدم گذاشتن")),
                        "detect_dc": int(t.get("detect_dc", 13)),
                        "disarm_dc": int(t.get("disarm_dc", 12)),
                        "damage": str(t.get("damage", "1d6")),
                        "effect": str(t.get("effect", "آسیب به بازیکن")),
                        "triggered": False,
                        "disarmed": False,
                    })
                except (TypeError, ValueError):
                    continue
    data["traps"] = traps
    # Normalize branches
    raw_b = data.get("branches")
    branches = []
    if isinstance(raw_b, list):
        for b in raw_b:
            if isinstance(b, dict) and b.get("text"):
                branches.append({"text": str(b.get("text")), "consequence": str(b.get("consequence", ""))})
    data["branches"] = branches
    # Twist
    data["twist"] = str(data.get("twist") or "")
    # locations/npcs guarantees
    if not locations:
        locations = [{"name": "ورودی", "description": "یک ورودی تاریک", "encounter_hint": ""}]
    data["locations"] = locations
    data["npcs"] = npcs or [{"name": "غریبه", "role": "راهنما", "secret": "چیزی می‌داند"}]
    # اطمینان از وجود فیلدهای الزامی
    data["title"] = data.get("title") or "ماجرای بی‌نام"
    data["hook"] = data.get("hook") or "شما در ورودی یک مکان تاریک ایستاده‌اید."
    data["goal"] = data.get("goal") or "به انتهای مکان برسید و زنده بیرون بیایید."
    return data


class Narrator:
    def __init__(self):
        self.provider = config.AI_PROVIDER if config.AI_PROVIDER != "none" else None
        key_map = {
            "gemini": config.GEMINI_API_KEY,
            "groq": config.GROQ_API_KEY,
            "openrouter": config.OPENROUTER_API_KEY,
            "mistral": config.MISTRAL_API_KEY,
        }
        self.api_key = key_map.get(self.provider, "")
        if not self.api_key:
            self.provider = None  # حالت آفلاین

    @property
    def available(self) -> bool:
        return self.provider is not None

    # ---------- لایه درخواست ----------
    def _call(self, system: str, user: str, max_tokens: int = 900) -> str:
        if self.provider == "gemini":
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{config.GEMINI_MODEL}:generateContent?key={self.api_key}")
            body = {
                "contents": [{"role": "user", "parts": [{"text": system + "\n\n" + user}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": max_tokens},
            }
            text = _post_json(url, body)
            data = json.loads(text)
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return None

        if self.provider in ("groq", "openrouter", "mistral"):
            if self.provider == "groq":
                url = "https://api.groq.com/openai/v1/chat/completions"
                model = config.GROQ_MODEL
            elif self.provider == "mistral":
                url = "https://api.mistral.ai/v1/chat/completions"
                model = config.MISTRAL_MODEL
            else:
                url = "https://openrouter.ai/api/v1/chat/completions"
                model = config.OPENROUTER_MODEL
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.9,
                "max_tokens": max_tokens,
            }
            headers = {"Authorization": f"Bearer {self.api_key}"}
            if self.provider == "openrouter":
                headers["HTTP-Referer"] = "https://t.me/"
                headers["X-Title"] = "DnD Telegram Bot"
            text = _post_json(url, body, headers=headers)
            data = json.loads(text)
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                return None
        return None

    # ---------- عملیات عمومی ----------
    def narrate(self, session: Session, action: str) -> str:
        """پاسخ دانجن‌مستر به یک اقدام بازیکن."""
        from .world import try_environment_action
        if action and len(action) < 80:
            for p in session.players.values():
                ch = p.get("char")
                if ch:
                    env = try_environment_action(session, ch, action)
                    if env:
                        session.add_log(ch.name, action)
                        session.add_log("DM", env)
                        return env
                    break
        context = self._context(session)
        user_msg = (
            f"بافت بازی:\n{context}\n\n"
            f"اقدام بازیکن: {action}\n\n"
            "حالا روایت کن. اگر این اقدام وضعیت دنیا را تغییر می‌دهد (مثل روشن کردن مشعل، "
            "باز کردن در، جابجایی مکان، برداشتن آیتم) در روایتت به‌وضوح آن تغییر را منعکس کن و "
            "همان وضعیت جدید را در ادامه داستان در نظر بگیر."
        )
        try:
            text = self._call(SYSTEM_PROMPT, user_msg)
            if text:
                low = text.lower()
                if "مشعل" in action or "روشن" in action or "افروز" in action or "آتش" in action:
                    if any(w in text for w in ["روشن", "شعله", "نور", "آتش", "افروخت"]):
                        if hasattr(session, "world"):
                            session.world["light"] = "torch"
                if "تاریک" in text and "تاریکی" in text and hasattr(session, "world"):
                    if session.world.get("light") != "torch":
                        session.world["light"] = "dark"
                session.add_log("DM", text.replace("\n", " ")[:400])
                return text.strip()
        except Exception:
            pass
        return self._fallback_narrate(session, action)

    def scenario(self, session: Session, request: str = "") -> dict:
        """ساخت سناریوی کامل توسط هوش مصنوعی (یا آفلاین)."""
        from .rules import MONSTERS
        chars = [p["char"] for p in session.players.values() if p.get("char")]
        players = max(1, len(chars))
        level = max(1, min(20, (sum(c.level for c in chars) // players) if chars else 1))
        user_msg = SCENARIO_PROMPT.format(players=players, level=level)
        if request.strip():
            user_msg += f"\n\nالزامات اضافه از طرف DM: {request}"
        try:
            text = self._call("", user_msg, max_tokens=2000)
            data = _extract_json(text) if text else None
            if data and data.get("title"):
                data = _normalize_scenario(data, MONSTERS, players, level)
                if data.get("encounters"):
                    session.scenario = data
                    locs = data.get("locations") or []
                    if locs and isinstance(locs, list):
                        first_loc = locs[0].get("name") if isinstance(locs[0], dict) else str(locs[0])
                        session.world["location"] = first_loc
                        session.world["locations"] = [
                            (l.get("name") if isinstance(l, dict) else str(l)) for l in locs
                        ]
                        session.world["visited"] = [first_loc]
                    session.world.setdefault("flags", {})["scenario_built"] = True
                    return data
        except Exception:
            pass
        from .rules import MONSTERS as _M
        chars = [p["char"] for p in session.players.values() if p.get("char")]
        _p = max(1, len(chars))
        _l = max(1, min(20, (sum(c.level for c in chars) // _p) if chars else 1))
        fb = _normalize_scenario(self._fallback_scenario(session), _M, _p, _l)
        # همگام‌سازی world در fallback هم انجام شود
        locs = fb.get("locations") or []
        if locs:
            first_loc = locs[0].get("name") if isinstance(locs[0], dict) else str(locs[0])
            session.world["location"] = first_loc
            session.world["locations"] = [
                (l.get("name") if isinstance(l, dict) else str(l)) for l in locs
            ]
            session.world["visited"] = [first_loc]
        session.world.setdefault("flags", {})["scenario_built"] = True
        session.scenario = fb
        return fb

    def recap(self, session: Session) -> str:
        """خلاصه وضعیت فعلی ماجرا."""
        context = self._context(session)
        try:
            text = self._call(
                SYSTEM_PROMPT,
                f"بافت بازی:\n{context}\n\nحالا در ۲ پاراگراف خلاصه کن گروه الان کجاست، چه اتفاقی افتاده و چه مسیرهایی پیش رو دارد.",
            )
            if text:
                return text.strip()
        except Exception:
            pass
        return "📌 " + session.log_text(8)

    # ---------- بافت بازی برای AI ----------
    def _context(self, session: Session) -> str:
        lines = [f"عنوان ماجرا: {session.name}"]
        if session.scenario:
            lines.append(f"سناریو: {session.scenario.get('title')} — هدف: {session.scenario.get('goal')}")
            locs = session.scenario.get("locations") or []
            if locs and isinstance(locs[0], dict):
                loc_names = [l.get("name", "") for l in locs]
            else:
                loc_names = [str(l) for l in locs]
            if loc_names:
                lines.append(f"مکان‌ها: {', '.join(loc_names)}")
            if session.scenario.get('encounters'):
                enc = ", ".join(f"{e.get('count',1)}× {e.get('name')}" for e in session.scenario['encounters'])
                lines.append(f"دشمنان سناریو: {enc}")
            if session.scenario.get("twist"):
                lines.append(f"(پیچ پنهان برای DM: {session.scenario.get('twist')})")
        w = getattr(session, 'world', None) or {}
        if w:
            light_fa = {"dark": "تاریک", "torch": "روشن با مشعل", "bright": "روشن"}.get(w.get("light"), w.get("light", ""))
            if light_fa:
                lines.append(f"نور محیط: {light_fa}")
            if w.get("location"):
                lines.append(f"مکان فعلی: {w['location']}")
            if w.get("flags"):
                lines.append("وضعیت‌ها: " + ", ".join(f"{k}={v}" for k, v in w["flags"].items()))
        chars = []
        for p in session.players.values():
            ch = p["char"]
            if ch:
                inv = ", ".join(f"{k}:{v}" for k, v in ch.inventory.items() if v > 0) or "خالی"
                chars.append(f"{ch.name} ({ch.race}, {ch.cls} سطح {ch.level}, HP {ch.hp}/{ch.max_hp}, موجودی: {inv})")
        if chars:
            lines.append("گروه: " + ", ".join(chars))
        lines.append("رویدادهای اخیر:")
        lines.append(session.log_text(15))
        return "\n".join(lines)

    # ---------- حالت آفلاین ----------
    def _fallback_narrate(self, session: Session, action: str) -> str:
        return (
            f"📖 روایت (حالت آفلاین):\n\n"
            f"«{action}» — باد سردی از میان ویرانه‌ها می‌وزد و صدای قدم‌هایت در سکوت می‌پیچد. "
            f"هیچ‌کس از نتیجه این کار مطمئن نیست، اما راه برگشتی نیست.\n\n"
            f"💡 برای روایت سینمایی با هوش مصنوعی، کلید API را در فایل .env تنظیم کن "
            f"(راهنما: README.md — بخش هوش مصنوعی رایگان)."
        )

    def _fallback_scenario(self, session=None) -> dict:
        players = 1
        avg_level = 1
        if session is not None:
            chars = [p["char"] for p in session.players.values() if p.get("char")]
            players = max(1, len(chars))
            avg_level = max(1, sum(c.level for c in chars) // max(1, len(chars)))

        from .rules import MONSTERS
        budget = 100 * players * avg_level

        def pick(monster_key, max_count):
            m = MONSTERS[monster_key]
            per = m.get("xp", 50)
            n = max(1, min(max_count, budget // max(per, 1)))
            return {"name": monster_key, "count": n, "ac": m["ac"],
                    "hp": m["hp"], "dmg": m["dmg"], "xp": per, "cr": m.get("cr", 0.25)}

        if avg_level <= 2:
            enc = [
                {**pick("goblin", max(2, players)), "location": "پاکسازی"},
                {**pick("wolf", max(1, players-1)), "location": "پاکسازی"},
            ]
            title = "کمینگاه گابلین‌ها در جنگل کهن"
            hook = "کاروانی در دل جنگل گم شده و دود آتش گابلین‌ها از میان درختان دیده می‌شود. بوته‌های خشک خون‌آلود هستند."
            goal = "کاروانیان را نجات دهید و کمینگاه گابلین‌ها را در هم بشکنید."
            locations = [
                {"name": "جاده جنگلی", "description": "درختان انبوه راه را احاطه کرده‌اند؛ برگ‌های خشک زیر پا صدا می‌کنند.", "encounter_hint": "ردپا تازه"},
                {"name": "پاکسازی", "description": "فضای باز کوچکی با آتش خاموش و چند چادر پاره.", "encounter_hint": "کمین گابلین"},
                {"name": "غار کمینگاه", "description": "ورودی تاریک یک غار کوچک که صدای جیغ از آن می‌آید.", "encounter_hint": "رئیس گابلین"},
            ]
            treasure = [
                {"item": "gold", "qty": 80 + players*20, "description": "سکه‌های مسروقه کاروان"},
                {"item": "potion", "qty": 2, "description": "دو معجون شفا در چادر رئیس"},
                {"item": "torch", "qty": 2, "description": "دو مشعل روشن‌نشده"},
            ]
            npcs = [
                {"name": "کریم تاجر", "role": "بازرگان اسیر", "secret": "یک طومار جادویی در جیب دارد پنهان کرده"},
                {"name": "پیرمرد چوپان", "role": "راهنما", "secret": "نقشه درون غار را می‌داند"},
            ]
            traps = [
                {"name": "تله طنابی", "location": "جاده جنگلی", "trigger": "قدم گذاشتن روی برگ‌های پوشیده", "detect_dc": 12, "disarm_dc": 10, "damage": "1d4", "effect": "پا به هوا می‌روی و آسیب می‌بینی", "triggered": False, "disarmed": False},
            ]
            branches = [
                {"text": "از راه اصلی جلو برویم", "consequence": "مستقیم به کمین گابلین‌ها می‌رسیم اما ممکن است در تله بیفتیم"},
                {"text": "دزدکی از کنار درختان وارد غار شویم", "consequence": "غافلگیر می‌کنیم اما راه پر از تله است"},
                {"text": "اول با پیرمرد چوپان صحبت کنیم", "consequence": "نقشه کمین را می‌فهمیم"},
            ]
            twist = "کریم تاجر در واقع خودش با گابلین‌ها همکاری می‌کرده و کاروان را به کمین کشانده."
            # باس سطح ۱: یک گابلین قوی‌تر که در آخرین گروه ادغام می‌شود
            if enc:
                # آخرین گروه گابلین را تقویت می‌کنیم و یکی از آنها را باس قرار می‌دهیم
                enc[-1]["count"] = max(1, enc[-1]["count"])
                boss = {"name": "goblin", "count": 1, "ac": 14, "hp": 12, "dmg": "1d6+2", "xp": 100,
                        "cr": 0.5, "is_boss": True, "ability": "فریاد کمک: در نوبت اول یک گابلین دیگر صدا می‌زند", "location": "غار کمینگاه"}
            else:
                boss = None
        elif avg_level <= 4:
            enc = [
                {**pick("skeleton", 2), "location": "پایین معبد"},
                {**pick("bandit", players + 1), "location": "تالار اصلی"},
            ]
            title = "معبد فراموش‌شده"
            hook = "زمزمه‌هایی از یک معبد متروک به گوش می‌رسد — راهزنان و اسکلت‌ها آنجا لانه کرده‌اند. سنگ نوشته‌های خونین ورود را منع می‌کنند."
            goal = "معبد را پاکسازی کنید و اثر باستانی را بازیابید."
            locations = [
                {"name": "پایین معبد", "description": "پله‌های سنگی شکسته که به زیر زمین می‌رود.", "encounter_hint": "دو اسکلت نگهبان"},
                {"name": "تالار اصلی", "description": "سالنی بزرگ با ستون‌های شکسته و مجسمه‌های بی‌چهره.", "encounter_hint": "راهزنان مستقر"},
                {"name": "محراب مرموز", "description": "اتاقی مخفی با یک اثر باستانی در مرکز.", "encounter_hint": "جادوی تاریک"},
            ]
            treasure = [
                {"item": "gold", "qty": 200 + players*30, "description": "سکه‌های باستانی"},
                {"item": "potion", "qty": 3, "description": "سه معجون شفا"},
            ]
            npcs = [
                {"name": "راهب ترسیده", "role": "تنها بازمانده", "secret": "اثر باستانی نفرین شده"},
            ]
            traps = [
                {"name": "تیغه دیواری", "location": "پایین معبد", "trigger": "فشار دادن سنگ اشتباه", "detect_dc": 14, "disarm_dc": 12, "damage": "1d8", "effect": "تیغه از دیوار بیرون می‌زند", "triggered": False, "disarmed": False},
            ]
            branches = [
                {"text": "مستقیم به تالار حمله کنیم", "consequence": "نبرد سنگین اما غافلگیری ندارند"},
                {"text": "از راه مخفی به محراب برویم", "consequence": "اثر را می‌دزدیم اما راهزنان باخبر می‌شوند"},
            ]
            twist = "اثر باستانی کسی را که لمسش می‌کند تسخیر می‌کند."
            boss = {"name": "bandit", "count": 1, "ac": 14, "hp": 22, "dmg": "1d8+2", "xp": 200,
                    "cr": 1, "is_boss": True, "ability": "فریاد کمک و یک همراه اضافی", "location": "تالار اصلی"}
        else:
            enc = [
                {**pick("giant_spider", 1), "location": "پای برج"},
                {**pick("orc", players), "location": "پلکان مارپیچ"},
            ]
            title = "برج هارپی‌ها"
            hook = "هارپی‌ها مسافران را می‌ربایند و در برج بلند زندانی کرده‌اند. پرهای خونین اطراف برج پراکنده است."
            goal = "به بالای برج صعود کنید، هارپی‌ها را شکست دهید و اسیران را نجات دهید."
            locations = [
                {"name": "پای برج", "description": "سنگ‌های شکسته و لانه‌های تخریب شده.", "encounter_hint": "عنکبوت‌ها"},
                {"name": "پلکان مارپیچ", "description": "پله‌های باریک و پیچ‌درپیچ درون برج.", "encounter_hint": "کمین اورک‌ها"},
                {"name": "آشیانه هارپی", "description": "بالای برج، محل زندگی هارپی‌ها.", "encounter_hint": "هارپی‌ها و زندانیان"},
            ]
            treasure = [
                {"item": "gold", "qty": 500 + players*50, "description": "گنج انباشت شده سال‌ها"},
                {"item": "potion", "qty": 4, "description": "چهار معجون"},
            ]
            npcs = [
                {"name": "شاهدخت اسیر", "role": "زندانی", "secret": "پدر شاه جایزه بزرگ برای نجاتش می‌دهد"},
            ]
            traps = [
                {"name": "سقف لرزان", "location": "پلکان مارپیچ", "trigger": "فشار به پله وسط", "detect_dc": 15, "disarm_dc": 13, "damage": "2d6", "effect": "سنگ‌ها از سقف می‌ریزند", "triggered": False, "disarmed": False},
            ]
            branches = [
                {"text": "با طناب از دیواره بالا برویم", "consequence": "سریع‌تر اما خطر سقوط"},
                {"text": "از پلکان اصلی با احتیاط", "consequence": "امن‌تر اما تله‌ها در راه"},
            ]
            twist = "شاهدخت خودش یک جادوگر است و هارپی‌ها را احضار کرده بود."
            boss = {"name": "harpy", "count": 1, "ac": 13, "hp": 38, "dmg": "1d6+2", "xp": 400,
                    "cr": 1, "is_boss": True, "ability": "آواز فریبنده که بازیکنان را به سمت لبه برج می‌کشاند", "location": "آشیانه هارپی"}

        if boss:
            enc.append(boss)

        return {
            "title": title, "hook": hook, "goal": goal,
            "locations": locations, "npcs": npcs,
            "encounters": enc, "treasure": treasure,
            "traps": traps, "branches": branches,
            "twist": twist, "boss": boss,
        }
