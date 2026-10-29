"""Durable comparison records, independent of LangGraph checkpoint serialization."""
import json
import sqlite3
from threading import RLock
from pathlib import Path


def comparison_status(runs):
    states = [run["status"] for run in runs.values()]
    if "running" in states or "queued" in states:
        return "running"
    if "awaiting_review" in states:
        return "awaiting_review"
    return "error" if "error" in states else "completed"


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.connection = sqlite3.connect(directory / "comparisons.db", check_same_thread=False)
        self.connection.execute("CREATE TABLE IF NOT EXISTS comparisons (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        self.connection.commit()

    def save(self, value):
        with self.lock:
            self.connection.execute("INSERT OR REPLACE INTO comparisons VALUES (?, ?, ?)",
                                    (value["id"], value["created_at"], json.dumps(value, allow_nan=False)))
            self.connection.commit()

    def get(self, identifier):
        with self.lock:
            row = self.connection.execute("SELECT payload FROM comparisons WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise KeyError(identifier)
            return json.loads(row[0])

    def list(self, limit=50):
        with self.lock:
            return [json.loads(row[0]) for row in self.connection.execute("SELECT payload FROM comparisons ORDER BY created_at DESC LIMIT ?", (limit,))]

    def update_run(self, identifier, path, run):
        with self.lock:
            value = self.get(identifier)
            value["runs"][path] = run
            value["status"] = comparison_status(value["runs"])
            self.save(value)

    def close(self):
        self.connection.close()
