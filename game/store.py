# -*- coding: utf-8 -*-
"""ذخیره‌سازی SQLite — جلسات بازی روی گوشی هم سبک و سریع می‌ماند."""
import json
import os
import sqlite3
import time

from .models import Session


class Store:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                chat_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at REAL
            )"""
        )
        self.conn.commit()
        self._cache = {}

    def save(self, session: Session):
        data = json.dumps(session.to_dict(), ensure_ascii=False)
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions (chat_id, data, updated_at) VALUES (?, ?, ?)",
            (session.chat_id, data, time.time()),
        )
        self.conn.commit()
        self._cache[session.chat_id] = session

    def load(self, chat_id: int):
        if chat_id in self._cache:
            return self._cache[chat_id]
        row = self.conn.execute(
            "SELECT data FROM sessions WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        if not row:
            return None
        session = Session.from_dict(json.loads(row[0]))
        self._cache[chat_id] = session
        return session

    def find_by_code(self, code: str):
        code = code.strip().upper()
        rows = self.conn.execute("SELECT chat_id, data FROM sessions").fetchall()
        for _, data in rows:
            s = Session.from_dict(json.loads(data))
            if s.code == code:
                return s
        return None

    def delete(self, chat_id: int):
        self.conn.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
        self.conn.commit()
        self._cache.pop(chat_id, None)

    def all_sessions(self):
        rows = self.conn.execute("SELECT chat_id, data FROM sessions").fetchall()
        return [Session.from_dict(json.loads(d)) for _, d in rows]

    def close(self):
        self.conn.close()
