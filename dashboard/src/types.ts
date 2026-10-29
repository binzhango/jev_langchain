export type Path = 'normal' | 'jev';
export type Status = 'queued' | 'running' | 'awaiting_review' | 'completed' | 'error';
export type Execution = 'live' | 'fixture';
export type JsonObject = Record<string, unknown>;

export interface Config {
  model: string;
  base_url: string;
  jev_model: string;
  jev_configured: boolean;
  risk_threshold: number;
  auto_refund_limit: number;
  hard_refund_limit: number;
}
export interface Scenario {
  id: string;
  title: string;
  description: string;
  task: string;
  fixture: JsonObject & {
    customer_id?: string;
    order?: {
      id: string;
      status: string;
      total: number;
      items: { name: string; price: number; missing?: boolean }[];
    };
  };
  expected: unknown;
}
export interface TraceEvent {
  id: string;
  type: string;
  title: string;
  timestamp: string;
  elapsed_ms?: number;
  detail: JsonObject;
}
export interface Review {
  id: string;
  tool: string;
  args: JsonObject;
  reason: string;
}
export interface Run {
  path: Path;
  degraded?: boolean;
  decision_errors?: { kind: string; message: string }[];
  status: Status;
  events: TraceEvent[];
  output: string;
  error: string | null;
  metrics: {
    llm_calls: number;
    jev_calls: number;
    tool_calls: number;
    input_tokens: number | null;
    output_tokens: number | null;
    duration_ms: number;
    jev_ms: number;
    review_wait_ms: number;
  };
  pending_review: Review | null;
  actions: { tool: string; args: JsonObject; result: unknown }[];
  outcome: null | {
    label: string;
    passed: boolean | null;
    checks: { name: string; passed: boolean; detail: string }[];
  };
}
export interface Comparison {
  id: string;
  created_at: string;
  task: string;
  scenario_id: string;
  source: Execution;
  status: Status;
  model: string;
  input_hash: string;
  snapshot: JsonObject;
  runs: { normal: Run; jev: Run };
  analysis: {
    first_divergence: string | null;
    agreement: boolean | null;
    note: string;
  };
}
