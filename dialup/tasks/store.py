"""SQLite storage for tasks and their event log. Survives server restarts."""
import sqlite3
import threading
import time
import uuid
from enum import Enum

from .models import Channel, Status, Task

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    caller TEXT NOT NULL,
    goal TEXT NOT NULL,
    channel TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    status TEXT NOT NULL,
    result TEXT,
    steps INTEGER NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_task ON events(task_id);
"""

UPDATABLE = {"status", "result", "steps", "tokens"}


class Store:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            cols = {r["name"] for r in self._db.execute("PRAGMA table_info(tasks)")}
            if "language" not in cols:  # database from before language support
                self._db.execute("ALTER TABLE tasks ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")
                self._db.commit()

    # ---- tasks ----

    def create_task(self, caller: str, goal: str, channel: Channel, language: str = "en") -> Task:
        t = Task(id=uuid.uuid4().hex[:6], caller=caller, goal=goal, channel=channel, language=language)
        with self._lock:
            self._db.execute(
                "INSERT INTO tasks (id, caller, goal, channel, language, status, result, steps, tokens,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (t.id, t.caller, t.goal, t.channel.value, t.language, t.status.value,
                 t.result, t.steps, t.tokens, t.created_at, t.updated_at),
            )
            self._db.commit()
        return t

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return _task(row) if row else None

    def update(self, task_id: str, **fields) -> None:
        bad = set(fields) - UPDATABLE
        if bad:
            raise ValueError(f"can't update {bad}")
        fields["updated_at"] = time.time()
        values = [v.value if isinstance(v, Enum) else v for v in fields.values()]
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._db.execute(f"UPDATE tasks SET {cols} WHERE id=?", (*values, task_id))
            self._db.commit()

    def recent(self, limit: int = 20) -> list[Task]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_task(r) for r in rows]

    def waiting_for(self, caller: str) -> Task | None:
        """The caller's task that is waiting on an answer, if any."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM tasks WHERE caller=? AND status=? ORDER BY updated_at DESC LIMIT 1",
                (caller, Status.WAITING.value),
            ).fetchone()
        return _task(row) if row else None

    def fail_unfinished(self) -> int:
        """On startup: tasks that were mid-run lost their browser, so mark them failed."""
        live = (Status.QUEUED.value, Status.RUNNING.value, Status.WAITING.value)
        with self._lock:
            cur = self._db.execute(
                "UPDATE tasks SET status=?, result=?, updated_at=? WHERE status IN (?,?,?)",
                (Status.FAILED.value, "Server restarted", time.time(), *live),
            )
            self._db.commit()
        return cur.rowcount

    # ---- events ----

    def add_event(self, task_id: str, kind: str, text: str) -> dict:
        at = time.time()
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events (task_id, kind, text, at) VALUES (?,?,?,?)",
                (task_id, kind, text, at),
            )
            self._db.commit()
        return {"id": cur.lastrowid, "task_id": task_id, "kind": kind, "text": text, "at": at}

    def events(self, task_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def _task(row: sqlite3.Row) -> Task:
    d = dict(row)
    d["status"] = Status(d["status"])
    d["channel"] = Channel(d["channel"])
    return Task(**d)
