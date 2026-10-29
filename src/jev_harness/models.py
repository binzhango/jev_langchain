"""One local worker model for both paths; a scripted model only for fixture mode."""
import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from .config import Settings


def local_model(settings: Settings):
    return ChatOpenAI(
        base_url=settings.base_url, api_key=settings.llm_api_key, model=settings.model,
        temperature=0, timeout=settings.llm_timeout, max_tokens=settings.max_tokens,
        max_retries=0, stream_usage=False, use_responses_api=False,
    )


class ScriptedWorker(BaseChatModel):
    """Runs the real orchestration code with explicitly synthetic model responses."""
    scenario_id: str
    order_id: str

    @property
    def _llm_type(self) -> str:
        return "scripted-walkthrough"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        results = [m for m in messages if isinstance(m, ToolMessage)]
        if self.scenario_id == "ambiguous":
            reply = AIMessage(content="Which item was missing or incorrect? I need that detail before changing your order.")
        elif not results:
            reply = self._call("lookup_order", {"order_id": self.order_id}, "lookup")
        elif len(results) == 1 and self.scenario_id != "status":
            amount = {"missing-item": 9, "large-refund": 40, "unjustified-refund": 9, "hard-ceiling": 250}[self.scenario_id]
            reply = self._call("issue_refund", {"order_id": self.order_id, "amount": amount,
                               "reason": "Customer's refund request", "request_review": self.scenario_id == "unjustified-refund"}, "refund")
        else:
            # Facts from actual tools; no fabricated success after denial/rejection.
            reply = AIMessage(content="Scripted walkthrough completed. The tool returned: " + str(results[-1].content))
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def _call(self, name, args, suffix):
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"fixture-{suffix}", "type": "tool_call"}])
