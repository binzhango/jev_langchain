# Jev vs the local LLM: decision benchmark

**Exploratory deployment measurements, not proof of a better model.** The first run's 18/18 versus 17/18 usable correct answers differ by one JSON field-name error; both models were correct on all valid responses. The 151 ms versus 11.16 s medians compare hosted Jev with a local 27B generative model on different serving infrastructure, including local reasoning overhead. This is not an equivalent-hardware speed comparison or an end-to-end agent benchmark. Scripted fixtures show mechanics, not model behavior. Keep these qualifications next to any numbers copied into a slide or summary.

There are now two complementary experiments:

- `compare` / `evaluate`: normal LangChain agent versus Jev-assisted agent on the same support task, including tool loops and final responses.
- `benchmark`: Jev versus the **existing local generative LLM**, answering identical decision questions. No extra local model, agent tool execution, or change to the dashboard's two main paths.

```bash
export JEV_TOKEN
uv run jev-lab benchmark --repeat 3 --output artifacts/benchmark
# A shorter smoke test, spanning all three primitives:
uv run jev-lab benchmark --limit 6 --repeat 1 --output artifacts/benchmark-smoke
```

Open **Decision benchmark** in the dashboard sidebar, open `artifacts/benchmark/report.html` directly, read `report.md`, or inspect `report.json`. The dashboard serves the latest saved report; start benchmark runs from the CLI. Restart the dashboard server after installing this change. With a custom data directory, pass `--output "$JEV_LAB_DATA_DIR/benchmark"`. Progress is retained in `progress.json` after each pair. These commands make live inference requests, not scripted calls. Avoid running agent comparisons simultaneously on the same local model server.

## Tasks and fair inputs

The versioned suite in `src/jev_harness/benchmark.py` contains 18 authored examples: six intent Choices, six urgency Nouls, and six refund-risk Scores. JSON reports include the complete cases, labels, dataset hash, model IDs, request settings, order, and per-call results. Review the labels yourself; this is a small teaching suite, not an independently adjudicated or representative industry benchmark.

Both models receive the exact same state and question instructions/criteria. IDs and expected labels are excluded from inference payloads. Jev answers through its typed interface. The local LLM is prompted to return only the required choice/probability/score as JSON, with no explanation or full distribution requirement. This avoids making the LLM generate unnecessary material just to match Jev's richer response format. A malformed response counts as a failure; no repair calls are hidden. Raw output and reported usage are retained even when parsing fails.

The baseline uses ordinary chat completions with prompted JSON. During integration, LM Studio rejected `json_object`; `json_schema` returned empty final content with this model. Those integration runs are excluded from the published result. LM Studio documents [schema-constrained output](https://beta.lmstudio.ai/docs/developer/openai-compat/structured-output), but the benchmark uses the verified working interface for this server/model combination. Local reasoning, if enabled by the server, remains included in latency and reported token usage.

One warmup per provider is recorded separately and excluded by default. `--no-warmup` disables it. Calls run sequentially; order is counterbalanced across cases/repetitions, and case order is shuffled with a reproducible `--seed`. This is a client-observed latency comparison across a LAN/local endpoint and a hosted endpoint, with different hardware, network, tokenization, and caching. Warmup does not eliminate all cache/load effects.

## Metrics

| Metric | Interpretation |
| --- | --- |
| Decision accuracy | Correct decisions divided by all attempts; failed requests count as incorrect |
| Lenient accuracy | Secondary score after bounded, label-independent normalization; strict failures remain recorded |
| First-pass 95% accuracy intervals | Wilson intervals on the first recorded repetition of each unique case; rerunning a case does not increase this sample size |
| Valid decision accuracy | Correct decisions divided by valid responses; interpret alongside failure counts |
| Choice correctness | Exact selected key matches the expected intent |
| Noul correctness / Brier | Probability threshold 0.5 for binary accuracy; squared probability error for valid outputs |
| Score correctness / MAE | Allow vs review at threshold 1.0; mean absolute distance from the expected rubric level for valid outputs |
| False allows | Valid risk answers below 1.0 when the expected level requires review |
| Unnecessary reviews | Valid risk answers at least 1.0 when the expected level is routine |
| p50 / p95 latency | Client-observed time for valid responses, including parsing; all-attempt p50 is also in JSON |
| Failures | Network, timeout, invalid JSON, missing field, or out-of-range answer |
| Usage | Reported input/output tokens with coverage counts; missing usage stays unknown |

Read failure counts alongside accuracy and timing. Failed outputs are not counted as safe or as false allows; they are separately recorded failures. The report's primitive breakdown prevents an aggregate score from hiding one weak task type. Compare individual disagreements before deciding whether Jev helps your use case.

Brier and MAE are conditional on valid responses. A small Brier score does not prove broad calibration. Local LLM probability values are generated estimates, not assumed to have Jev's calibration characteristics. Token counts across different model tokenizers are not equal units of compute, and no monetary savings are inferred.

Start with the default single repetition as an integration check. Use multiple repetitions and expand/review the dataset before treating differences as a performance claim. No provider is assumed to win.

Lenient parsing only strips a complete JSON code fence or unwraps a sole `decision` field, either a scalar or an object containing the expected field. It rejects conflicting/duplicate keys, arbitrary prose, type coercions, and values outside the original rubric. Both providers use the same rule. It never consults the expected label to parse an answer and makes no repair/model call. The rule was introduced after inspecting the historical field-name failure, so the historical lenient result is explicitly a post-hoc sensitivity analysis. Both providers score 18/18 under that rule; the local LLM still has one strict formatting failure.

The [Wilson method](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) supplies binomial accuracy intervals. The report uses one first-pass observation per case rather than treating repeated runs as independent tasks. These authored cases are not a representative random sample: the intervals illustrate finite-sample uncertainty, not generalization or a paired significance test. Latency statistics are descriptive and do not currently have confidence intervals.
