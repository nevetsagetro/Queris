import { DemoHistoryItem, Example, QueryResult } from "../types";

type Props = {
  history: QueryResult[];
  demoHistory: DemoHistoryItem[];
  onSelect: (result: QueryResult) => void;
  onRunExample: (example: Example) => void;
};

export function HistoryView({ history, demoHistory, onSelect, onRunExample }: Props) {
  return <section><div className="page-heading"><div><p className="eyebrow">Persistent workspace</p><h1>History</h1><p className="lede">Demo starters make the product reviewable; real analyses stay available after a reload.</p></div><span className="catalog-stat">{demoHistory.length + history.length} entries</span></div>
    <div className="history-section"><div className="panel-heading"><div><p className="eyebrow">Demo history</p><h2>Prepared starters</h2></div><span className="count-badge">{demoHistory.length}</span></div><p className="muted">These questions are curated for discovery and have not been executed or attributed to a user. Run one to generate its real SQL, result and explanation.</p><div className="history-list">{demoHistory.map((item) => { const example: Example = { id: item.id, title: item.question, question: item.question, category: "demo", tables: item.tables, chart: item.chart }; return <div className="history-row" key={item.id}><div><strong>{item.question}</strong><span>{item.result_summary} · {item.tables.join(", ")}</span></div><button className="secondary-button" onClick={() => onRunExample(example)}>Run</button></div>; })}</div></div>
    <div className="history-section"><div className="panel-heading"><div><p className="eyebrow">Real history</p><h2>Executed analyses</h2></div><span className="count-badge">{history.length}</span></div>{history.length === 0 ? <div className="empty-state">No real analyses yet. Run a question to save it here.</div> : <div className="history-list">{history.map((item, index) => <button className="history-row" key={`${item.question}-${index}`} onClick={() => onSelect(item)}><div><strong>{item.question}</strong><span>{item.status} · {item.retry_count} retries · {item.latency_ms.toFixed(0)} ms{item.cache_hit ? " · cache" : ""}</span></div><span className="tag">Open</span></button>)}</div>}</div>
  </section>;
}
