# Local dashboard API

All endpoints are relative to the Python server. In development Vite proxies `/api` to port 8000. The built dashboard is served by FastAPI. No browser credentials or external APIs are used.

## Endpoints

- `GET /api/config`: `{model, base_url, jev_model, jev_configured, risk_threshold, auto_refund_limit, hard_refund_limit}`.
- `GET /api/scenarios`: array of `{id, title, description, task, fixture, expected}`. Fixture includes `customer_id` and `order` with `id,status,items:[{name,price,missing}],total`.
- `POST /api/comparisons`: `{scenario_id, task?:string, execution:"live"|"fixture"}`. Live is the default; fixture means a clearly labeled scripted simulation, not model performance. Returns the comparison object immediately.
- `GET /api/comparisons`: array of saved comparison objects, newest first, capped at 50.
- `GET /api/comparisons/{id}`: latest comparison. Poll while queued/running/awaiting_review. Each run continues independently when the other awaits review.
- `POST /api/comparisons/{id}/review`: `{path:"normal"|"jev", review_id:string, decision:"approve"|"edit"|"reject", args?:object}`. Edit supplies complete replacement arguments. Returns latest comparison; errors have a `detail` string. Final policy always checks edited arguments.
- `GET /api/comparisons/{id}/export`: full JSON download.

## Comparison

```typescript
type Comparison = {
 id:string; created_at:string; task:string; scenario_id:string;
 source:'live'|'fixture'; status:'queued'|'running'|'awaiting_review'|'completed'|'error';
 model:string; input_hash:string; snapshot:object;
 runs:{normal:Run; jev:Run};
 analysis:{first_divergence:string|null; agreement:boolean|null; note:string};
};
type Run = {
 path:'normal'|'jev'; status:'queued'|'running'|'awaiting_review'|'completed'|'error';
 events:Event[]; output:string; error:string|null;
 degraded?:boolean; decision_errors?:{kind:string; message:string}[];
 metrics:{llm_calls:number; jev_calls:number; tool_calls:number; input_tokens:number|null;
   output_tokens:number|null; duration_ms:number; jev_ms:number; review_wait_ms:number};
 pending_review:null|{id:string; tool:string; args:Record<string,unknown>; reason:string};
 actions:{tool:string; args:object; result:unknown}[];
 outcome:null|{label:string; passed:boolean|null; checks:{name:string; passed:boolean; detail:string}[]};
};
type Event = {
 id:string; type:string; title:string; timestamp:string; elapsed_ms?:number;
 detail:Record<string,unknown>;
};
```

Common event types: `input`, `jev_triage`, `workflow`, `model`, `tool_proposed`, `jev_risk`, `policy`, `review_requested`, `review_resolved`, `tool_result`, `response`, `error`. Decision details contain `state`, `questions`, `answers` keyed by ID, `usage`, `model`, `request_id`, and `elapsed_ms` where available. `jev_risk` also carries `threshold` and `needs_review`. Answers follow TypeSafe primitives (`type`, `choice`, `probabilities`, `confidence`, `score`, `legend`, `noul` as applicable). A workflow event records the rule applied, not model chain-of-thought.

Fixture mode is for interactive walkthroughs without credentials and must remain visibly labeled on every result. It uses scripted agent responses and synthetic Jev answers. Never present fixture timings or scripted decisions as a live benchmark. Custom task text is supported in live mode; fixture mode requires the selected scenario's unchanged task.

Threshold exploration is frontend-only: recompute `score >= threshold` on a saved Jev risk answer, label it hypothetical, and do not mutate or rerun the comparison.
