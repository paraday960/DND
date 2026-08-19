# -*- coding: utf-8 -*-
"""
🧪 تست عمیق‌تر: همه endpointهایی که UI صدا می‌زند را چک می‌کند
- هر دو سرور Flask و Fallback
- چک کردن crash با بدنه خالی، بدنه بد، فیلدهای گمشده
- چک کردن state سازگار بعد از اکشن‌ها
- چک کردن پلی‌ترو کامل نبرد تا پیروزی
"""
import json, os, sys, threading, time, urllib.request, urllib.error, importlib

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.environ["BOT_TOKEN"] = "12345:ABCDEFG"
os.environ["MISTRAL_API_KEY"] = "offline-test"
os.environ["WEBAPP_DEV"] = "1"

ALL_ENDPOINTS = [
    "/api/meta",
    "/api/room/create",
    "/api/room/join",
    "/api/room/state",
    "/api/char/create",
    "/api/char/levelup",
    "/api/combat/start",
    "/api/combat/attack",
    "/api/combat/cast",
    "/api/combat/dodge",
    "/api/combat/dash",
    "/api/combat/disengage",
    "/api/combat/help",
    "/api/combat/hide",
    "/api/combat/shove",
    "/api/combat/secondwind",
    "/api/combat/actionsurge",
    "/api/combat/rage",
    "/api/combat/inspire",
    "/api/combat/offhand",
    "/api/combat/smite",
    "/api/combat/jump",
    "/api/combat/helpup",
    "/api/combat/throw",
    "/api/combat/dip",
    "/api/combat/cunning",
    "/api/combat/rebuke",
    "/api/combat/skip",
    "/api/combat/end",
    "/api/combat/deathsave",
    "/api/inventory/use",
    "/api/move",
    "/api/where/look",
    "/api/look",
    "/api/where",
    "/api/scenario",
    "/api/story",
    "/api/check",
    "/api/rest",
    "/api/roll",
]


def _req(url, body=None, method="POST", timeout=30, retries=3):
    for attempt in range(retries):
        try:
            data = json.dumps(body).encode() if body is not None else b""
            headers = {"Content-Type": "application/json"}
            r = urllib.request.Request(url, data=data, headers=headers, method=method)
            resp = urllib.request.urlopen(r, timeout=timeout)
            return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {"error": "non-json", "raw": ""}
        except Exception as e:
            if attempt + 1 < retries:
                time.sleep(0.3)
                continue
            return 0, {"error": str(e)[:120]}


def _start_flask(port):
    os.environ["WEBAPP_DEV"] = "1"
    sys.path.insert(0, ROOT)
    import minigame_e2e_test as e2e
    return e2e.make_flask_server()(port)


def _start_fallback(port):
    sys.path.insert(0, ROOT)
    import minigame_e2e_test as e2e
    return e2e.make_fallback_server()(port)


