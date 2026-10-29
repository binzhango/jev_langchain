"""Pair identical inputs, isolate effects, and retain both realized histories."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import fcntl
import json
import sqlite3
from time import perf_counter, time
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .agent import Session, build_agent
from .config import Settings
from .domain import get_scenario, outcome
from .store import Store


def new_run(path, fixture):
    return {"path": path, "status": "queued", "events": [], "output": "", "error": None, "degraded": False, "decision_errors": [],
            "metrics": {"llm_calls": 0, "jev_calls": 0, "tool_calls": 0, "input_tokens": None,
                        "output_tokens": None, "duration_ms": 0, "jev_ms": 0, "review_wait_ms": 0},
            "pending_review": None, "actions": [], "outcome": None, "world": deepcopy(fixture),
            "event_keys": [], "tool_results": {}, "risk_cache": {}, "model_steps": 0}


class ComparisonRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self._lease = (settings.data_dir / "runner.lock").open("a+")
        try:
            fcntl.flock(self._lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lease.close()
            raise ValueError("Another runner is using this data directory. Use the running dashboard, stop it before CLI execution, or set a different JEV_LAB_DATA_DIR.") from None
        self.store = Store(settings.data_dir)
        # Avoid timing distortions from two requests competing for one local server.
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="comparison")
        self._recover()

    def _recover(self):
        for comparison in self.store.list(10000):
            for path, run in comparison["runs"].items():
                if run["status"] in {"running", "queued"}:
                    run["status"] = "error"
                    run["error"] = "Server stopped during execution. Start a fresh comparison; completed and paused runs remain inspectable."
                    self.store.update_run(comparison["id"], path, run)

    def create(self, scenario_id="missing-item", task=None, execution="live", first="normal", background=True):
        if execution not in {"live", "fixture"}:
            raise ValueError("execution must be live or fixture")
        if first not in {"normal", "jev"}:
            raise ValueError("first must be normal or jev")
        scenario = get_scenario(scenario_id)
        task = task.strip() if task is not None else scenario["task"]
        if not task or len(task) > 10000:
            raise ValueError("Task must contain 1–10000 characters.")
        if execution == "fixture" and task != scenario["task"]:
            raise ValueError("Scripted fixture mode requires the scenario's original task. Use live mode for a custom task.")
        if execution == "live" and not self.settings.jev_token:
            raise ValueError("JEV_TOKEN is not available to the server. Export it before starting, or choose the scripted fixture walkthrough.")
        identifier = uuid4().hex
        snapshot = {"scenario_id": scenario_id, "task": task, "fixture": deepcopy(scenario["fixture"]),
                    "scenario_time": "2026-01-15T12:00:00Z", "policy_version": "support-v1",
                    "model": self.settings.model, "temperature": 0, "max_tokens": self.settings.max_tokens,
                    "execution_config": self.settings.execution_identity()}
        value = {"id": identifier, "created_at": datetime.now(timezone.utc).isoformat(), "task": task,
                 "scenario_id": scenario_id, "source": execution, "status": "queued", "model": self.settings.model,
                 "input_hash": hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
                 "snapshot": snapshot, "custom": task != scenario["task"], "first": first,
                 "runs": {path: new_run(path, scenario["fixture"]) for path in ("normal", "jev")},
                 "analysis": {"first_divergence": None, "agreement": None,
                              "note": "Shared initial task; independent data and histories. Results measure the whole harness. Fixture mode is scripted, not model evidence."}}
        self.store.save(value)
        paths = (first, "jev" if first == "normal" else "normal")
        for path in paths:
            if background:
                self.executor.submit(self._execute, identifier, path)
            else:
                self._execute(identifier, path)
        return self.store.get(identifier)

    def review(self, identifier, path, review_id, decision, args=None, background=True):
        if path not in {"normal", "jev"} or decision not in {"approve", "edit", "reject"}:
            raise ValueError("Invalid path or review decision.")
        with self.store.lock:
            value = self.store.get(identifier)
            if value["snapshot"].get("execution_config") != self.settings.execution_identity():
                raise ValueError("Execution settings changed since this comparison started. Restore its recorded settings before resuming, or create a new comparison.")
            run = value["runs"][path]
            pending = run.get("pending_review")
            if run["status"] != "awaiting_review" or not pending or pending["id"] != review_id:
                raise ValueError("This review is no longer pending. Refresh the comparison.")
            if decision == "edit":
                if not isinstance(args, dict) or set(args) - {"order_id", "amount", "reason", "request_review"} or not {"order_id", "amount", "reason"} <= set(args):
                    raise ValueError("Edited arguments must contain order_id, amount, reason and optionally request_review.")
                if not isinstance(args["order_id"], str) or not isinstance(args["reason"], str) or not isinstance(args["amount"], (int, float)) or isinstance(args["amount"], bool):
                    raise ValueError("Edited order_id/reason must be text and amount must be a number.")
                if "request_review" in args and not isinstance(args["request_review"], bool):
                    raise ValueError("request_review must be true or false.")
                json.dumps(args, allow_nan=False)
            run["status"] = "queued"
            run["metrics"]["review_wait_ms"] += max(0, (time() - run.pop("paused_at", time())) * 1000)
            self.store.update_run(identifier, path, run)
        resume = {"decision": decision, "args": args}
        if background:
            self.executor.submit(self._execute, identifier, path, resume)
        else:
            self._execute(identifier, path, resume)
        return self.store.get(identifier)

    def _execute(self, identifier, path, resume=None):
        comparison = self.store.get(identifier)
        run = comparison["runs"][path]
        run["status"] = "running"
        self.store.update_run(identifier, path, run)
        session = Session(self.settings, comparison, run, lambda updated: self.store.update_run(identifier, path, updated))
        started = perf_counter()
        checkpoint_dir = self.settings.data_dir / "checkpoints"
        checkpoint_dir.mkdir(exist_ok=True)
        connection = sqlite3.connect(checkpoint_dir / f"{identifier}-{path}.db", check_same_thread=False)
        try:
            graph = build_agent(session, SqliteSaver(connection))
            session.emit("input", "Identical starting task and fixture", {"input_hash": comparison["input_hash"], **comparison["snapshot"]}, once="input")
            if resume is not None:
                inputs = Command(resume=resume)
            else:
                # Both get these same facts, including those supplied to Jev.
                content = comparison["task"] + "\n\nShared starting context:\n" + json.dumps(comparison["snapshot"]["fixture"])
                inputs = {"messages": [{"role": "user", "content": content}]}
            result = graph.invoke(inputs, config={"configurable": {"thread_id": identifier + "-" + path}, "recursion_limit": 32})
            if result.get("__interrupt__"):
                run["status"] = "awaiting_review"
                run["paused_at"] = time()
            else:
                run["status"] = "completed"
                run["pending_review"] = None
                run["output"] = result["messages"][-1].text
                run["outcome"] = outcome(session.world, get_scenario(comparison["scenario_id"]), run["actions"], run["output"], custom=comparison["custom"])
                if run.get("degraded"):
                    run["outcome"]["passed"] = None
                    run["outcome"]["label"] = "Task checks recorded; Jev unavailable during this run. Excluded from decision-quality comparison."
                session.emit("response", "Final response", {"text": run["output"], "outcome": run["outcome"]}, once="response")
        except Exception as error:
            run["status"] = "error"
            run["pending_review"] = None
            run["error"] = self.settings.safe_error(error)
            session.emit("error", "Run failed", {"message": run["error"]})
        finally:
            run["metrics"]["duration_ms"] += round((perf_counter() - started) * 1000, 2)
            session.save()
            connection.close()
            self._analyze(identifier)

    def _analyze(self, identifier):
        with self.store.lock:
            comparison = self.store.get(identifier)
            runs = comparison["runs"]
            if all(run["status"] in {"completed", "error"} for run in runs.values()):
                left, right = (runs[path]["actions"] for path in ("normal", "jev"))
                divergence = None
                for index in range(max(len(left), len(right))):
                    a = left[index] if index < len(left) else None
                    b = right[index] if index < len(right) else None
                    # Ignore generated prose in reasons; compare action/amount/status.
                    def signature(action):
                        if action is None:
                            return None
                        args = {key: value for key, value in action["args"].items() if key not in {"reason", "request_review"}}
                        result = action["result"]
                        return action["tool"], args, result.get("status") if isinstance(result, dict) else result
                    if signature(a) != signature(b):
                        divergence = f"Action {index + 1}: {a['tool'] if a else 'no action'} vs {b['tool'] if b else 'no action'}. Inspect the aligned traces for arguments, review, and results."
                        break
                comparison["analysis"]["first_divergence"] = divergence
                comparison["analysis"]["agreement"] = divergence is None if all(run["status"] == "completed" for run in runs.values()) else None
                self.store.save(comparison)

    def close(self):
        self.executor.shutdown(wait=True)
        self.store.close()
        fcntl.flock(self._lease.fileno(), fcntl.LOCK_UN)
        self._lease.close()
