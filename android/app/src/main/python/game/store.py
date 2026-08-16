# -*- coding: utf-8 -*-
"""ذخیره‌سازی جلسات بازی — SQLite روی دسکتاپ، fallback به فایل JSON روی اندروید.
هر دو پشت یک اینترفیس یکسان (Store)."""
import json
import os
import threading
import time

try:
    import sqlite3
    HAVE_SQLITE = True
except Exception:  # pragma: no cover
    HAVE_SQLITE = False

from .models import Session


class _SqliteBackend:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                chat_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at REAL
            )"""
        )
        self.conn.commit()

    def save(self, session: Session):
        data = json.dumps(session.to_dict(), ensure_ascii=False)
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions (chat_id, data, updated_at) VALUES (?, ?, ?)",
            (session.chat_id, data, time.time()),
        )
        self.conn.commit()

    def load(self, chat_id: int):
        row = self.conn.execute(
            "SELECT data FROM sessions WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return Session.from_dict(json.loads(row[0])) if row else None

    def find_by_code(self, code: str):
        code = code.strip().upper()
        rows = self.conn.execute("SELECT data FROM sessions").fetchall()
        for (data,) in rows:
            s = Session.from_dict(json.loads(data))
            if s.code == code:
                return s
        return None

    def delete(self, chat_id: int):
        self.conn.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
        self.conn.commit()

    def all_sessions(self):
        rows = self.conn.execute("SELECT data FROM sessions").fetchall()
        return [Session.from_dict(json.loads(d)) for (d,) in rows]

    def close(self):
        self.conn.close()


class _JsonBackend:
    """fallback برای اندروید (وقتی sqlite در دسترس نیست) — یک فایل JSON با قفل."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _read_all(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_all(self, data: dict):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def save(self, session: Session):
        with self.lock:
            data = self._read_all()
            data[str(session.chat_id)] = session.to_dict()
            self._write_all(data)

    def load(self, chat_id: int):
        with self.lock:
            d = self._read_all().get(str(chat_id))
        return Session.from_dict(d) if d else None

    def find_by_code(self, code: str):
        code = code.strip().upper()
        with self.lock:
            for d in self._read_all().values():
                s = Session.from_dict(d)
                if s.code == code:
                    return s
        return None

    def delete(self, chat_id: int):
        with self.lock:
            data = self._read_all()
            data.pop(str(chat_id), None)
            self._write_all(data)

    def all_sessions(self):
        with self.lock:
            return [Session.from_dict(d) for d in self._read_all().values()]

    def close(self):
        pass


class Store:
    """انتخاب خودکار backend — رابط یکسان برای همه‌جا."""

    def __init__(self, db_path: str):
        if HAVE_SQLITE:
            self._backend = _SqliteBackend(db_path)
        else:
            self._backend = _JsonBackend(db_path)
        self._cache = {}

    def save(self, session: Session):
        self._backend.save(session)
        self._cache[session.chat_id] = session

    def load(self, chat_id: int):
        if chat_id in self._cache:
            return self._cache[chat_id]
        session = self._backend.load(chat_id)
        if session:
            self._cache[chat_id] = session
        return session

    def find_by_code(self, code: str):
        return self._backend.find_by_code(code)

    def delete(self, chat_id: int):
        self._backend.delete(chat_id)
        self._cache.pop(chat_id, None)

    def all_sessions(self):
        return self._backend.all_sessions()

    def close(self):
        self._backend.close()
