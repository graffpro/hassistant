"""
WorkflowStore — хранит именованные workflows в SQLite.
"""
import sqlite3
import json
from datetime import datetime
from typing import Optional
from core.config import config
from core.logger import logger


class WorkflowStore:
    def __init__(self):
        self.db_path = config.memory.db_path
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    success_count INTEGER DEFAULT 1,
                    fail_count INTEGER DEFAULT 0,
                    last_used TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_action_type ON workflows(action, object_type)")
        logger.debug("WorkflowStore initialized")

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def save(self, name: str, action: str, object_type: str, steps: list) -> int:
        """Сохраняет или обновляет workflow."""
        existing = self.find_exact(action, object_type, name)
        now = datetime.utcnow().isoformat()

        with self._conn() as conn:
            if existing:
                conn.execute(
                    "UPDATE workflows SET steps=?, success_count=success_count+1, last_used=? WHERE id=?",
                    (json.dumps(steps), now, existing["id"])
                )
                logger.debug(f"Workflow updated: {name}")
                return existing["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO workflows (name, action, object_type, steps, last_used) VALUES (?,?,?,?,?)",
                    (name, action, object_type, json.dumps(steps), now)
                )
                logger.info(f"Workflow saved: {name} ({action}/{object_type})")
                return cur.lastrowid

    def find_exact(self, action: str, object_type: str, name: str = None) -> Optional[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            q = "SELECT * FROM workflows WHERE action=? AND object_type=?"
            params = [action, object_type]
            if name:
                q += " AND name=?"
                params.append(name)
            q += " ORDER BY success_count DESC LIMIT 1"
            row = conn.execute(q, params).fetchone()
            if row:
                d = dict(row)
                d["steps"] = json.loads(d["steps"])
                return d
        return None

    def find_by_action(self, action: str) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM workflows WHERE action=? ORDER BY success_count DESC LIMIT 10",
                (action,)
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["steps"] = json.loads(d["steps"])
                result.append(d)
            return result

    def mark_failed(self, workflow_id: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE workflows SET fail_count=fail_count+1 WHERE id=?",
                (workflow_id,)
            )

    def get_all(self) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM workflows ORDER BY success_count DESC").fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["steps"] = json.loads(d["steps"])
                result.append(d)
            return result
