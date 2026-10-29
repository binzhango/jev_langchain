import { useState } from 'react';
import { AlertCircle, ArrowUpRight, Bot, Check, CheckCircle2, ChevronDown, Circle, Clock3, Code2, GitBranch, Hand, LoaderCircle, MessageSquare, ShieldCheck, Sparkles, Wrench, X } from 'lucide-react';
import DecisionDetail from './DecisionDetail';
import type { Execution, JsonObject, Path, Review, Run, Status, TraceEvent } from './types';

function duration(ms: number): string {
  if (!Number.isFinite(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}

const statusLabel: Record<Status, string> = {
  queued: 'Queued', running: 'Running', awaiting_review: 'Needs review', completed: 'Complete', error: 'Failed',
};
export function StatusBadge({ status }: { status: Status }) {
  const Icon = status === 'running' ? LoaderCircle : status === 'completed' ? CheckCircle2 : status === 'awaiting_review' ? Hand : status === 'error' ? AlertCircle : Circle;
  return <span className={`status status-${status}`}><Icon size={12} className={status === 'running' ? 'spin' : undefined} />{statusLabel[status] ?? status}</span>;
}

const eventIcons: Record<string, typeof Circle> = {
  input: MessageSquare, jev_triage: Sparkles, workflow: GitBranch, model: Bot, model_result: Bot, tool_proposed: Wrench,
  jev_risk: ShieldCheck, policy: ShieldCheck, review_requested: Hand, review_resolved: Check,
  tool_result: Code2, response: MessageSquare, error: AlertCircle,
};

function EventRow({ event, source }: { event: TraceEvent; source: Execution }) {
  const Icon = eventIcons[event.type] ?? Circle;
  const decision = event.type === 'jev_triage' || event.type === 'jev_risk';
  return <li className={`event-row ${decision ? 'event-decision' : ''} ${event.type === 'error' ? 'event-error' : ''}`}>
    <span className="event-node"><Icon size={14} /></span>
    <details className="event-disclosure">
      <summary>
        <span className="event-summary"><span className="event-kind">{event.type === 'workflow' ? 'prompt guidance' : event.type.replaceAll('_', ' ')}{decision && <span className="jev-mark">Jev</span>}</span><span className="event-title">{event.type === 'workflow' ? 'Selected playbook hint (advisory)' : event.title}</span></span>
        {source === 'live' && typeof event.elapsed_ms === 'number' && <span className="event-time">{duration(event.elapsed_ms)}</span>}
        <ChevronDown size={14} className="event-chevron" />
      </summary>
      <div className="event-body">
        {event.type === 'workflow' && <p>Advisory prompt selection only. Both agents retain all playbooks and tools; no workflow-specific execution restriction is applied.</p>}
        {decision && <DecisionDetail event={event} />}
        <details className="raw-details" open={!decision}>
          <summary><Code2 size={13} />{decision ? 'Raw state, questions & response' : 'Event details'}</summary>
          <pre>{JSON.stringify(event.detail, null, 2)}</pre>
        </details>
      </div>
    </details>
  </li>;
}

export type ReviewHandler = (path: Path, review: Review, decision: 'approve' | 'edit' | 'reject', args?: JsonObject) => Promise<void>;

function ApprovalPanel({ path, review, onReview }: { path: Path; review: Review; onReview: ReviewHandler }) {
  const [editing, setEditing] = useState(false);
  const [args, setArgs] = useState(JSON.stringify(review.args, null, 2));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(decision: 'approve' | 'edit' | 'reject') {
    setError('');
    let replacement: JsonObject | undefined;
    if (decision === 'edit') {
      try {
        const parsed: unknown = JSON.parse(args);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error();
        replacement = parsed as JsonObject;
      } catch {
        setError('Arguments must be a valid JSON object.');
        return;
      }
    }
    setBusy(true);
    try { await onReview(path, review, decision, replacement); }
    catch (error) { setError(error instanceof Error ? error.message : 'Could not submit review.'); }
    finally { setBusy(false); }
  }
  return <section className="approval-panel" aria-label="Human review">
    <div className="approval-heading"><Hand size={16} /><strong>Your review is needed</strong></div>
    <p>{review.reason}</p>
    <code className="tool-label">{review.tool}</code>
    {editing ? <><label htmlFor={`args-${path}`}>Complete replacement arguments</label><textarea id={`args-${path}`} className="json-editor" rows={7} value={args} onChange={e => setArgs(e.target.value)} spellCheck={false} /></> : <pre>{JSON.stringify(review.args, null, 2)}</pre>}
    <p className="policy-note">Edited arguments are checked against the same hard policy before execution.</p>
    {error && <p className="inline-error" role="alert">{error}</p>}
    <div className="approval-actions">
      <button className="button review-approve" disabled={busy} onClick={() => void submit(editing ? 'edit' : 'approve')}>{busy ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />}{editing ? 'Approve edits' : 'Approve'}</button>
      <button className="button" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? 'Cancel edit' : 'Edit'}</button>
      <button className="button review-reject" disabled={busy} onClick={() => void submit('reject')}><X size={14} />Reject</button>
    </div>
  </section>;
}

export default function RunPanel({ path, run, source, model, onReview }: { path: Path; run?: Run; source: Execution; model?: string; onReview: ReviewHandler }) {
  const isJev = path === 'jev';
  const events = run?.events ?? [];
  const [onlyDecisions, setOnlyDecisions] = useState(false);
  const selectedEvents = onlyDecisions ? events.filter(event => ['jev_triage', 'workflow', 'jev_risk', 'policy', 'review_requested', 'review_resolved', 'tool_proposed', 'tool_result', 'error'].includes(event.type)) : events;
  const metrics = run?.metrics;
  return <section className={`run-panel ${isJev ? 'run-jev' : 'run-normal'}`} aria-label={isJev ? 'Jev-assisted agent' : 'Normal agent'}>
    <header className="run-header">
      <div className="run-identity"><span className="run-icon">{isJev ? <GitBranch size={21} /> : <Bot size={21} />}</span><div><div className="path-label">PATH {isJev ? 'B' : 'A'}</div><h2>{isJev ? 'Jev-assisted agent' : 'Normal agent'}</h2></div></div>
      {run ? <StatusBadge status={run.status} /> : <span className="ready-label">Ready</span>}
    </header>
    <div className="run-description">
      <p>{isJev ? 'Jev scores refunds. Python can require human review.' : 'The local LLM chooses its next action.'}</p>
      <div className="model-label" title={model}><Bot size={12} /><span>{model || 'Your local LLM'}</span>{isJev && <><span className="model-plus">+</span><span className="model-jev">Jev</span></>}</div>
    </div>
    <div className="metrics-grid">
      <div><span>Run time</span><strong>{source === 'fixture' ? 'Scripted' : run && metrics ? duration(metrics.duration_ms) : '—'}</strong></div>
      <div><span>LLM calls</span><strong>{metrics?.llm_calls ?? '—'}</strong></div>
      <div><span>Tool calls</span><strong>{metrics?.tool_calls ?? '—'}</strong></div>
      <div><span>Jev calls</span><strong>{metrics?.jev_calls ?? '—'}</strong></div>
    </div>
    {run && metrics && <details className="usage-details"><summary>Usage & timing <ChevronDown size={12} /></summary><dl><div><dt>Input tokens</dt><dd>{metrics.input_tokens == null ? 'Not reported' : metrics.input_tokens.toLocaleString()}</dd></div><div><dt>Output tokens</dt><dd>{metrics.output_tokens == null ? 'Not reported' : metrics.output_tokens.toLocaleString()}</dd></div><div><dt>Jev time</dt><dd>{source === 'fixture' ? 'Not measured' : duration(metrics.jev_ms)}</dd></div><div><dt>Human waiting</dt><dd>{source === 'fixture' ? 'Not benchmark data' : duration(metrics.review_wait_ms)}</dd></div></dl></details>}
    <div className="timeline-heading"><h3>Decision trace <span>{events.length}</span></h3>{events.length > 0 && <label className="trace-filter"><input type="checkbox" checked={onlyDecisions} onChange={e => setOnlyDecisions(e.target.checked)} />Actions & decisions</label>}</div>
    {events.length > 0 ? <ol className="timeline">{selectedEvents.map(event => <EventRow key={event.id} event={event} source={source} />)}</ol> : <div className="empty-trace"><div className="empty-route"><span /><span /><span /></div><strong>{run?.status === 'queued' ? 'Waiting for this path' : 'The path will appear here'}</strong><p>{run?.status === 'queued' ? 'Paths run sequentially to avoid competing for the local model.' : isJev ? 'Inspect Jev’s predictions, the rules they trigger, and the agent’s actions.' : 'See the agent’s tool choices, policy results, and final response.'}</p></div>}
    {run?.status === 'awaiting_review' && run.pending_review && <ApprovalPanel key={run.pending_review.id} path={path} review={run.pending_review} onReview={onReview} />}
    {run?.degraded && <div className="run-error degraded-warning" role="status"><AlertCircle size={16} /><div><strong>Jev was unavailable during this run</strong><p>Excluded from decision-quality comparison. The agent used the documented fallback behavior.</p>{run.decision_errors?.map((error, index) => <p key={index}>{error.kind}: {error.message}</p>)}</div></div>}
    {run?.error && <div className="run-error" role="alert"><AlertCircle size={16} /><div><strong>This path could not finish</strong><p>{run.error}</p></div></div>}
    {run?.output && <section className="final-response"><div className="small-heading"><ArrowUpRight size={15} />Final response</div><p>{run.output}</p></section>}
    {run?.outcome && <section className={`outcome outcome-${run.outcome.passed === null || run.degraded ? 'unscored' : run.outcome.passed ? 'pass' : 'fail'}`}><div className="outcome-heading">{run.outcome.passed === null || run.degraded ? <Circle size={15} /> : run.outcome.passed ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}<strong>{run.degraded ? 'Excluded from decision-quality scoring' : run.outcome.passed === null ? 'Task not automatically scored' : run.outcome.passed ? 'Action checks passed' : 'Action checks did not pass'}</strong></div><p className="outcome-label">{run.outcome.label}</p><p className="outcome-label">These checks cover tool actions. Inspect the final response separately.</p>{run.outcome.checks?.length > 0 && <details><summary>View action checks</summary><ul>{run.outcome.checks.map((check, index) => <li key={index}>{check.passed ? <Check size={13} /> : <X size={13} />}<div><strong>{check.name}</strong><p>{check.detail}</p></div></li>)}</ul></details>}</section>}
    {run?.status === 'running' && <div className="working-state" role="status"><LoaderCircle size={14} className="spin" />{isJev ? 'Following the Jev-assisted path…' : 'The local agent is working…'}</div>}
    {run?.status === 'awaiting_review' && !run.pending_review && <div className="working-state"><Clock3 size={14} />Waiting for review details…</div>}
  </section>;
}
