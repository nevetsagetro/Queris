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
    <section className="ask-grid"><div className="primary-column"><form className="question-card" onSubmit={onSubmit}><label htmlFor="question">What would you like to know?</label><textarea id="question" value={question} onChange={(event) => { setQuestion(event.target.value); clearDemo(); }} placeholder="e.g. Which countries generated the most revenue?" rows={4} /><div className="form-footer"><span className="muted">Read-only · schema-aware · cached on repeat</span><button className="primary-button" disabled={!question.trim() || busy} type="submit">{busy ? "Running…" : "Run analysis"}</button></div></form>{result && <ResultPanel result={result} />}</div><ExamplesPanel examples={examples.slice(0, 12)} total={examples.length} onUse={onUseExample} /></section>
  </>;
}

function ExamplesPanel({ examples, total, onUse }: { examples: Example[]; total: number; onUse: (example: Example) => void }) {
  return <aside className="side-panel"><div className="panel-heading"><div><p className="eyebrow">Question starters</p><h2>Find a useful starting point</h2></div><span className="count-badge">{total}</span></div><div className="example-list">{examples.map((example) => <button className="example-card" key={example.id} onClick={() => onUse(example)}><span className="example-category">{example.category}</span><strong>{example.title}</strong><span>{example.question}</span></button>)}</div><p className="muted">Open Data catalog to browse all {total} reviewed starters.</p></aside>;
}