def run_tests(label, factory, port):
    results = []
    def chk(name, cond, detail=""):
        results.append((name, bool(cond), detail))
        m = "✅" if cond else "❌"
        print(f"  {m} {name} {detail[:100] if detail else ''}")

    shutdown = factory(port)
    try:
        time.sleep(2)
        base = f"http://127.0.0.1:{port}"
        print(f"\n{'='*60}\n🚀 عمیق: {label} (port {port})\n{'='*60}")

        # 1. Endpoint existence (GET or POST without body — should return JSON error, not 500)
        for ep in ALL_ENDPOINTS:
            method = "GET" if ep in ("/api/meta", "/healthz", "/") else "POST"
            st, j = _req(base + ep, body={} if method == "POST" else None, method=method)
            ok = st != 500 and isinstance(j, dict)
            chk(f"{method} {ep} -> not 500", ok, f"(status={st})")

        # 2. Full combat playthrough: create room, create char, start combat, win
        uid = 7777
        uname = "DeepTest"
        qs = f"?user_id={uid}&user_name={uname}"
        st, j = _req(base + "/api/room/create" + qs, body={})
        chk("create room", st == 200 and j.get("ok"), str(j)[:120])
        data = j.get("data") or {}
        code = ""
        if isinstance(data.get("code"), str):
            code = data["code"]
        elif isinstance(data.get("state"), dict):
            code = ((data["state"].get("room") or {}).get("code") or "")
        chk("room code", bool(code), f"code={code}, keys={list(data.keys())}")

        st, j = _req(base + f"/api/char/create{qs}", body={
            "room": code, "name": "آرش", "race": "human", "cls": "fighter", "weapon": "longsword",
        })
        chk("create fighter", st == 200 and j.get("ok"), str(j)[:160])

        st, j = _req(base + f"/api/combat/start{qs}", body={"room": code})
        chk("combat start", st == 200 and j.get("ok"), str(j)[:120])

        # Simulate many attacks until combat ends
        win = False
        for i in range(60):
            st, j = _req(base + f"/api/combat/attack{qs}", body={"room": code, "target": ""})
            d = j.get("data") or {}
            if not j.get("ok"):
                # skip turn if not my turn
                st2, j2 = _req(base + f"/api/combat/skip{qs}", body={"room": code})
                d2 = j2.get("data") or {}
                if d2.get("state") and not d2["state"].get("combat"):
                    win = True
                    break
            if d.get("state") and not d["state"].get("combat"):
                win = True
                break
        chk("combat ended within 60 actions", win, "combat cleared")

        # 3. State shape after combat (must have sheet.me with hp/max_hp)
        st, j = _req(base + f"/api/room/state?room={code}&user_id={uid}&user_name={uname}", body=None, method="GET")
        data = j.get("data") or {}
        me = data.get("me") or {}
        my_char = me.get("char") or {}
        chk("state.me exists after combat", bool(me), f"keys={list(me.keys())[:20]}")
        chk("me.char.hp int", isinstance(my_char.get("hp"), int), f"hp={my_char.get('hp')}")
        chk("me.char.max_hp int", isinstance(my_char.get("max_hp"), int), f"max={my_char.get('max_hp')}")
        chk("combat None after victory", data.get("combat") is None, f"combat={data.get('combat')}")

        # 4. Fuzz: garbage inputs shouldn't 500
        garbage_bodies = [
            None, "", "abc", 123, [],
            {"room": "XXXXXX"},  # nonexistent room
            {"target": None, "spell": None, "slot": "abc"},
            {"action": "💩"},
            {"user_id": "not-a-number"},
        ]
        crashes = 0
        for ep in ["/api/combat/attack", "/api/combat/cast", "/api/char/create", "/api/inventory/use"]:
            for gb in garbage_bodies:
                try:
                    data = json.dumps(gb).encode() if gb is not None else b""
                    r = urllib.request.Request(base + ep + qs + "&room=" + code,
                                               data=data, headers={"Content-Type": "application/json"}, method="POST")
                    resp = urllib.request.urlopen(r, timeout=10)
                    st_g = resp.status
                except urllib.error.HTTPError as e:
                    st_g = e.code
                except Exception as e:
                    st_g = 0
                    print(f"   CRASH {ep} body={gb!r} err={e}")
                if st_g == 500 or st_g == 0:
                    crashes += 1
        chk("fuzz: no crashes/500s", crashes == 0, f"crashes={crashes}")

        # 5. All classes character creation
        classes_ok = 0
        classes_total = 0
        from game.rules import CLASSES
        for cls_name in CLASSES.keys():
            classes_total += 1
            uid2 = 8000 + classes_total
            uname2 = f"Player{cls_name}"
            st, j = _req(base + f"/api/room/create?user_id={uid2}&user_name={uname2}", body={})
            d2 = j.get("data") or {}
            c2 = d2.get("code") or (((d2.get("state") or {}).get("room") or {}).get("code") or "")
            st, j = _req(base + f"/api/char/create?user_id={uid2}&user_name={uname2}", body={
                "room": c2, "name": f"Test{cls_name}", "race": "human", "cls": cls_name,
                "weapon": list(CLASSES[cls_name].get("weapons", ["longsword"]))[0],
            })
            if st == 200 and j.get("ok"):
                classes_ok += 1
            else:
                print(f"   ❌ class {cls_name} failed (code={c2}): {str(j)[:150]}")
        chk("all classes creatable", classes_ok == classes_total, f"{classes_ok}/{classes_total}")

    finally:
        try: shutdown()
        except Exception: pass

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n📊 {label}: {passed}/{total}")
    return passed, total, results


if __name__ == "__main__":
    p1, t1, r1 = run_tests("Flask deep", _start_flask, 19101)
    p2, t2, r2 = run_tests("Fallback deep", _start_fallback, 19102)
    print(f"\n{'='*60}")
    print(f"🎯 Flask deep:    {p1}/{t1}")
    print(f"🎯 Fallback deep: {p2}/{t2}")
    if p1 == t1 and p2 == t2:
        print("✅ همه تست‌های عمیق پاس شدند!")
    else:
        print("❌ برخی تست‌ها شکست خوردند.")
        sys.exit(1)
