# Walkthrough of the supplied sample

The supplied `agentic_harness_with_jev-main` archive is a food-delivery support application. Its main idea is useful: a generative model talks and proposes tools, while Jev predictions influence how the harness runs that model. The application also includes business policy, conversation management, two web frontends, and a database. Reading those as separate layers makes Jev's role easier to see.

This walkthrough describes the inspected sample source, not claims from executing it. The complete review is in [the sample review](sample-review.md). Paths below belong to that archive. Its upstream repository URL has not been established, so these are reading instructions rather than public source links.

## 1. Find the assembly point

Start with `main.py` and `src/cli.py`, then read `src/agents/agent.py`. The builder creates a LangChain `create_agent` with tools, middleware, runtime customer context, and a SQLite checkpointer. `src/middleware/__init__.py` supplies the order of the hooks.

Customer identity is runtime context used by tools, rather than a tool argument selected by the model. The web demo supplies its session/customer context itself; the separate chat/dashboard applications do not establish production authentication.

## 2. Inspect the questions before the answers

Read `src/classification/jev.py`. It defines two uses of Jev:

- **Triage:** category (`Choice`), urgency (`Noul`), frustration (`Score`), and need for reasoning (`Noul`) share one request.
- **Proposed-refund risk:** a separate `Score` evaluates an applicable tool call.

These outputs are predictions about supplied state. They become behavior only after other code consumes them. `src/middleware/state.py` shows which values persist in the agent state.

The sample's triage classifies the latest human message. `src/middleware/triage.py` avoids redoing triage on iterations caused by tool results. That saves repeated classification, but a context-light follow-up such as “yes, that one” can lose its referent. The teaching implementation therefore makes the decision input inspectable and includes relevant context.

## 3. Follow each prediction into a branch

| Prediction | Sample consumer | Resulting behavior |
| --- | --- | --- |
| Category | `src/middleware/skills.py` | Injects one matching support playbook |
| Category, need for reasoning, confidence, frustration | `src/middleware/routing.py` | Chooses a fast or reasoning chat model |
| Urgency and frustration history | `src/middleware/triage.py`, `src/policy.py` | Influence escalation and remedy rules |
| Proposed-refund risk | `src/middleware/risk_gate.py` | Can request human review |

The prompt combines base instructions, voice, triage, a selected skill, and escalation directives. The sample's `SKILL.md` files are support playbooks consumed by the application. Their selection is a concrete example of classification changing the context seen by a generative model.

Model routing is Python logic. The sample prioritizes escalation, certain policy-sensitive categories, reasoning probability at least 0.5, frustration at least 1.5, and category confidence below 0.6. Otherwise it uses the fast model. Those thresholds are design choices, not properties of Jev.

The new repo keeps one worker model shared between the two paths. It demonstrates advisory playbook selection and a refund risk gate. Playbook selection adds a prompt line; it does not restrict tools or enforce routing.

## 4. Separate semantic review from hard policy

For a proposed refund, policy first identifies a hard denial, mandatory review, or an otherwise-allowed amount. Only the otherwise-allowed case receives the Jev risk assessment. Refunds over the automatic threshold go directly to review; hard-denied refunds skip Jev risk scoring.

The sample also has vouchers and cancellations. Vouchers always require review, while cancellation follows a fulfilment-stage/remedy policy. It would therefore be inaccurate to say that Jev checks every tool call or independently authorizes refunds.

Read `src/middleware/risk_gate.py`, `src/middleware/refund_policy.py`, and `src/policy.py` together. The review middleware can interrupt execution, and the dashboard supplies approve/edit/reject decisions. Final policy must run on the arguments that will actually execute, including an edited amount. Middleware order matters because checking only the original proposal would miss the change.

Then read `src/tools/`. These functions perform lookups and simulated business mutations against SQLite. An entry in the refunds table is the action's observable effect; a reassuring model response alone is not proof that a refund ran.

## 5. Distinguish memory from observation

`src/memory/memory.py` supplies checkpoint persistence and model-based summarization. Checkpoints allow a paused graph to resume; summarization changes the working conversation available to the model.

`src/trace.py` and `src/middleware/tracing.py` serve another purpose: a durable, readable event record. The UI reads structured events rather than decoding serialized checkpoints. Conversation history is taken from trace messages so that a summary does not replace the customer's original words in the chat UI.

`src/threads.py` adds open/closed conversation status. `src/titles.py` asks the fast model to name untitled threads when they are listed. These are support-product features, not Jev mechanisms, and title generation adds model activity outside the customer's turn.

## 6. Trace the user interfaces

`src/api.py` exposes threads, traces, review/resume, human replies, customer chat, and conversation management. Its event stream watches database changes so it can observe CLI activity in another process.

The `dashboard/` Next.js app presents operator queues, decision events, scores, and review controls. The `chat/` Next.js app presents customer messages and pending states. The CLI also relies on the dashboard to resolve reviews, so some sample scenarios require multiple processes.

The most reusable UI idea is a score next to the question and threshold that gave it meaning. The main improvement is to keep the downstream policy/action visible in the same sequence. A filter showing only Jev predictions can hide what those predictions changed.

## 7. Read scenarios as hypotheses

`TESTING.md` contains useful prompts for lookups, missing items, refunds, ambiguity, review edits, and persistence. It is a manual scenario guide, not an automated comparative benchmark. Reseeding resets business data while retaining checkpoints and traces, and fixture dates depend on the current time. Those behaviors make an isolated demo convenient but need changing for repeatable paired runs.

The source also has documentation drift: actual model IDs differ from README names and some comments. Read `src/config.py` for the inspected configuration rather than assuming the prose names the model being invoked.

## What the smaller implementation preserves

The new implementation is authored for this teaching repo, using the sample as an architectural reference. It retains explicit questions, advisory playbook selection and a refund risk gate, hard policy, review, and event inspection. It simplifies the support data and omits the voucher/cancellation ladder, generated titles, and summarization so the first comparison has fewer moving parts.

The primary experience is one task, two independent runs, and side-by-side evidence. The [concept guide](concepts.md) explains those responsibilities; the [evaluation guide](evaluation.md) explains how to interpret differences.

The archive contains an Apache-2.0 license; this repository uses MIT for its new code. No wholesale archive copy is used. If sample source is adapted in later work, retain the applicable upstream license and attribution notices and identify its provenance.
