"""Inspect risk and the threshold without executing a refund."""
import json
from jev_harness.config import Settings
from jev_harness.decisions import JevDecisions
from jev_harness.domain import SupportWorld, get_scenario

settings = Settings.from_env()
scenario = get_scenario("unjustified-refund")
world = SupportWorld(scenario["fixture"])
args = {"order_id": "ORD-1001", "amount": 9, "reason": "Customer requested money back"}
policy = world.evaluate_refund(args)
response = JevDecisions(settings).classify({
    "task": scenario["task"], "proposed_action": {"tool": "issue_refund", "arguments": args},
    "verified_order": world.lookup(args["order_id"]),
}, "risk")
score = response["answers"]["risk"]["score"]
print(json.dumps({"hard_policy": policy, "jev_response": response,
                  "threshold": settings.risk_threshold, "needs_review": score >= settings.risk_threshold,
                  "executed": False}, indent=2))
