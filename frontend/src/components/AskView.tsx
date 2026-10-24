import { FormEvent } from "react";
import { Example, QueryResult } from "../types";
import { ResultPanel } from "./ResultPanel";

type Props = {
  question: string;
  setQuestion: (value: string) => void;
  clearDemo: () => void;
  onSubmit: (event?: FormEvent) => void;
  busy: boolean;
  examples: Example[];
  onUseExample: (example: Example) => void;
  result: QueryResult | null;
};

export function AskView({ question, setQuestion, clearDemo, onSubmit, busy, examples, onUseExample, result }: Props) {
  return <>
    <section className="intro"><p className="eyebrow">Ask your data</p><h1>Turn a business question into a safe answer.</h1><p className="lede">Explore the catalog first, choose a starter, or ask in your own words. Queris validates every query before read-only execution.</p></section>
    <section className="ask-grid"><div className="primary-column"><form className="question-card" onSubmit={onSubmit}><label htmlFor="question">What would you like to know?</label><textarea id="question" value={question} onChange={(event) => { setQuestion(event.target.value); clearDemo(); }} placeholder="e.g. Which countries generated the most revenue?" rows={4} /><div className="form-footer"><span className="muted">Read-only · schema-aware · cached on repeat</span><button className="primary-button" disabled={!question.trim() || busy} type="submit">{busy ? "Running…" : "Run analysis"}</button></div></form>{(busy || result) && <ExecutionFlow busy={busy} result={result} />}{result && <ResultPanel result={result} />}</div><ExamplesPanel examples={examples.slice(0, 12)} total={examples.length} onUse={onUseExample} /></section>
  </>;
}

function ExecutionFlow({ busy, result }: { busy: boolean; result: QueryResult | null }) {
  const completed = !busy && Boolean(result);
  const steps = [
    ["Catalog", completed || busy ? "Ready" : "Waiting"],
    ["Generate SQL", result?.execution_mode === "cache" ? "Skipped · cache" : completed ? "Complete" : "Running"],
    ["Validate", completed && result ? (result.blocked ? "Blocked" : "Complete") : "Waiting"],
    ["Execute read-only", completed && result ? (result.status === "success" ? "Complete" : "Stopped") : "Waiting"],
    ["Cache", result?.cache_hit ? "Replayed" : completed ? "Saved" : "Waiting"],
  ];
  return <section className="execution-flow" aria-live="polite"><div className="flow-heading"><p className="eyebrow">Execution flow</p><span>{busy ? "Running analysis…" : "Traceable local pipeline"}</span></div><div className="flow-steps">{steps.map(([label, status]) => <div className={`flow-step ${status === "Waiting" ? "waiting" : status === "Blocked" ? "blocked" : "complete"}`} key={label}><i aria-hidden="true" /><span><strong>{label}</strong><small>{status}</small></span></div>)}</div></section>;
}

function ExamplesPanel({ examples, total, onUse }: { examples: Example[]; total: number; onUse: (example: Example) => void }) {
  return <aside className="side-panel"><div className="panel-heading"><div><p className="eyebrow">Question starters</p><h2>Find a useful starting point</h2></div><span className="count-badge">{total}</span></div><div className="example-list">{examples.map((example) => <button className="example-card" key={example.id} onClick={() => onUse(example)}><span className="example-category">{example.category}</span><strong>{example.title}</strong><span>{example.question}</span></button>)}</div><p className="muted">Open Data catalog to browse all {total} dataset starters.</p></aside>;
}
