"""Incremental SQLite persistence: changed run fields plus append-only events."""
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


def normalize_legacy_run(run):
    """Translate old saved naming at the storage boundary, including resume keys."""
    if "workflow" in run:
        run["playbook_hint"] = run.pop("workflow")
    run["event_keys"] = ["playbook_hint" if key == "workflow" else key for key in run.get("event_keys", [])]
    for event in run.get("events", []):
        if event["type"] == "workflow":
            event["type"] = "playbook_hint"
            event["title"] = "Selected playbook hint (advisory)"
            detail = event["detail"]
            if "workflow" in detail:
                detail["playbook_hint"] = detail.pop("workflow")
    return run


def encode(value):
    return json.dumps(value, allow_nan=False)


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.connection = sqlite3.connect(directory / "comparisons.db", check_same_thread=False)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("CREATE TABLE IF NOT EXISTS comparisons (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        self.connection.commit()
        legacy = []
        for identifier, payload in self.connection.execute("SELECT id, payload FROM comparisons"):
            value = json.loads(payload)
            if isinstance(value.get("runs"), dict):
                legacy.append((identifier, value))
        if legacy:
            # Preserve an exact, readable pre-migration database before changing it.
            backup_path = directory / "comparisons.pre-fields.db"
            if not backup_path.exists():
                with sqlite3.connect(backup_path) as backup:
                    self.connection.backup(backup)
        with self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS run_fields (comparison_id TEXT NOT NULL REFERENCES comparisons(id), path TEXT NOT NULL, name TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(comparison_id, path, name))")
            self.connection.execute("CREATE TABLE IF NOT EXISTS events (comparison_id TEXT NOT NULL REFERENCES comparisons(id), path TEXT NOT NULL, position INTEGER NOT NULL, event_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(comparison_id, path, position), UNIQUE(comparison_id, path, event_id))")
            for identifier, value in legacy:
                runs = value.pop("runs")
                for path, run in runs.items():
                    self._write_run(identifier, path, normalize_legacy_run(run))
                self.connection.execute("UPDATE comparisons SET payload=? WHERE id=?", (encode(value), identifier))

    def _write_run(self, identifier, path, run):
        # This method participates in the caller's single atomic transaction.
        # Serialize fields independently; SQLite only writes fields that changed.
        for name, value in run.items():
            if name == "events":
                continue
            self.connection.execute(
                "INSERT INTO run_fields VALUES (?, ?, ?, ?) ON CONFLICT(comparison_id,path,name) DO UPDATE SET payload=excluded.payload WHERE run_fields.payload != excluded.payload",
                (identifier, path, name, encode(value)))
        old_names = {row[0] for row in self.connection.execute("SELECT name FROM run_fields WHERE comparison_id=? AND path=?", (identifier, path))}
        for name in old_names - set(run):
            self.connection.execute("DELETE FROM run_fields WHERE comparison_id=? AND path=? AND name=?", (identifier, path, name))
        count = self.connection.execute("SELECT COUNT(*) FROM events WHERE comparison_id=? AND path=?", (identifier, path)).fetchone()[0]
        events = run.get("events", [])
        if len(events) < count:
            raise ValueError("Persisted events are append-only; refusing to truncate history.")
        for position in range(count, len(events)):
            event = events[position]
            self.connection.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?)", (identifier, path, position, event["id"], encode(event)))

    def save(self, value):
        with self.lock, self.connection:
            metadata = {key: item for key, item in value.items() if key != "runs"}
            self.connection.execute("INSERT INTO comparisons VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload WHERE comparisons.payload != excluded.payload",
                                    (value["id"], value["created_at"], encode(metadata)))
            for path, run in value["runs"].items():
                self._write_run(value["id"], path, run)

    def get(self, identifier):
        with self.lock:
            row = self.connection.execute("SELECT payload FROM comparisons WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise KeyError(identifier)
            value = json.loads(row[0])
            runs = {}
            for path, name, payload in self.connection.execute("SELECT path, name, payload FROM run_fields WHERE comparison_id=?", (identifier,)):
                runs.setdefault(path, {"events": []})[name] = json.loads(payload)
            for path, payload in self.connection.execute("SELECT path, payload FROM events WHERE comparison_id=? ORDER BY path, position", (identifier,)):
                runs[path]["events"].append(json.loads(payload))
            value["runs"] = runs
            value["status"] = comparison_status(runs)
            return value

    def list(self, limit=50):
        with self.lock:
            identifiers = [row[0] for row in self.connection.execute("SELECT id FROM comparisons ORDER BY created_at DESC LIMIT ?", (limit,))]
            return [self.get(identifier) for identifier in identifiers]

    def update_run(self, identifier, path, run):
        with self.lock, self.connection:
            if not self.connection.execute("SELECT 1 FROM comparisons WHERE id=?", (identifier,)).fetchone():
                raise KeyError(identifier)
            self._write_run(identifier, path, run)

    def close(self):
        self.connection.close()
