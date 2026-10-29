import { useState } from 'react';
import { ArrowRight, SlidersHorizontal } from 'lucide-react';
import type { JsonObject, TraceEvent } from './types';

function record(value: unknown): JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonObject : {};
}
function printable(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
}

export default function DecisionDetail({ event }: { event: TraceEvent }) {
  const answers = record(event.detail.answers);
  const questions = record(event.detail.questions);
  const savedThreshold = typeof event.detail.threshold === 'number' ? event.detail.threshold : 1.5;
  const [threshold, setThreshold] = useState(savedThreshold);
  const riskAnswer = record(answers.risk);
  const risk = typeof riskAnswer.score === 'number' ? riskAnswer.score : null;
  return (
    <div className="decision-detail">
      {event.type === 'jev_triage' && <p className="question">Category selects one extra playbook prompt line. It does not filter tools or enforce routing. Urgency and frustration are displayed signals; the separate refund risk score drives the additional review gate.</p>}
      {Object.entries(answers).map(([id, value]) => {
        const answer = record(value);
        const question = record(questions[id]);
        const probabilities = record(answer.probabilities);
        return (
          <section className="answer" key={id}>
            <div className="answer-heading">
              <span>{id.replaceAll('_', ' ')}</span>
              <span className="primitive">{String(answer.type ?? 'decision')}</span>
            </div>
            {question.instructions != null && <p className="question">{printable(question.instructions)}</p>}
            <div className="answer-value">
              {answer.type === 'choice' && <strong>{String(answer.choice).replaceAll('_', ' ')}</strong>}
              {answer.type === 'noul' && typeof answer.noul === 'number' && <><strong>{(answer.noul * 100).toFixed(1)}%</strong><span>probability of yes</span></>}
              {answer.type === 'score' && typeof answer.score === 'number' && <><strong>{answer.score.toFixed(2)}</strong><span>expected rubric score</span></>}
              {typeof answer.confidence === 'number' && <span className="confidence">{(answer.confidence * 100).toFixed(0)}% confidence</span>}
            </div>
            {Object.keys(probabilities).length > 0 && <div className="probabilities">
              {Object.entries(probabilities).map(([name, probability]) => typeof probability === 'number' && <div className="probability" key={name}>
                <span title={name}>{name.replaceAll('_', ' ')}</span>
                <div className="probability-track"><div style={{ width: `${Math.max(0, Math.min(100, probability * 100))}%` }} /></div>
                <span>{(probability * 100).toFixed(1)}%</span>
              </div>)}
            </div>}
            {(answer.legend != null || question.criteria != null) && <details className="rubric-details">
              <summary>View criteria</summary>
              <pre>{printable(answer.legend ?? question.criteria)}</pre>
            </details>}
          </section>
        );
      })}
      {event.type === 'jev_risk' && risk !== null && <section className="threshold-explorer">
        <div className="small-heading"><SlidersHorizontal size={14} /> Explore the review threshold</div>
        <p>This changes the displayed rule only. The saved run is unchanged.</p>
        <div className="threshold-rule"><code>{risk.toFixed(2)} ≥ {threshold.toFixed(2)}</code><ArrowRight size={14} /><strong>{risk >= threshold ? 'Request review' : 'Pass semantic gate'}</strong></div>
        <label htmlFor={`threshold-${event.id}`}>Hypothetical threshold <span>{threshold.toFixed(2)}</span></label>
        <input id={`threshold-${event.id}`} type="range" min="0" max="2" step="0.05" value={threshold} onChange={e => setThreshold(Number(e.target.value))} />
        <div className="range-labels"><span>0 · routine</span><span>2 · severe</span></div>
        <button className="text-button" onClick={() => setThreshold(savedThreshold)}>Restore saved threshold ({savedThreshold.toFixed(2)})</button>
      </section>}
    </div>
  );
}
