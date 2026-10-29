"""One state, several typed questions. No agent or text generation involved."""
import json
from jev_harness.config import Settings
from jev_harness.decisions import JevDecisions
from jev_harness.domain import get_scenario

scenario = get_scenario("missing-item")
response = JevDecisions(Settings.from_env()).classify({
    "task": scenario["task"], "fixture": scenario["fixture"],
})
# Includes exact state/questions, all answers/distributions, usage and request ID.
print(json.dumps(response, indent=2))
