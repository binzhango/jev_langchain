# Jev Decision Lab

**One task. Two LangChain agents. Inspect what changes when Jev makes orchestration decisions.**

Enter a support task once and run it through two paths:

| Normal agent | Jev-assisted agent |
| --- | --- |
| Your local LLM chooses its next action using the task, tools, and policy instructions. | Hosted Jev classifies the task and assesses proposed refunds. Python turns those predictions into workflow and review decisions. |
| The local LLM generates tool calls and responses. | The **same local LLM** generates tool calls and responses. |

Both get the same task, fixture facts, tools, policy knowledge, model, and generation settings. Each has independent order data and checkpoints. There is no separate local decision model.

The dashboard puts the two traces next to one another: proposed actions, arguments, policy verdicts, tool results, approvals, and final responses. The Jev column adds the exact state, questions, typed answers, probability distributions, and rules that consumed them.

## Start locally with uv

Install [uv](https://docs.astral.sh/uv/) and [Node.js with npm](https://nodejs.org/) (20.19+, 22.12+, or newer). On macOS, Linux, or WSL, open a terminal in this repository and run **one command**:

```bash
bash start.sh
```

The launcher uses uv to set up Python and the locked dependencies, installs and builds the frontend, and starts **both the dashboard and API in one service**. On first launch it asks for your local model URL, model ID, and optional credentials, saving new values in the private, ignored `.env` file. Existing `.env` files and exported credentials are preserved. Start your LM Studio or other local model server separately for live comparisons; you can skip the Jev token to explore scripted walkthroughs.

Open [localhost:8000](http://localhost:8000). Select a scenario, inspect the task, and choose **Run both paths**. Press **Ctrl+C** in the terminal to stop the app. Use the same command next time. The runs execute sequentially to avoid competing for one local server, while their traces appear in aligned columns. Approve, edit, or reject any pending refund in its column.

The app reads `JEV_TOKEN`, falling back to `TYPESAFE_API_KEY`. It explicitly passes that value to the TypeSafe client. Credentials stay out of browser responses and trace records. No paid generative-model provider is needed. [Local setup and troubleshooting](docs/local-setup.md)

For a walkthrough without model calls, choose **Scripted fixture** in the dashboard, or run:

```bash
uv run jev-lab compare --scenario missing-item --execution fixture
```

Fixture mode uses synthetic Jev values and scripted agent responses through the real policy/review machinery. It is labeled throughout and is **not a benchmark or a recording of model behavior**. Custom task text requires live mode.

## What Jev does

The important boundary is:

```text
Shared task and facts
  → Jev: state + questions → typed predictions
  → Python: predictions + thresholds → workflow / review decision
  → Local LLM: proposed tool calls and response
  → Hard policy: validate the actual action → simulated tool effect
```

- **Choice** selects a support workflow and returns probabilities and confidence.
- **Noul** gives the probability that a statement is true. Urgency is demonstrated this way.
- **Score** locates a case on an ordered rubric. Proposed-action risk is compared with an explicit review threshold.

Jev does not write the final answer or authorize a refund itself. Python enforces ownership, finite whole-cent amounts, a $200 ceiling, the remaining order value, and duplicate protection in both paths. Refunds over $25 require review. Reviewed edits are checked again before execution. Frustration and urgency are visible teaching signals; they do not silently change monetary entitlement. [Decision anatomy](docs/concepts.md)

## Learn in small steps

```bash
uv run python examples/01_jev_primitives.py
uv run python examples/02_local_agent.py
uv run python examples/03_jev_workflow.py
uv run python examples/04_jev_tool_review.py
uv run python examples/05_compare.py --scenario missing-item
```

Read [decisions.py](src/jev_harness/decisions.py) for the actual Jev questions, [agent.py](src/jev_harness/agent.py) for the LangChain hooks, and [domain.py](src/jev_harness/domain.py) for the rules shared by both agents. [Walkthrough of the original sample](docs/sample-walkthrough.md)

## Compare real behavior

For a **decision-only benchmark**, give Jev and the existing local LLM the exact same state and question, without agent/tool-loop differences:

```bash
uv run jev-lab benchmark --repeat 3 --output artifacts/benchmark
```

This writes JSON evidence, a Markdown comparison, and a standalone HTML report. It uses the existing local chat model to answer decision questions; no local decision model is required. See [benchmark methodology](docs/decision-benchmark.md).

Six seeded cases cover a status inquiry, a justified small refund, a larger refund requiring review, an unsupported small refund, an ambiguous request, and a prohibited payout. Custom tasks reuse a selected fixture and remain ungraded unless you supply your own assessment.

```bash
uv run jev-lab compare --scenario missing-item --output artifacts/my-comparison.json
uv run jev-lab evaluate --execution live --repeat 3 --review reject --output artifacts/evaluation.json
uv run pytest -q
```

`compare` offers interactive CLI approval, editing, and rejection. In a noninteractive terminal it leaves reviews pending for the dashboard. Evaluation uses a declared reviewer policy (`reject` by default); that choice can prevent a justified large refund from completing, so inspect individual checks rather than interpreting every failed outcome as a model error.

The reports retain completed, incomplete, and failed runs; actual side effects; call counts; reported usage; timing; and the first divergent action. Human waiting is separate from execution time. Repeated runs alternate which path goes first. Saved comparisons and paused graph checkpoints persist in the ignored `artifacts/` directory.

One process owns a data directory at a time. Use the dashboard while its server is running; for a separate CLI experiment, stop the server or set `JEV_LAB_DATA_DIR=artifacts/cli`. This prevents two processes from resuming the same approval.

This compares **adding the Jev-assisted harness as a whole**. Workflow context and review rules change along with the decision source. A normal LLM often decides within a generation it already needs, so Jev can add latency. This repo measures the effect rather than assuming faster or better results. [Evaluation method and limits](docs/evaluation.md)

Two live integration examples and their complete traces are available in [observed results](docs/observed-results.md). Both paths executed the correct simulated refunds; timings varied, and one response incorrectly described the approval state. The recordings illustrate why action checks and response quality must be assessed separately.

## Project map

```text
src/jev_harness/
  decisions.py   Jev questions, full responses, explicit workflow rules
  agent.py       two LangChain paths, tracing, policy and review middleware
  domain.py      fixtures, simulated tools, shared deterministic rules
  runner.py      identical inputs, independent state, checkpoints, comparisons
  store.py       durable JSON event records in SQLite
  api.py         local dashboard API
  cli.py         uv commands, provider probes, paired evaluation
dashboard/       React + Vite learning workspace
examples/        numbered runnable lessons
tests/           policy, isolation, approval/resume, and API checks
docs/            concepts, original-sample walkthrough, setup, evaluation
```

This is a local educational sandbox. All orders, payments, and escalations are simulated. Keep the server bound to localhost; it is not a production customer-support service.

## Background

Inspired by [LangChain's Building a Harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev), the [TypeSafe integration](https://docs.langchain.com/oss/python/integrations/providers/typesafe), and the supplied `agentic_harness_with_jev-main` sample. This implementation was authored as a smaller teaching project; the original sample's architectural review is in [the sample review](docs/sample-review.md). The original archive carries Apache-2.0; this repository's new code is covered by its [MIT license](LICENSE).
