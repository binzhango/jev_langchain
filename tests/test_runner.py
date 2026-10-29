"""Exercise real LangChain checkpoint/review orchestration with synthetic workers."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import socket
from threading import Barrier

import pytest

from jev_harness import agent, decisions
from jev_harness.config import Settings
from jev_harness.domain import get_scenario
from jev_harness.runner import ComparisonRunner
from jev_harness.store import Store


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    """Fixture mode must not instantiate remote clients or attempt network I/O."""
    def forbidden(*args, **kwargs):
        raise AssertionError("Fixture execution attempted a real model client or network call")

    monkeypatch.setattr(agent, "local_model", forbidden)
    monkeypatch.setattr(decisions, "TypeSafeClassifier", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def runner(tmp_path):
    value = ComparisonRunner(Settings(data_dir=tmp_path, model="same-configured-worker"))
    try:
        yield value
    finally:
        value.close()


def create(runner, scenario="missing-item", **kwargs):
    return runner.create(scenario_id=scenario, execution="fixture", background=False, **kwargs)


def resolve(runner, comparison, path, decision="approve", args=None):
    review_id = comparison["runs"][path]["pending_review"]["id"]
    return runner.review(comparison["id"], path, review_id, decision, args=args, background=False)


def events(run, kind):
    return [event for event in run["events"] if event["type"] == kind]


def test_identical_inputs_same_worker_and_separate_effects(runner, monkeypatch):
    worker_inputs = []
    original = agent.ScriptedWorker

    def capture_worker(**kwargs):
        worker_inputs.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(agent, "ScriptedWorker", capture_worker)
    comparison = create(runner)
    assert comparison["status"] == "completed"
    assert comparison["source"] == "fixture"
    assert comparison["model"] == comparison["snapshot"]["model"] == "same-configured-worker"
    assert len(worker_inputs) == 2
    assert worker_inputs[0] == worker_inputs[1]
    expected_hash = hashlib.sha256(json.dumps(comparison["snapshot"], sort_keys=True).encode()).hexdigest()
    assert comparison["input_hash"] == expected_hash
    normal, jev = (comparison["runs"][path] for path in ("normal", "jev"))
    assert events(normal, "input")[0]["detail"] == events(jev, "input")[0]["detail"]
    assert events(normal, "input")[0]["detail"]["input_hash"] == expected_hash
    assert normal["world"]["order"]["refunded_amount"] == jev["world"]["order"]["refunded_amount"] == 9
    assert len(normal["world"]["refunds"]) == len(jev["world"]["refunds"]) == 1
    assert comparison["snapshot"]["fixture"]["refunds"] == []
    assert comparison["snapshot"]["fixture"]["order"]["refunded_amount"] == 0
    assert get_scenario("missing-item")["fixture"]["refunds"] == []
    assert normal["world"] is not jev["world"]
    normal["world"]["order"]["refunded_amount"] = 123
    assert jev["world"]["order"]["refunded_amount"] == 9
    assert runner.store.get(comparison["id"])["runs"]["normal"]["world"]["order"]["refunded_amount"] == 9
    assert comparison["analysis"]["agreement"] is True
    assert comparison["analysis"]["first_divergence"] is None


@pytest.mark.parametrize("scenario,decision,passed", [
    ("status", None, True), ("missing-item", None, True),
    ("large-refund", "approve", True), ("unjustified-refund", "reject", True),
    ("ambiguous", None, None), ("hard-ceiling", None, True),
])
def test_every_fixture_has_defined_completion_and_truthful_metrics(runner, scenario, decision, passed):
    comparison = create(runner, scenario)
    if decision:
        assert comparison["status"] == "awaiting_review"
        assert all(run["status"] == "awaiting_review" for run in comparison["runs"].values())
        assert all(run["world"]["refunds"] == [] for run in comparison["runs"].values())
        comparison = resolve(runner, comparison, "normal", decision)
        assert comparison["runs"]["normal"]["status"] == "completed"
        assert comparison["runs"]["jev"]["status"] == "awaiting_review"
        comparison = resolve(runner, comparison, "jev", decision)
    assert comparison["status"] == "completed"
    for path, run in comparison["runs"].items():
        assert run["status"] == "completed", run["error"]
        assert run["error"] is None
        assert run["outcome"]["passed"] is passed
        assert run["output"]
        assert run["pending_review"] is None
        assert run["metrics"]["llm_calls"] == run["metrics"]["jev_calls"] == 0
        assert run["metrics"]["input_tokens"] is None
        assert run["metrics"]["output_tokens"] is None
        assert run["metrics"]["jev_ms"] == 0
        assert run["metrics"]["tool_calls"] == len(run["actions"])
        assert all(event["detail"]["model"] == "scripted-walkthrough" for event in events(run, "model"))
        if path == "jev":
            assert len(events(run, "jev_triage")) == 1
            assert events(run, "jev_triage")[0]["detail"]["source"] == "synthetic"
        else:
            assert not events(run, "jev_triage")
            assert not events(run, "jev_risk")


@pytest.mark.parametrize("first", ["normal", "jev"])
def test_changing_execution_order_preserves_fixture_inputs_and_outcomes(runner, first):
    comparison = create(runner, first=first)
    assert comparison["first"] == first
    assert comparison["analysis"]["agreement"] is True
    assert all(run["outcome"]["passed"] is True for run in comparison["runs"].values())
    second = create(runner, first="jev" if first == "normal" else "normal")
    assert second["id"] != comparison["id"]
    assert second["input_hash"] == comparison["input_hash"]
    assert second["snapshot"] == comparison["snapshot"]


@pytest.mark.parametrize("path", ["normal", "jev"])
@pytest.mark.parametrize("decision,edit,result_status,paid", [
    ("approve", None, "success", 40),
    ("edit", {"order_id": "ORD-1001", "amount": 30, "reason": "Reviewed amount"}, "success", 30),
    ("edit", {"order_id": "ORD-1001", "amount": 250, "reason": "Above ceiling"}, "denied", 0),
    ("edit", {"order_id": "another-order", "amount": 9, "reason": "Wrong owner"}, "denied", 0),
    ("reject", None, "rejected", 0),
])
def test_review_checks_actual_arguments_and_cannot_execute_twice(runner, path, decision, edit, result_status, paid):
    comparison = create(runner, "large-refund")
    review_id = comparison["runs"][path]["pending_review"]["id"]
    comparison = resolve(runner, comparison, path, decision, edit)
    run = comparison["runs"][path]
    other = comparison["runs"]["jev" if path == "normal" else "normal"]
    assert run["status"] == "completed", run["error"]
    assert other["status"] == "awaiting_review"
    assert other["world"]["refunds"] == []
    assert run["world"]["order"]["refunded_amount"] == paid
    assert len(run["world"]["refunds"]) == int(paid > 0)
    refunds = [action for action in run["actions"] if action["tool"] == "issue_refund"]
    assert len(refunds) == 1
    assert refunds[0]["result"]["status"] == result_status
    if edit:
        assert refunds[0]["args"] == edit
    if paid:
        assert run["world"]["refunds"][0]["approved"] is True
    assert len(events(run, "review_requested")) == 1
    assert len(events(run, "review_resolved")) == 1
    assert len(events(run, "input")) == 1
    snapshot = deepcopy(run)
    with pytest.raises(ValueError, match="no longer pending"):
        runner.review(comparison["id"], path, review_id, "approve", background=False)
    assert runner.store.get(comparison["id"])["runs"][path] == snapshot


def test_stale_and_malformed_reviews_preserve_pending_state(runner):
    comparison = create(runner, "large-refund")
    identifier = comparison["id"]
    pending = comparison["runs"]["normal"]["pending_review"]
    with pytest.raises(ValueError, match="no longer pending"):
        runner.review(identifier, "normal", "stale-review", "approve", background=False)
    for edit in [{"amount": 9}, {"order_id": "ORD-1001", "amount": True, "reason": "x"},
                 {"order_id": "ORD-1001", "amount": float("nan"), "reason": "x"},
                 {"order_id": "ORD-1001", "amount": 9, "reason": "x", "unexpected": 1}]:
        with pytest.raises(ValueError):
            runner.review(identifier, "normal", pending["id"], "edit", args=edit, background=False)
    assert runner.store.get(identifier) == comparison


def test_concurrent_review_submissions_have_one_winner(runner):
    comparison = create(runner, "large-refund")
    pending = comparison["runs"]["normal"]["pending_review"]
    barrier = Barrier(2)

    def approve():
        barrier.wait()
        try:
            runner.review(comparison["id"], "normal", pending["id"], "approve", background=False)
            return "accepted"
        except ValueError as error:
            assert "no longer pending" in str(error)
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(), range(2)))
    assert sorted(results) == ["accepted", "stale"]
    run = runner.store.get(comparison["id"])["runs"]["normal"]
    assert run["status"] == "completed", run["error"]
    assert len(run["world"]["refunds"]) == 1
    assert run["world"]["order"]["refunded_amount"] == 40


def test_pause_survives_store_reopen_and_each_path_resumes_independently(tmp_path):
    settings = Settings(data_dir=tmp_path)
    first = ComparisonRunner(settings)
    try:
        comparison = create(first, "large-refund")
        identifier = comparison["id"]
    finally:
        first.close()
    store = Store(tmp_path)
    try:
        assert store.get(identifier) == comparison
        assert store.list()[0]["id"] == identifier
    finally:
        store.close()

    second = ComparisonRunner(settings)
    try:
        assert second.store.get(identifier)["status"] == "awaiting_review"
        comparison = resolve(second, second.store.get(identifier), "normal")
        assert comparison["runs"]["normal"]["world"]["order"]["refunded_amount"] == 40
        assert comparison["runs"]["jev"]["world"]["refunds"] == []
    finally:
        second.close()

    third = ComparisonRunner(settings)
    try:
        persisted = third.store.get(identifier)
        assert persisted["runs"]["normal"] == comparison["runs"]["normal"]
        result = resolve(third, persisted, "jev")
        assert result["status"] == "completed"
        assert result["analysis"]["agreement"] is True
        for run in result["runs"].values():
            assert len(run["world"]["refunds"]) == 1
            assert len(events(run, "review_requested")) == len(events(run, "review_resolved")) == 1
            assert run["outcome"]["passed"] is True
    finally:
        third.close()


def test_fixture_rejects_custom_task_instead_of_substituting_scripted_evidence(runner):
    with pytest.raises(ValueError, match="original task"):
        create(runner, task="An entirely different task")
    assert runner.store.list() == []


def test_data_directory_has_one_writer_until_runner_closes(tmp_path):
    settings = Settings(data_dir=tmp_path)
    first = ComparisonRunner(settings)
    try:
        comparison = create(first, "large-refund")
        with pytest.raises(ValueError, match="Another runner"):
            ComparisonRunner(settings)
        # A rejected process must not recover, advance, or corrupt the owner's jobs.
        assert first.store.get(comparison["id"]) == comparison
    finally:
        first.close()
    successor = ComparisonRunner(settings)
    try:
        restored = successor.store.get(comparison["id"])
        assert restored == comparison
        result = resolve(successor, restored, "normal")
        assert result["runs"]["normal"]["status"] == "completed"
        assert result["runs"]["normal"]["world"]["order"]["refunded_amount"] == 40
    finally:
        successor.close()


def mock_live_providers(monkeypatch, scenario, failing_kind):
    """Keep the live orchestration path, replacing both providers before invocation."""
    scripted = agent.ScriptedWorker
    original_decisions = agent.JevDecisions

    class ThrowingJev:
        def __init__(self, settings, fixture=False):
            self.fixture_answers = original_decisions(settings, fixture=True)

        def classify(self, state, kind):
            if kind == failing_kind:
                raise RuntimeError("Injected provider outage; test-secret must stay redacted")
            return self.fixture_answers.classify(state, kind)

    monkeypatch.setattr(agent, "local_model", lambda settings: scripted(scenario_id=scenario, order_id="ORD-1001"))
    monkeypatch.setattr(agent, "JevDecisions", ThrowingJev)


def test_triage_outage_is_visible_and_not_graded_as_successful_jev_evidence(tmp_path, monkeypatch):
    mock_live_providers(monkeypatch, "status", "triage")
    runner = ComparisonRunner(Settings(data_dir=tmp_path, jev_token="test-secret"))
    try:
        comparison = runner.create(scenario_id="status", execution="live", background=False)
        normal, jev = (comparison["runs"][path] for path in ("normal", "jev"))
        assert normal["status"] == "completed"
        assert normal["outcome"]["passed"] is True
        assert normal["degraded"] is False
        assert normal["decision_errors"] == []
        assert jev["status"] == "completed"
        assert jev["degraded"] is True
        assert [error["kind"] for error in jev["decision_errors"]] == ["triage"]
        assert jev["triage"]["error"]
        assert jev["workflow"] == "clarify"
        assert events(jev, "error")
        assert jev["metrics"]["jev_calls"] == 1
        assert jev["metrics"]["jev_ms"] > 0
        assert "test-secret" not in json.dumps(comparison)
        # Completing a task via fallback is not proof of a successful Jev decision.
        assert jev["outcome"]["passed"] is None
        assert "Excluded from decision-quality comparison" in jev["outcome"]["label"]
        assert jev["outcome"]["checks"]
    finally:
        runner.close()


def test_risk_outage_requires_review_and_remains_ungraded_after_approval(tmp_path, monkeypatch):
    mock_live_providers(monkeypatch, "missing-item", "risk")
    runner = ComparisonRunner(Settings(data_dir=tmp_path, jev_token="test-secret"))
    try:
        comparison = runner.create(scenario_id="missing-item", execution="live", background=False)
        normal, jev = (comparison["runs"][path] for path in ("normal", "jev"))
        assert normal["status"] == "completed"
        assert normal["world"]["order"]["refunded_amount"] == 9
        assert jev["status"] == "awaiting_review"
        assert jev["degraded"] is True
        assert [error["kind"] for error in jev["decision_errors"]] == ["risk"]
        assert jev["world"]["refunds"] == []
        assert "unavailable" in jev["pending_review"]["reason"]
        risk_events = events(jev, "jev_risk")
        assert len(risk_events) == 1
        assert risk_events[0]["detail"]["error"]
        assert risk_events[0]["detail"]["needs_review"] is True
        comparison = resolve(runner, comparison, "jev")
        jev = comparison["runs"]["jev"]
        assert jev["status"] == "completed"
        assert jev["world"]["order"]["refunded_amount"] == 9
        assert len(jev["world"]["refunds"]) == 1
        assert jev["metrics"]["jev_calls"] == 2  # Checkpoint resume uses the cached failure.
        assert len(events(jev, "jev_risk")) == 1
        assert "test-secret" not in json.dumps(comparison)
        assert jev["outcome"]["passed"] is None
        assert len(jev["decision_errors"]) == 1
        assert "Excluded from decision-quality comparison" in jev["outcome"]["label"]
    finally:
        runner.close()


@pytest.mark.parametrize("score,expected_status", [(0.99, "completed"), (1.0, "awaiting_review")])
def test_default_risk_gate_reviews_at_the_uncertain_rubric_level(tmp_path, monkeypatch, score, expected_status):
    scripted = agent.ScriptedWorker
    original_decisions = agent.JevDecisions

    class BoundaryJev:
        def __init__(self, settings, fixture=False):
            self.fixture_answers = original_decisions(settings, fixture=True)

        def classify(self, state, kind):
            response = self.fixture_answers.classify(state, kind)
            if kind == "risk":
                response["answers"]["risk"]["score"] = score
                response["answers"]["risk"]["probabilities"] = {"0": 1 - score, "1": score, "2": 0}
            return response

    monkeypatch.setattr(agent, "local_model", lambda settings: scripted(scenario_id="missing-item", order_id="ORD-1001"))
    monkeypatch.setattr(agent, "JevDecisions", BoundaryJev)
    runner = ComparisonRunner(Settings(data_dir=tmp_path, jev_token="test-secret"))
    try:
        comparison = runner.create(scenario_id="missing-item", execution="live", background=False)
        jev = comparison["runs"]["jev"]
        assert jev["status"] == expected_status
        assert comparison["runs"]["normal"]["world"]["order"]["refunded_amount"] == 9
        risk = events(jev, "jev_risk")[0]["detail"]
        assert risk["needs_review"] is (score == 1.0)
        if score == 1.0:
            assert jev["pending_review"]
            assert jev["world"]["refunds"] == []
        else:
            assert jev["world"]["order"]["refunded_amount"] == 9
    finally:
        runner.close()


def test_live_decisions_use_shared_facts_without_evaluation_label_leakage(tmp_path, monkeypatch):
    from langchain_core.messages import HumanMessage, ToolMessage

    captured_decisions = []
    worker_messages = []
    original_decisions = agent.JevDecisions

    class CapturingWorker(agent.ScriptedWorker):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            worker_messages.append(deepcopy(messages))
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    class CapturingJev:
        def __init__(self, settings, fixture=False):
            self.fixture_answers = original_decisions(settings, fixture=True)

        def classify(self, state, kind):
            captured_decisions.append((kind, deepcopy(state)))
            return self.fixture_answers.classify(state, kind)

    monkeypatch.setattr(agent, "local_model", lambda settings: CapturingWorker(scenario_id="unjustified-refund", order_id="ORD-1001"))
    monkeypatch.setattr(agent, "JevDecisions", CapturingJev)
    runner = ComparisonRunner(Settings(data_dir=tmp_path, jev_token="test-secret"))
    try:
        comparison = runner.create(scenario_id="unjustified-refund", execution="live", background=False)
        assert comparison["status"] == "awaiting_review"
        assert [kind for kind, _ in captured_decisions] == ["triage", "risk"]
        states = dict(captured_decisions)

        def assert_no_labels(value):
            if isinstance(value, dict):
                assert not {"scenario_id", "expected"}.intersection(value)
                for child in value.values():
                    assert_no_labels(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_labels(child)

        for _, state in captured_decisions:
            assert_no_labels(state)
            assert "unjustified-refund" not in json.dumps(state)
        initial_messages = [messages for messages in worker_messages if not any(isinstance(m, ToolMessage) for m in messages)]
        assert len(initial_messages) == 2
        initial_inputs = [next(m.content for m in messages if isinstance(m, HumanMessage)) for messages in initial_messages]
        assert initial_inputs[0] == initial_inputs[1]
        task, fixture_json = initial_inputs[0].split("\n\nShared starting context:\n", 1)
        fixture = json.loads(fixture_json)
        assert states["triage"] == {"task": task, "fixture": fixture}
        assert states["risk"]["task"] == task == comparison["task"]
        assert states["risk"]["verified_order"]["order"] == fixture["order"]
        assert fixture == comparison["snapshot"]["fixture"]
        human_context = [m["content"] for m in states["risk"]["conversation"] if m["role"] == "human"]
        assert human_context == [initial_inputs[0]]
        # Evaluation identity stays in the comparison record, outside model evidence.
        assert comparison["snapshot"]["scenario_id"] == "unjustified-refund"
    finally:
        runner.close()


@pytest.mark.parametrize("changed", [
    {"model": "different-worker"},
    {"max_tokens": 512},
    {"risk_threshold": 1.5},
    {"base_url": "http://localhost:9876/v1"},
])
def test_changed_execution_settings_cannot_resume_or_mutate_pending_review(tmp_path, changed):
    settings = Settings(data_dir=tmp_path, jev_token="private-jev-test-key", llm_api_key="private-llm-test-key")
    first = ComparisonRunner(settings)
    try:
        comparison = create(first, "large-refund")
        assert comparison["snapshot"]["execution_config"] == settings.execution_identity()
        serialized = json.dumps(comparison)
        assert "private-jev-test-key" not in serialized
        assert "private-llm-test-key" not in serialized
    finally:
        first.close()

    restarted = ComparisonRunner(replace(settings, **changed))
    try:
        for path in ("normal", "jev"):
            with pytest.raises(ValueError, match="Execution settings changed"):
                resolve(restarted, comparison, path)
        persisted = restarted.store.get(comparison["id"])
        assert persisted == comparison
        assert persisted["status"] == "awaiting_review"
        for run in persisted["runs"].values():
            assert run["status"] == "awaiting_review"
            assert run["pending_review"]
            assert run["world"]["refunds"] == []
            assert run["world"]["order"]["refunded_amount"] == 0
    finally:
        restarted.close()
