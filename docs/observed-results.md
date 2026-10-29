# First observed live comparisons

These are two integration examples from October 28, 2026, using the same `qwen3.8-27b-mlx` worker in LM Studio and hosted `jev-1.14.0`. Each scenario ran once, normal first, with independent fixture data. They are not a statistical benchmark. Both use real model inference and simulated support operations.

| Task | Normal agent | Jev-assisted agent | Observed actions |
| --- | --- | --- | --- |
| Confirmed missing $9 item | 26.30 s active time; 3 LLM calls | 29.41 s active time; 3 LLM + 2 Jev calls | Both looked up the order and issued one $9 refund |
| Confirmed missing $40 dinner | 24.30 s active time; 3 LLM calls | 23.17 s active time; 3 LLM + 2 Jev calls | Both paused for approval, then issued one $40 refund |

Jev request time totaled approximately 450 ms and 405 ms respectively. Active time excludes queueing and review waiting. A test driver approved the simulated $40 refunds on both paths using the same policy. Model loading/caching and response length can influence the differences; the order was not counterbalanced in these two smoke tests. Use the repeat evaluator to investigate performance.

## Action checks are not answer-quality checks

Both scenarios passed their observable action checks. In the $9 case, the normal agent nevertheless said the refund was “pending approval” after the tool had already reported success. Its output is retained in the recording. The Jev-assisted response correctly reported execution but also mentioned a payment-processing timeline that the fixture does not specify. Neither fluent prose nor a passing action check proves every statement is grounded.

This is why the dashboard separates actual tool effects, final response text, and action checks. It does not automatically declare one model better from these two runs.

## Inspect the evidence

- [Full $9 comparison](recordings/missing-item-live.json)
- [Full $40 comparison and approval/resume](recordings/large-refund-live.json)

The recordings preserve task snapshots, model identities, raw Jev state/questions/answers, observed tools, usage, and timing. Internal replay caches were omitted. These integration recordings were made before resume-configuration fingerprinting was added; they are evidence for inspection, not imported resumable checkpoints.

The [evaluation guide](evaluation.md) explains the comparison's scope and limitations. The dashboard's separate scripted walkthroughs are not these live recordings and must not be used as performance evidence.

## First decision-only benchmark

On October 29, 2026, the 18-case teaching suite ran once against the same local Qwen model and hosted Jev, using one excluded warmup per provider, shuffled case order, and counterbalanced sequential requests. This isolates decision calls from agent tool execution. See [methodology](decision-benchmark.md) and the [complete recording](recordings/decision-benchmark-live.json).

| Metric | Local Qwen LLM | Hosted Jev |
| --- | --- | --- |
| Valid and correct / all attempts | 17 / 18 | 18 / 18 |
| Correct among valid responses | 17 / 17 | 18 / 18 |
| Correct after lenient parsing (post-hoc) | 18 / 18 | 18 / 18 |
| Strict accuracy, 95% Wilson interval | 74.2%–99.0% | 82.4%–100% |
| Lenient accuracy, 95% Wilson interval | 82.4%–100% | 82.4%–100% |
| Formatting failures | 1 | 0 |
| Median valid-response latency | 11.158 s | 0.151 s |
| p95 valid-response latency | 45.328 s | 0.219 s |
| Median latency including failures | 12.414 s | 0.151 s |
| Noul Brier, valid responses | 0.000 | 0.001 |
| Risk score MAE, valid responses | 0.000 | 0.132 |
| Reported output tokens, including invalid output | 5,275 | 499 |

These are **18 authored cases in one run**, not proof of superiority. The one-item difference is a JSON field-name failure. The latency columns compare **hosted Jev with a local 27B generative model**, not equivalent hardware, serving stacks, or decoding behavior; they cannot establish intrinsic model speed or end-to-end agent improvement. Scripted fixtures demonstrate the review machinery only and are excluded from these measurements.

The LLM returned `{"decision": 1.0}` instead of the requested `{"noul": 1.0}` for `urgency-3`. This is an output-contract failure, not evidence of a wrong urgency judgment. No repair or retry was applied. Both providers made every valid discrete decision correctly, with no false allows or unnecessary reviews on the six risk cases. The LLM matched the authored numeric labels exactly on valid outputs; Jev's soft scores differed slightly while producing the same threshold decisions.

This run observed lower request latency for hosted Jev and one fewer invalid output. That is deployment-specific evidence, not an established general reliability or speed advantage. It does **not** establish better semantic decision quality, broad calibration, or improved full-agent task outcomes. The local model's reported output includes reasoning tokens; hardware, networking, tokenizers, and decoding interfaces differ. Earlier incompatible JSON-mode/schema-mode probes are excluded; the published run uses ordinary prompted JSON throughout.

The lenient columns are a post-hoc sensitivity analysis using the documented parser, not a new inference run. Original recordings remain unchanged. Wilson intervals use the 18 first-pass cases and do not make this authored suite representative of a population.
