# Sample repository: learning review

Reviewed October 28, 2026 from the local `agentic_harness_with_jev-main` archive. This is a source-based architecture review; the application was not started and no inference calls were made. Performance and correctness claims below are limited accordingly.

## Core idea

The sample implements customer support for a fictional food-delivery company. A chat LLM proposes responses and tool calls. Jev classifies customer messages and assesses selected proposed refunds. Python rules use those predictions to control prompts, model routing, escalation, and human review.

This is a substantial application demo, including two Next.js frontends, a FastAPI backend, SQLite business data, LangGraph checkpoints, and a persistent event timeline. Its breadth makes the decision-model lesson harder to isolate.

## Reading path through the whole application

All paths in this section refer to the supplied sample, not the new implementation.

| Layer | Files to read | What it contributes |
| --- | --- | --- |
| Setup | `README.md`, `pyproject.toml`, `src/config.py` | Dependencies, tunable thresholds, storage, cloud model IDs |
| Entry points | `main.py`, `src/cli.py`, `api.py`, `src/api.py` | Terminal/web turn submission, approval/resume, frontend data |
| Agent assembly | `src/agents/agent.py`, `src/middleware/__init__.py` | `create_agent`, tools, runtime context, ordered middleware, checkpointer |
| Jev questions | `src/classification/jev.py` | Batched triage and separate proposed-refund risk scoring |
| Agent state | `src/context.py`, `src/middleware/state.py`, `src/middleware/triage.py` | Customer context, predictions, turn counters, frustration history, escalation state |
| Prompt construction | `src/middleware/skills.py`, `src/prompts/`, `src/skills/` | Base instructions, voice, one selected playbook, triage and escalation directives |
| Model selection | `src/middleware/routing.py`, `src/models/` | Pure route rules and chat-model clients |
| Action control | `src/middleware/risk_gate.py`, `src/middleware/refund_policy.py`, `src/policy.py` | Human review, policy revalidation, hard financial/stage constraints |
| Tools and data | `src/tools/`, `src/db/database.py` | Order lookups, simulated refunds/vouchers/cancellations, escalation, conversation closure |
| Memory | `src/memory/memory.py` | SQLite checkpoint persistence and model-based summarization |
| Observation | `src/trace.py`, `src/middleware/tracing.py` | Durable structured events and conversation record |
| Conversation management | `src/threads.py`, `src/titles.py` | Open/closed state and model-generated titles |
| Operator UI | `dashboard/components/`, `dashboard/app/`, `dashboard/lib/` | Event timeline, meters, approvals, escalation replies, attention queues |
| Customer UI | `chat/components/`, `chat/app/`, `chat/lib/` | Customer conversation/history, waiting states, event updates |
| Scenario guide | `TESTING.md` | Manual demo prompts and expected behaviors |

## One message, end to end

1. CLI or API submits a customer message with runtime customer context and a thread ID.
2. The compiled agent restores its checkpoint. Tracing captures the turn.
3. `JevTriageMiddleware` classifies the latest `HumanMessage`; tool-loop iterations reuse that result.
4. One TypeSafe request asks four questions: category (`Choice`), urgency (`Noul`), frustration (`Score`), and need for reasoning (`Noul`).
5. Python updates frustration history and escalation flags using predictions plus order/policy data.
6. Summarization may compact old messages. The dynamic prompt selects a support playbook from the predicted category.
7. Routing rules choose the fast or reasoning model. The LLM then responds or proposes a tool call.
8. For a proposed refund, deterministic policy first identifies hard denial, required review, or an otherwise-allowed amount. Only the otherwise-allowed case gets a Jev risk assessment.
9. Review can interrupt execution. An operator approves, edits, or rejects in the dashboard; checkpoint resume continues the agent.
10. Final policy checks the actual arguments before a tool mutates the simulated data. Tool results return to the LLM, and trace events reach the UI.

The workflow can loop through multiple tools; Jev triage does not rerun for each tool result.

## What Jev actually controls

| Prediction | Returned meaning | Consumer and effect |
| --- | --- | --- |
| Category | A selected workflow and confidence | Selects a playbook; influences model choice and escalation |
| Urgency | Probability of the urgency statement being true | Supplies urgency context/priority signals |
| Frustration | Expected score on a three-level rubric, 0–2 | Feeds mood history and routing/escalation/cancellation rules |
| Needs reasoning | Probability that the task needs more reasoning | Feeds fast/reasoning route selection |
| Tool risk | Expected score on a three-level risk rubric, 0–2 | Requests review when an otherwise-allowed refund reaches the threshold |

Jev does not generate the response, call the tool, set monetary policy, or grant authorization itself. A `Noul` value is a probability of yes; a `Score` value is a position on the supplied ordered rubric. Category confidence is another field and should not be conflated with either.

