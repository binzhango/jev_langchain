"""Exercise the real local API and fixture runner without contacting model services."""

import socket
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from jev_harness import agent, api, decisions
from jev_harness.api import create_app
from jev_harness.config import Settings


@pytest.fixture(autouse=True)
def forbid_model_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("API tests must not contact an external model service")

    monkeypatch.setattr(agent, "local_model", forbidden)
    monkeypatch.setattr(decisions, "TypeSafeClassifier", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path)), base_url="http://127.0.0.1") as value:
        yield value


def wait_for(client, identifier, predicate, timeout=10):
    deadline = monotonic() + timeout
    last = None
    while monotonic() < deadline:
        response = client.get(f"/api/comparisons/{identifier}")
        assert response.status_code == 200
        last = response.json()
        if predicate(last):
            return last
        sleep(0.01)
    pytest.fail(f"Comparison did not reach the expected state: {last}")


def settled(value):
    return all(
        run["status"] in {"completed", "error", "awaiting_review"}
        for run in value["runs"].values()
    )


def start_fixture(client, scenario="missing-item"):
    response = client.post("/api/comparisons", json={
        "scenario_id": scenario, "execution": "fixture",
    })
    assert response.status_code == 202
    return wait_for(client, response.json()["id"], settled)


def test_public_configuration_never_returns_credentials(tmp_path):
    settings = Settings(data_dir=tmp_path, jev_token="test-jev-secret", llm_api_key="test-worker-secret")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        response = client.get("/api/config")
        assert response.status_code == 200
        config = response.json()
        assert config["jev_configured"] is True
        assert config["model"] == settings.model
        assert config["base_url"] == settings.base_url
        assert set(config) == {
            "model", "base_url", "jev_model", "jev_configured", "risk_threshold",
            "auto_refund_limit", "hard_refund_limit",
        }
        assert settings.jev_token not in response.text
        assert settings.llm_api_key not in response.text


