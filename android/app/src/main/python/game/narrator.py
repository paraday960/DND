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
- هرگز نگو «من یک هوش مصنوعی هستم»."""

SCENARIO_PROMPT = """یک سناریوی کامل و جذاب D&D 5e برای گروهی {players} نفره با میانگین سطح {level} طراحی کن.
سناریو باید تاریک، پرتعلیق و قابل‌بازی باشد. فقط یک JSON معتبر و بدون متن اضافه برگردان با این ساختار دقیق:
{{
  "title": "عنوان سناریو",
  "hook": "دلیل شروع ماجرا (چند جمله)",
  "goal": "هدف نهایی گروه",
  "locations": ["مکان ۱", "مکان ۲", "مکان ۳"],
  "npcs": ["NPC ۱", "NPC ۲"],
  "encounters": [
    {{"name": "نام دشمن", "count": 3, "ac": 12, "hp": 10, "dmg": "1d6+2", "xp": 50, "cr": 0.25}}
  ],
  "treasure": "گنج و پاداش نهایی"
}}
نام دشمن‌ها را از این لیست انتخاب کن (همان املای لاتین): goblin, orc, skeleton, zombie, wolf, bandit, harpy, troll, dragon_young, giant_spider"""


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
        context = self._context(session)
        user_msg = f"بافت بازی:\n{context}\n\nاقدام بازیکن: {action}\n\nحالا روایت کن."
        try:
            text = self._call(SYSTEM_PROMPT, user_msg)
            if text:
                session.add_log("DM", text.replace("\n", " ")[:400])
                return text.strip()
        except Exception:
            pass
        return self._fallback_narrate(session, action)

    def scenario(self, session: Session, request: str = "") -> dict:
        """ساخت سناریوی کامل توسط هوش مصنوعی."""
        level = max(1, min(20, session.char_count() or 1))
        user_msg = SCENARIO_PROMPT.format(
            players=session.char_count() or 1, level=level
        )
        if request.strip():
            user_msg += f"\n\nالزامات اضافه از طرف DM: {request}"
        try:
            text = self._call("", user_msg, max_tokens=1400)
            data = _extract_json(text) if text else None
            if data and data.get("title"):
                return data
        except Exception:
            pass
        return self._fallback_scenario(session)

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
            lines.append(f"مکان‌ها: {', '.join(session.scenario.get('locations', []))}")
        chars = []
        for p in session.players.values():
            ch = p["char"]
            if ch:
                chars.append(f"{ch.name} ({ch.race}, {ch.cls} سطح {ch.level}, HP {ch.hp}/{ch.max_hp})")
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
        # مقیاس دشمنان متناسب با گروه (سطح و تعداد) تا نبرد اول قابل باخت نباشد
        players = 1
        avg_level = 1
        if session is not None:
            chars = [p["char"] for p in session.players.values() if p.get("char")]
            players = max(1, len(chars))
            avg_level = max(1, sum(c.level for c in chars) // max(1, len(chars)))

        # بودجه XP ساده: تقریباً 100 * تعداد * سطح (متوسط)
        budget = 100 * players * avg_level

        def pick(monster_key, max_count):
            from .rules import MONSTERS
            m = MONSTERS[monster_key]
            per = m.get("xp", 50)
            n = max(1, min(max_count, budget // max(per, 1)))
            return {"name": monster_key, "count": n, "ac": m["ac"],
                    "hp": m["hp"], "dmg": m["dmg"], "xp": per, "cr": m.get("cr", 0.25)}

        if avg_level <= 2:
            enc = [pick("goblin", max(2, players)), pick("wolf", players)]
            title = "کمینگاه گابلین‌ها در جنگل کهن"
            hook = "کاروانی در دل جنگل گم شده و دود آتش گابلین‌ها از میان درختان دیده می‌شود."
            goal = "کاروانیان را نجات دهید و کمینگاه گابلین‌ها را در هم بشکنید."
            locations = ["دهکده", "جاده جنگلی", "کمینگاه گابلین‌ها"]
            treasure = "۲۰۰ سکه و یک خنجر جادویی"
        elif avg_level <= 4:
            enc = [pick("bandit", players + 1), pick("wolf", 2), pick("skeleton", 2)]
            title = "معبد فراموش‌شده"
            hook = "زمزمه‌هایی از یک معبد متروک به گوش می‌رسد — راهزنان و اسکلت‌ها آنجا لانه کرده‌اند."
            goal = "معبد را پاکسازی کنید و اثر باستانی را بازیابید."
            locations = ["روستای پای کوه", "پل ویرانه", "تالار اصلی معبد"]
            treasure = "۶۰۰ سکه، طومار طلسم، زره سبک +۱"
        elif avg_level <= 7:
            enc = [pick("orc", players), pick("harpy", 2), pick("giant_spider", 2)]
            title = "برج هارپی‌ها"
            hook = "هارپی‌ها مسافران هوایی را می‌ربایند و در برج بلند زندانی کرده‌اند."
            goal = "به بالای برج صعود کنید، هارپی‌ها را شکست دهید و اسیران را نجات دهید."
            locations = ["پای برج", "پلکان مارپیچ", "آشیانه هارپی"]
            treasure = "۱۵۰۰ سکه، کمان +۱"
        else:
            enc = [pick("troll", 2), pick("orc", players), pick("dragon_young", 1)]
            title = "خزانه اژدهای مه‌آلود"
            hook = "پیکرهای نیمه‌جان در مسیر دهکده پیدا شده؛ اژدهایی در کوهستان لانه کرده."
            goal = "وارد کوهستان شوید، با ترول‌ها و اژدها روبه‌رو شوید و گنج را بازگردانید."
            locations = ["دهکده سوخته", "تنگه استخوان‌ها", "لانه اژدها"]
            treasure = "۵۰۰۰ سکه، شمشیر +۱، طومار باستانی"

        npcs = ["پیرمرد فال‌گیر", "نگهبان مضطرب", "بازمانده کاروان"]
        return {
            "title": title, "hook": hook, "goal": goal,
            "locations": locations, "npcs": npcs,
            "encounters": enc, "treasure": treasure,
        }
