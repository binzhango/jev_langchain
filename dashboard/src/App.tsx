import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, BookOpen, Check, ChevronDown, ChevronRight, CircleHelp, Code2, Columns2, Database, GitBranch, History, Info, Layers3, LoaderCircle, Plus, Radio, RotateCcw, Server, ShieldCheck, SlidersHorizontal, Terminal, X } from 'lucide-react';
import { api } from './api';
import RunPanel, { StatusBadge, type ReviewHandler } from './RunPanel';
import type { Comparison, Config, Execution, Scenario } from './types';

const activeStatuses = new Set(['queued', 'running', 'awaiting_review']);
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.';

function shortDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [history, setHistory] = useState<Comparison[]>([]);
  const [scenarioId, setScenarioId] = useState('');
  const [task, setTask] = useState('');
  const [execution, setExecution] = useState<Execution>('live');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(() => window.location.hash.slice(1) || null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [reload, setReload] = useState(0);
  const [showGuide, setShowGuide] = useState(false);
  const [mobileHistory, setMobileHistory] = useState(false);
  const activeIdRef = useRef(selectedId);
  activeIdRef.current = selectedId;

  const updateHistory = useCallback((value: Comparison) => {
    setHistory(previous => [value, ...previous.filter(item => item.id !== value.id)].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 50));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    Promise.all([
      api<Config>('/config', { signal: controller.signal }),
      api<Scenario[]>('/scenarios', { signal: controller.signal }),
      api<Comparison[]>('/comparisons', { signal: controller.signal }),
    ]).then(([nextConfig, nextScenarios, nextHistory]) => {
      if (controller.signal.aborted) return;
      setConfig(nextConfig); setScenarios(nextScenarios); setHistory(nextHistory);
      setScenarioId(previous => previous || nextScenarios[0]?.id || '');
      setTask(previous => previous || nextScenarios[0]?.task || '');
    }).catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setPollError('');
    async function poll() {
      try {
        const next = await api<Comparison>(`/comparisons/${encodeURIComponent(selectedId!)}`, { signal: controller.signal });
        if (controller.signal.aborted || activeIdRef.current !== selectedId) return;
        setComparison(next); updateHistory(next); setPollError('');
        if (activeStatuses.has(next.status)) timer = setTimeout(() => void poll(), next.status === 'awaiting_review' ? 1500 : 800);
      } catch (error) {
        if (controller.signal.aborted) return;
        setPollError(`Live updates interrupted. ${errorMessage(error)}`);
        timer = setTimeout(() => void poll(), 3500);
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [selectedId, updateHistory]);

  const selectedScenario = scenarios.find(scenario => scenario.id === scenarioId);
  const busy = comparison ? activeStatuses.has(comparison.status) : false;
  const mismatch = execution === 'fixture' && task !== selectedScenario?.task;

  function selectScenario(id: string) {
    setScenarioId(id);
    setTask(scenarios.find(scenario => scenario.id === id)?.task ?? '');
    setError('');
  }

  function openComparison(value: Comparison) {
    setComparison(value); setSelectedId(value.id); setScenarioId(value.scenario_id);
    setTask(value.task); setExecution(value.source); setMobileHistory(false);
    window.history.replaceState(null, '', `#${encodeURIComponent(value.id)}`);
  }

  function newComparison() {
    setSelectedId(null); setComparison(null); setPollError(''); setError(''); setMobileHistory(false);
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
    document.getElementById('task')?.focus();
  }

  async function startComparison() {
    if (!task.trim() || !scenarioId) return;
    if (mismatch) { setError('Scripted walkthroughs use the selected scenario’s exact task. Restore its task or choose live models.'); return; }
    setCreating(true); setError('');
    try {
      const value = await api<Comparison>('/comparisons', { method: 'POST', body: JSON.stringify({ scenario_id: scenarioId, task, execution }) });
      setComparison(value); setSelectedId(value.id); updateHistory(value);
      window.history.replaceState(null, '', `#${encodeURIComponent(value.id)}`);
    } catch (error) { setError(errorMessage(error)); }
    finally { setCreating(false); }
  }

  const onReview: ReviewHandler = async (path, review, decision, args) => {
    if (!comparison) throw new Error('No comparison selected.');
    const currentId = comparison.id;
    const value = await api<Comparison>(`/comparisons/${encodeURIComponent(currentId)}/review`, {
      method: 'POST', body: JSON.stringify({ path, review_id: review.id, decision, ...(args ? { args } : {}) }),
    });
    updateHistory(value);
    if (activeIdRef.current === currentId) setComparison(value);
  };

  const resultSource = comparison?.source ?? execution;
  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#" onClick={event => { event.preventDefault(); newComparison(); }} aria-label="Jev Decision lab home"><span className="brand-mark">j<span>·</span></span><strong>jev</strong><span className="brand-divider" /><span className="brand-subtitle">Decision lab</span></a>
      <div className="topbar-actions"><span className="environment-label"><Server size={14} />Local workspace</span><button className="icon-button mobile-history-button" aria-label="Show saved comparisons" onClick={() => setMobileHistory(!mobileHistory)}><History size={18} /></button><button className="button guide-button" onClick={() => setShowGuide(!showGuide)}><BookOpen size={15} />How it works</button></div>
    </header>

    <div className="workspace">
      <aside className={`sidebar ${mobileHistory ? 'sidebar-open' : ''}`} aria-label="Saved comparisons">
        <div className="sidebar-top"><span className="sidebar-label">WORKSPACE</span><button className="icon-button" onClick={newComparison} aria-label="Start a new comparison"><Plus size={17} /></button></div>
        <button className={`workspace-item ${!comparison ? 'workspace-item-active' : ''}`} onClick={newComparison}><Columns2 size={17} />New comparison<ChevronRight size={14} /></button>
        <a className="workspace-item" href="/benchmark/report.html"><Activity size={17} />Decision benchmark<ChevronRight size={14} /></a>
        <div className="saved-heading"><span>Saved comparisons</span><span>{history.length}</span></div>
        <div className="history-list">
          {history.length === 0 ? <div className="no-history"><History size={19} /><p>Your comparisons will be saved here.</p></div> : history.map(item => <button key={item.id} className={`history-item ${item.id === selectedId ? 'history-item-active' : ''}`} onClick={() => openComparison(item)}><span className="history-title">{item.task}</span><span className="history-meta"><span>{shortDate(item.created_at)}</span><span className={`source-dot source-${item.source}`} />{item.source === 'fixture' ? 'Scripted' : 'Live'}</span><span className="history-status">{item.status.replaceAll('_', ' ')}</span></button>)}
        </div>
        <div className="sidebar-footer"><GitBranch size={18} /><p>Same task.<br />Different decisions.</p><span>LangChain + Jev</span></div>
      </aside>

      <main>
        <div className="page-heading"><div><div className="breadcrumb"><span>Workspace</span><ChevronRight size={12} /><span>Compare agents</span></div><h1>One task. Two paths.</h1><p>See what changes when Jev helps an agent decide.</p></div><span className="experiment-tag"><Layers3 size={14} />Controlled comparison</span></div>

        {showGuide && <section className="guide-panel"><button className="icon-button close-guide" onClick={() => setShowGuide(false)} aria-label="Close guide"><X size={16} /></button><h2>A prediction becomes an action</h2><div className="guide-flow"><span>Shared task</span><ArrowRight size={14} /><span>Agent decisions</span><ArrowRight size={14} /><span>Policy & tools</span><ArrowRight size={14} /><span>Observable outcome</span></div><div className="guide-columns"><p><strong>Normal agent</strong> Your local LLM chooses tools, requests help, and writes the response. Hard policy still applies.</p><p><strong>Jev-assisted agent</strong> Jev predicts workflow and risk. Python rules use those answers to guide the same local LLM.</p><p><strong>Read the evidence</strong> Expand a trace event to inspect its inputs and outputs. A probability is a prediction, not proof that an action is correct.</p></div></section>}

        {error && <div className="error-banner" role="alert"><Info size={18} /><span>{error}</span><button className="text-button" onClick={() => setReload(value => value + 1)}>Retry connection</button></div>}

        <section className="task-panel" aria-labelledby="task-heading">
          <div className="task-panel-heading"><div className="section-title"><span className="section-icon"><Terminal size={17} /></span><h2 id="task-heading">The shared task</h2></div><span className="shared-label"><Check size={13} />Identical starting context</span></div>
          <div className="task-controls">
            <div className="field scenario-field"><label htmlFor="scenario">Scenario</label><div className="select-wrap"><select id="scenario" value={scenarioId} disabled={loading || scenarios.length === 0} onChange={event => selectScenario(event.target.value)}>{scenarios.length === 0 && <option>Loading scenarios…</option>}{scenarios.map(scenario => <option value={scenario.id} key={scenario.id}>{scenario.title}</option>)}</select><ChevronDown size={14} /></div></div>
            <div className="field execution-field"><label htmlFor="execution">Execution</label><div className="select-wrap"><select id="execution" value={execution} onChange={event => { setExecution(event.target.value as Execution); setError(''); }}><option value="live">Live models</option><option value="fixture">Scripted walkthrough</option></select><ChevronDown size={14} /></div></div>
          </div>
          <label className="sr-only" htmlFor="task">Task sent to both agents</label>
          <textarea id="task" className="task-input" value={task} onChange={event => setTask(event.target.value)} disabled={loading} placeholder="Enter one task for both agents…" rows={3} />
          <div className="task-context-row"><p>{selectedScenario?.description ?? 'Select a scenario to load a shared starting context.'}</p><button className="text-button restore-task" disabled={!selectedScenario || task === selectedScenario.task} onClick={() => setTask(selectedScenario?.task ?? '')}><RotateCcw size={12} />Restore task</button></div>
          {selectedScenario && <details className="fixture-details"><summary><Database size={13} />Starting data <span>{selectedScenario.fixture.order?.id ?? selectedScenario.fixture.customer_id ?? 'Scenario fixture'}</span><ChevronDown size={12} /></summary><div className="fixture-content"><div className="fixture-note">Both paths get independent copies. Changes in one cannot affect the other.</div><pre>{JSON.stringify(selectedScenario.fixture, null, 2)}</pre><details className="expected-details"><summary>Expected scenario behavior</summary><pre>{JSON.stringify(selectedScenario.expected, null, 2)}</pre></details></div></details>}
          {execution === 'fixture' && <div className="mode-notice"><Info size={14} /><span>Scripted agent responses and synthetic Jev predictions. No models are called; this is a walkthrough, not a benchmark.</span></div>}
          {mismatch && <p className="inline-error">Restore the scenario task to use its scripted walkthrough, or select live models for a custom task.</p>}
          {execution === 'live' && config && !config.jev_configured && <div className="mode-notice mode-warning"><Info size={14} /><span>Jev credentials are not configured in the server. Export <code>JEV_TOKEN</code> and restart it, or choose a scripted walkthrough.</span></div>}
          <div className="task-footer"><div className="provider-status"><span className="provider-chip" title={config?.base_url}><Server size={13} /><span>{config?.model ?? 'Connecting to server'}</span></span><span className={`provider-chip ${config?.jev_configured ? 'provider-ready' : ''}`} title={config?.jev_configured ? 'Credential configured; live calls verify connectivity.' : 'JEV_TOKEN not configured'}><span className="connection-dot" />Jev {config?.jev_configured ? 'configured' : 'not configured'}</span></div><button className="button primary-button" disabled={loading || creating || !task.trim() || !scenarioId || mismatch || busy || (execution === 'live' && !config?.jev_configured)} onClick={() => void startComparison()}>{creating ? <LoaderCircle size={16} className="spin" /> : <Columns2 size={16} />}{creating ? 'Starting comparison…' : busy ? 'Comparison in progress' : 'Run both paths'}{!creating && !busy && <ArrowRight size={15} />}</button></div>
        </section>

        <div className="comparison-section-heading"><div><h2>Compare the decisions</h2><p>{comparison ? 'Inspect the actual actions each path took.' : 'Two independent runs. One shared starting point.'}</p></div>{comparison && <a className="button export-button" href={`/api/comparisons/${encodeURIComponent(comparison.id)}/export`} download><ArrowDownToLine size={14} />Export trace</a>}</div>

        {comparison && <section className="comparison-meta"><div className="comparison-meta-top"><span className={`execution-badge execution-${comparison.source}`}><Radio size={12} />{comparison.source === 'fixture' ? 'SCRIPTED WALKTHROUGH' : 'LIVE COMPARISON'}</span><StatusBadge status={comparison.status} /><span className="run-timestamp">{shortDate(comparison.created_at)}</span></div><p className="recorded-task">{comparison.task}</p><div className="snapshot-row"><code title={comparison.input_hash}>Shared input · {comparison.input_hash.slice(0, 12)}</code><details><summary><Code2 size={12} />Inspect snapshot</summary><pre>{JSON.stringify(comparison.snapshot, null, 2)}</pre></details></div>{comparison.source === 'fixture' && <p className="fixture-result-note">These are scripted examples, not measured model decisions. Timing is excluded from comparisons.</p>}</section>}
        {pollError && <div className="error-banner poll-error" role="status"><Activity size={16} /><span>{pollError} Retrying automatically.</span></div>}

        {comparison?.analysis?.first_divergence && <div className="divergence-banner"><GitBranch size={18} /><div><strong>Where the paths diverge</strong><p>{comparison.analysis.first_divergence}</p></div></div>}

        <div className="comparison-grid">
          <RunPanel key={`${comparison?.id ?? 'empty'}-normal`} path="normal" run={comparison?.runs.normal} source={resultSource} model={comparison?.model ?? config?.model} onReview={onReview} />
          <RunPanel key={`${comparison?.id ?? 'empty'}-jev`} path="jev" run={comparison?.runs.jev} source={resultSource} model={comparison?.model ?? config?.model} onReview={onReview} />
        </div>

        {comparison?.analysis?.note && <div className="analysis-note"><Info size={15} /><p>{comparison.analysis.note}</p></div>}
        <footer className="main-footer"><span><ShieldCheck size={13} />Simulated support actions only</span><span><CircleHelp size={13} />Compare outcomes, not just confidence.</span><button className="text-button" onClick={() => { setShowGuide(true); window.scrollTo({ top: 0, behavior: 'smooth' }); }}><SlidersHorizontal size={13} />Understand the experiment</button></footer>
      </main>
    </div>
  </div>;
}
