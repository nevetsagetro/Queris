import { DemoHistoryItem, Example, MetricsSummary, QueryResult, RecommendedRun } from "../types";

type Props = {
  history: QueryResult[];
  demoHistory: DemoHistoryItem[];
  recommendations: RecommendedRun[];
  metrics: MetricsSummary | null;
  onSelect: (result: QueryResult) => void;
  onRunExample: (example: Example) => void;
};

export function HistoryView({ history, demoHistory, recommendations, metrics, onSelect, onRunExample }: Props) {
  return <section><div className="page-heading"><div><p className="eyebrow">Persistent workspace</p><h1>History</h1><p className="lede">Recommendations lead to prepared demos; real analyses stay available after a reload.</p></div><span className="catalog-stat">{demoHistory.length + history.length} entries</span></div>
    <div className="metrics-strip" aria-label="Workspace metrics"><span><strong>{metrics?.query_count ?? 0}</strong> analyses</span><span><strong>{metrics?.cache_hits ?? 0}</strong> cache hits</span><span><strong>{metrics?.llm_count ?? 0}</strong> LLM calls</span><span><strong>{metrics?.total_latency_ms ?? 0}</strong> ms total</span></div>
    <div className="history-section"><div className="panel-heading"><div><p className="eyebrow">Recommended runs</p><h2>Start with the useful questions</h2></div><span className="count-badge">{recommendations.length}</span></div><div className="recommendation-list">{recommendations.map((recommendation) => { const example: Example = { id: recommendation.demo_id, title: recommendation.question, question: recommendation.question, category: "recommended", tables: recommendation.tables, chart: recommendation.chart }; return <div className="recommendation-row" key={recommendation.id}><div><strong>{recommendation.question}</strong><span>{recommendation.reason} · {recommendation.tables.join(", ")}</span></div><button className="secondary-button" onClick={() => onRunExample(example)}>Run</button></div>; })}</div></div>
    <div className="history-section"><div className="panel-heading"><div><p className="eyebrow">Demo history</p><h2>Prepared starters</h2></div><span className="count-badge">{demoHistory.length}</span></div><p className="muted">These questions are curated for discovery and have not been executed or attributed to a user. Run one to generate its real SQL, result and explanation.</p><div className="history-list">{demoHistory.map((item) => { const example: Example = { id: item.id, title: item.question, question: item.question, category: "demo", tables: item.tables, chart: item.chart }; return <div className="history-row" key={item.id}><div><strong>{item.question}</strong><span>{item.result_summary} · {item.tables.join(", ")}</span></div><button className="secondary-button" onClick={() => onRunExample(example)}>Run</button></div>; })}</div></div>
    <div className="history-section"><div className="panel-heading"><div><p className="eyebrow">Real history</p><h2>Executed analyses</h2></div><span className="count-badge">{history.length}</span></div>{history.length === 0 ? <div className="empty-state">No real analyses yet. Run a question to save it here.</div> : <div className="history-list">{history.map((item, index) => <button className="history-row" key={`${item.question}-${index}`} onClick={() => onSelect(item)}><div><strong>{item.question}</strong><span>{item.status} · {item.retry_count} retries · {item.latency_ms.toFixed(0)} ms{item.cache_hit ? " · cache" : ""}</span></div><span className="tag">Open</span></button>)}</div>}</div>
  </section>;
}
