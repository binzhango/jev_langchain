"""The smallest local LangChain tool loop; no Jev or local decision model."""
from langchain.agents import create_agent
from langchain.tools import tool
from jev_harness.config import Settings
from jev_harness.domain import SupportWorld, get_scenario
from jev_harness.models import local_model

scenario = get_scenario("status")
world = SupportWorld(scenario["fixture"])

@tool
def lookup_order(order_id: str) -> dict:
    """Look up this customer's verified order status."""
    return world.lookup(order_id)

agent = create_agent(local_model(Settings.from_env()), tools=[lookup_order],
                     system_prompt="Look up the order before answering. Be concise.")
result = agent.invoke({"messages": [{"role": "user", "content": scenario["task"]}]})
for message in result["messages"]:
    print(message.type, message.content, getattr(message, "tool_calls", ""))
