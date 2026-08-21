#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-diagnostics for the D&D bot runtime.

Run:
    python doctor.py
    python doctor.py --json
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import config
import runtime
from game.dice import roll_expression
from game.models import Character, Session
from game.store import Store


def _module_ok(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run_checks() -> dict:
    rt = runtime.check_runtime()
    results = []

    def check(name: str, ok: bool, detail: str = ""):
        results.append({"name": name, "ok": bool(ok), "detail": detail})

    check("runtime writable", rt["ok"], "; ".join(rt["problems"]))
    check("BOT_TOKEN configured", bool(config.BOT_TOKEN), "required for real Telegram run")
    check("requests installed", _module_ok("requests"))
    check("flask installed", _module_ok("flask"))
    check("telegram installed", _module_ok("telegram"))

    try:
        test_db = os.path.join(config.TMP_DIR, "doctor_store.db")
        try:
            os.remove(test_db)
        except FileNotFoundError:
            pass
        store = Store(test_db)
        s = Session(chat_id=4242, name="doctor", dm_id=1, dm_name="doctor")
        s.players["1"]["char"] = Character(name="Doctor", race="human", cls="fighter", weapon="longsword")
        store.save(s)
        loaded = store.load(4242)
        store.close()
        try:
            os.remove(test_db)
        except OSError:
            pass
        check("Store read/write", bool(loaded and loaded.players["1"]["char"].name == "Doctor"))
    except Exception as e:
        check("Store read/write", False, repr(e))

    try:
        r = roll_expression("2d6+3")
        check("Dice engine", 5 <= r["total"] <= 15, str(r))
    except Exception as e:
        check("Dice engine", False, repr(e))

    diag = rt["diagnostics"]
    ok = all(item["ok"] for item in results if item["name"] not in {"BOT_TOKEN configured"})
    return {
        "ok": ok,
        "results": results,
        "diagnostics": diag,
        "config": {
            "data_dir": config.DATA_DIR,
            "tmp_dir": config.TMP_DIR,
            "log_dir": config.LOG_DIR,
            "db_path": config.DB_PATH,
            "webapp_url_set": bool(config.webapp_url()),
            "ai_provider": config.AI_PROVIDER,
        },
    }


def main(argv: list[str]) -> int:
    report = run_checks()
    if "--json" in argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("🩺 D&D Bot Doctor")
        print("=" * 28)
        for item in report["results"]:
            mark = "✅" if item["ok"] else "⚠️"
            detail = f" — {item['detail']}" if item.get("detail") else ""
            print(f"{mark} {item['name']}{detail}")
        print("-" * 28)
        print("data:", report["config"]["data_dir"])
        print("tmp: ", report["config"]["tmp_dir"])
        print("logs:", report["config"]["log_dir"])
        print("db:  ", report["config"]["db_path"])
        print("نتیجه:", "آماده" if report["ok"] else "نیازمند توجه")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
