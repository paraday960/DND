# -*- coding: utf-8 -*-
"""موتور تاس — پشتیبانی از 2d6، 1d20+3، advantage و disadvantage."""
import random
import re

_PATTERN = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$", re.I)


class DiceError(ValueError):
    pass


def roll_dice(count: int, sides: int) -> list:
    if count < 1 or count > 100:
        raise DiceError("تعداد تاس باید بین ۱ تا ۱۰۰ باشد")
    if sides < 2:
        raise DiceError("تاس باید حداقل ۲ وجه داشته باشد")
    return [random.randint(1, sides) for _ in range(count)]


def roll_expression(expr: str) -> dict:
    """مثل: 2d6، 1d20+3، d8-1"""
    expr = expr.strip().lower().replace(" ", "")
    m = _PATTERN.match(expr)
    if not m:
        raise DiceError(f"عبارت تاس معتبر نیست: {expr} (مثال: 2d6 یا 1d20+3)")
    count = int(m.group(1) or "1")
    sides = int(m.group(2))
    mod = int(m.group(3) or "0")
    rolls = roll_dice(count, sides)
    total = sum(rolls) + mod
    breakdown = "+".join(str(r) for r in rolls)
    if mod:
        breakdown += f" {mod:+d}"
    return {"rolls": rolls, "total": total, "breakdown": breakdown,
            "count": count, "sides": sides, "mod": mod}


def roll_d20() -> int:
    return random.randint(1, 20)


def roll_advantage() -> dict:
    """دو تاس ۲۰ و گرفتن بیشتر — خوش‌شانسی"""
    r1, r2 = random.randint(1, 20), random.randint(1, 20)
    return {"rolls": [r1, r2], "total": max(r1, r2),
            "breakdown": f"{r1} و {r2} → بیشترین: {max(r1, r2)}"}


def roll_disadvantage() -> dict:
    """دو تاس ۲۰ و گرفتن کمتر — بدشانسی"""
    r1, r2 = random.randint(1, 20), random.randint(1, 20)
    return {"rolls": [r1, r2], "total": min(r1, r2),
            "breakdown": f"{r1} و {r2} → کمترین: {min(r1, r2)}"}


def parse_dice(dice_str: str) -> tuple:
    """'2d6+3' → (count, sides, mod)"""
    m = _PATTERN.match(dice_str.strip().lower().replace(" ", ""))
    if not m:
        raise DiceError(f"تاس نامعتبر: {dice_str}")
    return int(m.group(1) or "1"), int(m.group(2)), int(m.group(3) or "0")
