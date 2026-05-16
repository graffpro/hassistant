"""
ExperienceStore — лог успехов и провалов ассистента.
"""
import sqlite3
import json
from datetime import datetime
from core.config import config
from core.logger import logger


class ExperienceStore:
    def __init__(self):
        self.db_path = config.memory.db_path
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    object_type TEXT,
                    command TEXT,
                    success INTEGER,
                    error_message TEXT,
                    steps_data TEXT,
                    context TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
        logger.debug("ExperienceStore initialized")

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def record(self, action: str, object_type: str, command: str,
               success: bool, steps: list = None, error: str = None, context: dict = None):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO experiences
                   (action, object_type, command, success, error_message, steps_data, context)
                   VALUES (?,?,?,?,?,?,?)""",
                (action, object_type, command, int(success),
                 error, json.dumps(steps or []), json.dumps(context or {}))
            )
        status = "✓" if success else "✗"
        logger.debug(f"Experience [{status}]: {action}/{object_type}")

    def get_failures(self, action: str, object_type: str) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM experiences WHERE action=? AND object_type=? AND success=0 ORDER BY timestamp DESC LIMIT 5",
                (action, object_type)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_success_rate(self, action: str, object_type: str) -> float:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT AVG(success) as rate FROM experiences WHERE action=? AND object_type=?",
                (action, object_type)
            ).fetchone()
            return float(row[0] or 0.0)