The sample's actual routing rules prioritize escalation, designated categories, reasoning probability ≥0.5, frustration ≥1.5, and category confidence <0.6. Otherwise they choose the fast model.

The risk path is narrower than “Jev guards every action”: refunds over the automatic threshold go directly to review, hard-denied refunds skip Jev scoring, vouchers always require review, and cancellation follows its own policy.

## Strong ideas to retain

- One batched classification supplies multiple orchestration decisions.
- A shared typed state connects prediction to routing, prompts, and policy.
- Explicit Python routing and business-policy functions make decisions inspectable.
- Hard policy checks edited arguments after human review.
- Persistent events show model decisions, tool activity, review, and final responses.
- The UI displays question types, scores, and threshold markers.

These features show where a decision model fits into an agent harness. They do not, by themselves, measure its incremental benefit.

## Gaps to address in the teaching repo

1. **No controlled comparison.** Manual demo scenarios exist, but no automated benchmark or test suite was found. There is no ordinary-agent versus Jev-assisted-agent comparison showing what changes when selected orchestration decisions move to Jev.
2. **Incomplete decision evidence.** Response extraction discards category distributions, Score distributions/confidence, usage, request IDs, and measured duration. `Triage.raw` is defined but never populated. Tool risk becomes just one number.
3. **Prediction and consequence are separated in the UI.** The “Jev decisions only” filter can remove routing/policy/tool outcomes. Teaching requires showing them together.
4. **Context is too narrow for follow-ups.** Triage sees only the newest message. All requests must fit five overlapping categories, with no general/uncertain option. Low category confidence changes model routing but still injects one selected playbook.
5. **Risk omits verified tool evidence.** Its transcript takes a recent message window and removes tool messages, which can exclude relevant order facts and amounts.
6. **Failure behavior is not explicit at the adapter boundary.** There is no local, documented policy for classifier outages or invalid responses. The new example should make uncertainty/error handling part of the lesson.
7. **Business complexity hides the mechanism.** Frustration affects cancellation eligibility, while the implementation does not verify that a remedy was actually attempted in the way its narrative suggests. The new foundational example should omit that ladder.
8. **Documentation and runtime have drifted.** Actual configuration uses `openai:gpt-5.4-mini` and `openai:gpt-6-astra`; README/comments/constant names mention different models. Some instructions describe older CLI behavior.
9. **Local adaptation reaches beyond the agent model.** Four clients initialize at import, including summarization and title generation. Listing dashboard threads can trigger model calls. Avoid those hidden dependencies in the teaching version.
10. **The CLI is not independent for review cases.** It waits for the API/dashboard to resume approvals. Provide a CLI review path and clear dashboard startup instructions.
11. **Fixtures are not isolated evaluations.** Reseeding business tables leaves checkpoints and traces, and dates are relative. Comparisons need independent scenario state and fixed time.
12. **UI constants duplicate policy.** Several thresholds are embedded in TypeScript. The backend should emit the thresholds actually used by a run.

The two frontends are organizational separation, not evidence of production authentication. The new UI should present itself as a local learning sandbox, with simulated data and actions.

## Extraction strategy

Use the sample as an architectural reference. Build a smaller support workflow with explicit decision schemas and rules, then layer an interactive trace dashboard over that working core. Keep the dashboard in v1 as requested; reduce its product-management features so the decision lesson remains central.

The MVP compares exactly two paths:

1. **Ordinary LangChain agent:** the existing local generative LLM chooses its actions and workflow.
2. **Jev-assisted LangChain agent:** the same local worker LLM generates responses and proposed tool calls, while hosted Jev scores proposed refunds for an explicit Python review gate and supplies advisory triage guidance.

Both paths use the same tools, task information, hard policy, worker model and generation settings. Run each scenario with fresh business data and checkpoints and a fixed fixture time. Show the decisions and tool sequences alongside task outcomes, call counts, decision latency, and end-to-end latency; report model-loading overhead and human waiting separately.

This comparison measures the overall effect of adding the Jev-assisted harness. It does not perfectly isolate the decision model's contribution, because the playbook prompt hint and refund-review condition change together. In the implemented demo, triage does not filter tools or enforce routing. Record those differences and report both improvements and regressions without attributing every change solely to Jev. A separate local decision model or structured-decision classifier baseline is outside the agreed MVP.

The sample is Apache-2.0 licensed; the destination currently has MIT. Preserve applicable source notices for adapted material and establish upstream provenance before public release. The downloaded archive has no Git history, so implementation evolution has not been independently verified.

See the [project README](../README.md) for the implemented scope and dashboard, and the [evaluation guide](evaluation.md) for comparison methods and limitations.
