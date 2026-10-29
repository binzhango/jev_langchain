# Jev as a risk gate on proposed refunds

A normal LangChain agent asks a generative LLM for its next response or tool call. Jev adds a different kind of model: it evaluates supplied state against explicit questions and returns typed predictions. Python uses refund risk scores to require human review. Triage separately adds a selected-playbook prompt hint; it does not enforce a workflow or filter tools. The local LLM still writes responses and proposes tool calls.

The important boundary is:

```text
State + questions → Jev prediction → Python rule → agent action → observed result
```

For example, “this refund seems risky” is a prediction. “Review refunds whose risk score crosses this threshold” is a rule. Pausing a tool call is an action. The refund appearing in the simulated ledger is an observed result. Keeping these separate makes it possible to inspect which part caused a behavior.

## Three question types

| Type | Question it answers | Returned meaning | Example use |
| --- | --- | --- | --- |
| `Choice` | Which supplied option fits? | Selected option, probabilities over options, and confidence | Select a playbook prompt hint |
| `Noul` | Is this statement true? | Probability of yes, from 0 to 1 | Determine whether the message expresses urgency |
| `Score` | Where does this fall on an ordered rubric? | Score, rubric/legend, probabilities, and confidence | Assess proposed-action risk |

The question definitions matter as much as the state. Choices should describe distinct workflows and include a useful general or uncertain route. A score needs concrete ordered levels. “Routine, notable, severe” is more interpretable when each level explains what evidence qualifies.

A `Noul` of `0.5` means an even split between yes and no; it does not mean medium urgency. A three-level `Score` can fall between levels: on a 0–2 rubric, `1.4` is a weighted position on that rubric, not a 140% probability. Choice/Score confidence is a separate returned field. Do not substitute it for the selected option's probability or call every number “confidence.”

Multiple questions can share the same state in one Jev request. This avoids constructing a separate conversation for each classification. The full answers remain useful after the application has selected a branch: distributions reveal competing options, and model/request metadata identify what produced them. See the [LangChain TypeSafe integration](https://docs.langchain.com/oss/python/integrations/providers/typesafe) for the invocation and response contract.

## A decision is not an authorization

Consider this **invented teaching example**, not a recorded model response:

```text
Proposed action: refund one verified missing item
Jev risk score: 1.6 on the run's 0–2 rubric
Python review threshold: 1.5
Applied rule: 1.6 >= 1.5 → request human review
Final policy: validate the approved or edited arguments before executing
```

The threshold is an application choice. Jev does not set the refund ceiling, establish ownership, or grant permission. Hard rules about valid amounts, ownership, and duplicate refunds apply in both paths. Human approval cannot override those rules either.

An unavailable or unusable risk assessment must be visible as an error or a review condition. Treating missing evidence as a low risk score would hide a different decision inside error handling.

Read [decisions.py](../src/jev_harness/decisions.py) for the question definitions and playbook prompt-selection rule, and [domain.py](../src/jev_harness/domain.py) for deterministic refund policy and simulated effects. A returned field influences behavior only where code actually consumes it; displaying an urgency or frustration score alone does not make it a control rule.

## What the two paths share

Both paths already receive every playbook and the same three tools. The selected category adds one prompt line on the Jev path; the LLM can still propose any tool. Urgency, frustration, and triage `needs_review` are displayed but do not trigger control rules. Only the separate proposed-refund risk score adds an enforced review condition. Existing amount limits and agent-requested review apply on both paths, so a review is not necessarily caused by Jev.

| Normal agent | Jev-assisted agent |
| --- | --- |
| The local LLM chooses its next action using the task, tools, and support instructions | Jev scores proposed refunds; Python requires review at the risk threshold. Triage adds a prompt hint |
| The local LLM writes responses and tool arguments | The same local LLM writes responses and tool arguments |
| Shared deterministic policy and review mechanism | Shared deterministic policy and review mechanism |
| Observable tool proposals, outcomes, and responses | The same observations, plus Jev inputs, questions, and typed answers |

There is no additional local classifier model. The normal agent can make a decision within the generation that proposes a tool call; do not assume Jev replaces a separate baseline call. Jev can add latency. Whether additional review prevents an unsupported refund or unnecessarily delays a justified one requires live evaluation.

The dashboard starts both paths from the same task snapshot with independent mutable data. After their actions diverge, their histories may differ. A later disagreement is then a difference between realized trajectories, not necessarily a prediction on identical evidence.

## Reading the dashboard

Enter a task once and select **Run both**. Read the shared starting context first, then compare the action timelines. Open a Jev event to inspect its exact state, question, answer, and duration. Read the prompt-guidance event as advisory; follow the risk and policy events to see the enforced review rule, then the tool result to see what actually happened.

The normal path shows observable actions, not invented probabilities or private reasoning. A stored `workflow` event records prompt selection, not enforced routing or Jev's chain of thought. The first divergence helps locate where behavior began to differ; it does not establish which path was correct.

Changing a threshold in the explorer recomputes a hypothetical branch from a saved score. It does not execute an action or show what the LLM would have said afterward. Export the comparison JSON to retain the actual histories and metadata; see the [API contract](api-contract.md).

## Confidence and evidence

TypeSafe describes Jev's probabilities as calibrated. Calibration is a property measured across many predictions: among cases assigned a probability near 0.8, the event should occur roughly 80% of the time. One confident answer cannot demonstrate calibration, and a small support demo cannot validate a broad vendor claim. Typed output guarantees also do not establish that a classification is semantically correct.

Use this repo to examine concrete behavior and reproduce measurements on your setup. The [evaluation guide](evaluation.md) explains which conclusions the comparison can support.
