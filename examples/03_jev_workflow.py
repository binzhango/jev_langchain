"""Jev Choice selects a prompt hint; it does not enforce routing or filter tools.

This example always exposes lookup_order, regardless of the selected category.
"""
import json
from langchain.agents import create_agent
from langchain.tools import tool
from jev_harness.config import Settings
from jev_harness.decisions import JevDecisions, workflow, PLAYBOOKS
from jev_harness.domain import SupportWorld, get_scenario
from jev_harness.models import local_model

settings = Settings.from_env()
scenario = get_scenario("status")
world = SupportWorld(scenario["fixture"])
decision = JevDecisions(settings).classify({"task": scenario["task"], "fixture": world.data})
selected, rule = workflow(decision)
print(json.dumps({"prediction": decision["answers"]["category"], "workflow": selected, "rule": rule}, indent=2))

@tool
def lookup_order(order_id: str) -> dict:
    """Look up this customer's verified order status."""
    return world.lookup(order_id)

agent = create_agent(local_model(settings), tools=[lookup_order], system_prompt=PLAYBOOKS[selected])
result = agent.invoke({"messages": [{"role": "user", "content": scenario["task"]}]})
print(result["messages"][-1].text)
