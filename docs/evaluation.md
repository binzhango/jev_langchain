# Comparing the normal and Jev-assisted agents

The experiment asks: **what changes when a Jev refund risk gate and an advisory triage prompt are added to this LangChain support agent?** Both paths use the same local generative LLM. There is no extra local classifier in the baseline.

This measures the effect of the Jev-assisted harness as a whole. It does not isolate model-only quality: the assisted path adds a playbook prompt hint and an additional condition for pausing refunds for review. Both agents retain all playbooks and the same tools; no workflow-specific tool restrictions are implemented. Report those changes together with their outcomes.

## Run a paired case

After [local setup](local-setup.md):

```bash
uv run jev-lab compare --scenario missing-item
```

In the dashboard, select the scenario or enter one custom task, then select **Run both**. The task text is submitted once. Each path receives a copy of the same starting snapshot and its own mutable tool data. A refund in one path must not make the other path encounter an already-refunded order.

The saved comparison links both runs to the input snapshot and input hash. Use the raw JSON export to inspect inputs, events, actions, outcomes, and metrics. The [API contract](api-contract.md) defines the stored fields.

For repeated live runs:

```bash
uv run jev-lab evaluate --execution live --repeat 3
```

Three repetitions can expose obvious variation; they are not enough to establish a general performance claim. Keep failed and incomplete runs in the report. A result without a completed response or resolved review should not silently enter the successful-run latency average.

`evaluate` defaults to `--review reject`: it rejects every pending action in both paths. This means a justified large refund can fail its expected payment check because of the reviewer policy. You can explicitly select `--review approve` or use `--review ask` in an interactive terminal. Record the choice; unconditional approval can also permit an unjustified action after a model correctly requested review. `compare` defaults to interactive review. Use `--output artifacts/results.json` to save the command's full JSON result.

## What must stay equivalent

- Exact task and initial conversation, customer/order facts, fixed fixture time, and policy version.
- Tool definitions, deterministic limits, and access to the review mechanism.
- Worker model, server configuration, generation settings, and available task/policy knowledge.
- Scenario reset procedure and, for reviewed actions, the declared reviewer policy.

The normal agent receives a competent support prompt and chooses its own next step. Jev supplies additional predictions only in the assisted path. Document the questions, selected playbook prompt hint, thresholds, and failure handling that constitute that intervention.

Evaluation IDs and expected labels are kept out of live inference inputs. Jev triage sees the same task and fixture facts supplied to the local worker; risk assessment also sees the proposed action and verified tool evidence. If Jev is unavailable, the run displays a degraded warning and is excluded from automatic decision-quality scoring, even if the fallback completes a task. Its observed action checks remain inspectable.

The runs can appear side by side while executing sequentially. Concurrent inference on one local server would measure resource contention as well as agent behavior. For repeated measurements, alternate path order and separate cold/model-loading runs from warm runs. Record whether a human or a script resolved reviews; human waiting and differing reviewer choices can dominate the result.

The current runner accepts one submitted task per comparison, followed by its tool-call loop and any review/resume steps. Once the first action differs, later tool results and context may differ too. A future multi-turn evaluation should retain each path's realized history; a focused decision evaluation should use predefined shared checkpoints when both paths must act on precisely the same evidence.

## Read the metrics with their limits

| Evidence | What to examine | What it does not establish |
| --- | --- | --- |
| Task outcome and checks | Whether a labeled scenario reached its expected observable state | General answer quality outside the labels |
| Proposed and executed actions | Tool names, arguments, policy verdicts, and actual results | Private model reasoning |
| First divergence | Where observable action sequences begin to differ | Which path is better |
| Review/allow/deny results | Correctly prevented or unnecessarily delayed actions | Safety on all possible inputs |
| `llm_calls`, `jev_calls`, `tool_calls` | Live model-request attempts and returned tool outcomes; denied/rejected proposals count as tool outcomes | Equal work per count, or proof that every tool body executed |
| `duration_ms` | Accumulated active graph-execution time across initial and resumed invocations | Full user wall time: queueing and human waiting are excluded |
| `review_wait_ms` | Waiting time recorded when a pending review is resolved | An estimate for a review still waiting |
| `jev_ms` | Total time spent in Jev requests, including failed attempts | An equivalent separate baseline classifier time |
| Token usage | Reported input/output token counts | Dollar cost or local energy use |

Read per-event durations alongside aggregate time. The CLI summary reports the median active `duration_ms` for completed live runs; it does not report a full user wall-time median. Failed runs remain in the detailed comparison records. Token totals combine available model usage; use the Jev and model-result events to inspect provider-specific contributions. If provider usage is missing, retain the missing value rather than interpreting it as zero.

The normal agent's orchestration happens within its generation calls. It has no separately measured classifier latency. Jev adds requests; a simple task may finish faster without them. Better review decisions are a hypothesis to test, not an established benefit of this demo. Decision-only hosted-versus-local latency is not a measurement of end-to-end agent speed.

Custom tasks usually have no expected labels. Show their differences without declaring a winner. For labeled tasks, inspect whether the checks capture the intended outcome: a model saying “refunded” is not equivalent to a successful refund tool result. Review false allows, false denials, unnecessary reviews, and unresolved cases separately rather than compressing everything into one success number.

## Fixture execution is a walkthrough

```bash
uv run jev-lab compare --scenario missing-item --execution fixture
```

Fixture mode uses scripted agent behavior and synthetic Jev answers. It requires the selected scenario's unchanged task. It is useful for learning the timeline, demonstrating review controls, and checking deterministic policy without credentials.

Those answers are not Jev predictions. The scripted normal path is not evidence of the local LLM's behavior. Fixture timings and apparent wins must never be mixed into live model measurements. Keep the `source` label visible in reports and screenshots.

All support tools operate on simulated data in both execution modes. **Live** means actual model inference, not real refunds or external business actions.

## Publishing a result

Report the scenario set and labels, run count, execution mode, model identities, local hardware/server settings, generation settings, dependency lock revision, thresholds, path order, and reviewer behavior. Include failures and per-scenario differences, not just the most favorable example.

Price estimates need the applicable provider pricing and usage, with a date and method. Local inference is not automatically free; leave compute cost unknown when it has not been measured. Neither lower token count nor a hosted vendor speedup claim proves lower end-to-end cost here.

A small teaching set cannot validate broad calibration, reliability, or production readiness. It can support a narrower conclusion such as “on these cases and this setup, the assisted path requested review more often and used fewer worker calls.” Do not fill in a performance conclusion until live runs provide the evidence.