def test_fixture_comparison_completes_and_exports_the_saved_record(client):
    scenarios = client.get("/api/scenarios")
    assert scenarios.status_code == 200
    task = next(case["task"] for case in scenarios.json() if case["id"] == "missing-item")
    created = start_fixture(client)
    result = wait_for(client, created["id"], lambda value: value["analysis"]["agreement"] is not None)
    assert result["status"] == "completed"
    assert result["source"] == "fixture"
    assert result["task"] == task
    for run in result["runs"].values():
        assert run["status"] == "completed"
        assert run["outcome"]["passed"] is True
        assert run["metrics"]["llm_calls"] == 0
        assert run["metrics"]["jev_calls"] == 0
        assert len(run["world"]["refunds"]) == 1
        event = next(event for event in run["events"] if event["type"] == "input")
        assert event["detail"]["input_hash"] == result["input_hash"]
    assert result["snapshot"]["fixture"]["refunds"] == []
    jev_event = next(event for event in result["runs"]["jev"]["events"] if event["type"] == "jev_triage")
    assert jev_event["detail"]["source"] == "synthetic"

    exported = client.get(f"/api/comparisons/{result['id']}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert f"comparison-{result['id']}.json" in exported.headers["content-disposition"]
    assert exported.json() == client.get(f"/api/comparisons/{result['id']}").json()
    assert client.get("/api/comparisons").json()[0]["id"] == result["id"]


def test_fixture_rejects_custom_text_without_creating_a_comparison(client):
    response = client.post("/api/comparisons", json={
        "scenario_id": "missing-item", "execution": "fixture", "task": "An unrelated custom request",
    })
    assert response.status_code == 400
    assert "original task" in response.json()["detail"]
    assert client.get("/api/comparisons").json() == []


def test_live_without_jev_token_fails_before_any_model_call(client):
    response = client.post("/api/comparisons", json={
        "scenario_id": "missing-item", "execution": "live",
    })
    assert response.status_code == 400
    assert "JEV_TOKEN" in response.json()["detail"]
    assert client.get("/api/comparisons").json() == []


@pytest.mark.parametrize("suffix", ["", "/export"])
def test_missing_comparison_returns_404(client, suffix):
    response = client.get(f"/api/comparisons/does-not-exist{suffix}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Comparison not found."}


def test_missing_review_comparison_returns_404(client):
    response = client.post("/api/comparisons/does-not-exist/review", json={
        "path": "normal", "review_id": "unknown-review", "decision": "approve",
    })
    assert response.status_code == 404
    assert response.json() == {"detail": "Comparison not found."}


@pytest.mark.parametrize('origin', ['https://evil.example', 'null', 'http://localhost.evil.example:8000', 'http://localhost:9000', 'http://[invalid'])
def test_foreign_origins_cannot_create_comparisons(client, origin):
    response = client.post('/api/comparisons', headers={'origin': origin}, json={'execution': 'fixture'})
    assert response.status_code == 403
    assert client.get('/api/comparisons').json() == []


@pytest.mark.parametrize('host', ['evil.example', 'localhost.evil.example', '127.0.0.1.evil.example', 'localhost@evil.example'])
def test_untrusted_host_rejected(client, host):
    assert client.get('/api/config', headers={'host': host}).status_code == 400


@pytest.mark.parametrize('origin', ['http://127.0.0.1', 'http://localhost:5173', 'http://127.0.0.1:5173'])
def test_local_ui_origins_work(client, origin):
    assert client.get('/api/config', headers={'origin': origin}).status_code == 200


def test_benchmark_report_is_read_only_and_restricts_filenames(client, tmp_path):
    assert client.get('/benchmark/report.html').status_code == 404
    folder = tmp_path / 'benchmark'
    folder.mkdir()
    (folder / 'report.html').write_text('<h1>Recorded benchmark</h1>')
    response = client.get('/benchmark/report.html')
    assert response.status_code == 200
    assert response.text == '<h1>Recorded benchmark</h1>'
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/benchmark/secrets.env').status_code == 422


def test_stale_review_is_rejected_and_cannot_repeat_a_payment(client):
    comparison = start_fixture(client, "large-refund")
    assert comparison["status"] == "awaiting_review"
    pending = comparison["runs"]["normal"]["pending_review"]
    url = f"/api/comparisons/{comparison['id']}/review"
    stale = client.post(url, json={
        "path": "normal", "review_id": "stale-review", "decision": "approve",
    })
    assert stale.status_code == 400
    assert "no longer pending" in stale.json()["detail"]
    unchanged = client.get(f"/api/comparisons/{comparison['id']}").json()
    assert unchanged["runs"]["normal"]["pending_review"] == pending
    assert unchanged["runs"]["normal"]["world"]["refunds"] == []

    approved = {"path": "normal", "review_id": pending["id"], "decision": "approve"}
    assert client.post(url, json=approved).status_code == 202
    assert client.post(url, json=approved).status_code == 400
    result = wait_for(client, comparison["id"], lambda value: value["runs"]["normal"]["status"] in {"completed", "error"})
    assert result["runs"]["normal"]["status"] == "completed"
    assert len(result["runs"]["normal"]["world"]["refunds"]) == 1
    assert result["runs"]["normal"]["world"]["refunds"][0]["amount"] == 40
    assert result["runs"]["jev"]["status"] == "awaiting_review"
    assert result["runs"]["jev"]["world"]["refunds"] == []


def test_root_has_useful_fallback_without_a_built_dashboard(tmp_path, monkeypatch):
    # Resolve the static directory beneath an empty tree without moving a real build.
    monkeypatch.setattr(api, "__file__", str(tmp_path / "no-build" / "src" / "jev_harness" / "api.py"))
    with TestClient(create_app(Settings(data_dir=tmp_path / "data")), base_url="http://127.0.0.1") as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "npm --prefix dashboard run build" in response.json()["message"]
        assert response.json()["api_docs"] == "/docs"
        assert client.get("/api/scenarios").status_code == 200
