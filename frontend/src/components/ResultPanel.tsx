import { useEffect, useMemo, useState } from "react";
import { QueryResult } from "../types";

export function ResultPanel({ result }: { result: QueryResult }) {
  const numeric = useMemo(() => numericResult(result), [result]);
  const [showLightChart, setShowLightChart] = useState(false);
  const chartConfidence = result.chart_recommendation?.confidence ?? 0;
  const chartReady = result.status === "success" && chartConfidence >= 0.9 && result.chart_recommendation?.chart !== "table";
  useEffect(() => setShowLightChart(false), [result.question, result.sql]);
  const message = result.status === "success" ? "Analysis complete" : result.explanation ?? result.clarification ?? result.no_answer ?? result.error ?? "No answer returned.";
  return (
    <section className="result-panel">
      <div className="result-heading">
        <div>
          <p className="eyebrow">{result.execution_mode === "demo" ? "Prepared demo · no LLM" : result.cache_hit ? "Session cache" : "Analysis complete"}</p>
          <h2>{result.status === "success" ? message : "Analysis stopped"}</h2>
        </div>
        <div className="metrics"><span>{result.retry_count} retries</span><span>{result.latency_ms.toFixed(0)} ms</span><span className={result.blocked ? "blocked" : "ok"}>{result.blocked ? "Blocked" : "Read-only"}</span></div>
      </div>
      {result.status === "success" && (
        <>
          {result.chart_recommendation && <div className="chart-recommendation"><div><p className="eyebrow">Recommended view</p><strong>{result.chart_recommendation.chart} chart</strong><span>{result.chart_recommendation.reason}</span></div><div className="chart-recommendation-action"><b>{Math.round(result.chart_recommendation.confidence * 100)}% confidence</b>{chartReady && <button type="button" className="secondary-button" onClick={() => setShowLightChart((visible) => !visible)}>{showLightChart ? "Hide chart" : "View chart"}</button>}</div></div>}
          {result.similar_questions.length > 0 && <div className="language-panel"><p className="eyebrow">Language analysis</p><strong>Related validated patterns</strong>{result.similar_questions.slice(0, 3).map((item) => <span key={item.demo_id}>{Math.round(item.similarity * 100)}% · {item.question}</span>)}</div>}
          <div className="result-section"><p className="eyebrow">Results · Resultado</p><div className="result-table"><div className="column-row column-header">{result.columns.map((column) => <span key={column}>{column}</span>)}</div>{result.rows.slice(0, 100).map((row, index) => <div className="column-row" key={index}>{row.map((value, cell) => <span key={cell}>{String(value)}</span>)}</div>)}</div>
          {showLightChart && numeric && <div className="mini-chart"><p className="eyebrow">Light chart · {numeric.label}</p>{numeric.items.map((item) => <div className="bar-row" key={item.label}><span>{item.label}</span><div><i style={{ width: `${numeric.max ? Math.max(0, (item.value / numeric.max) * 100) : 0}%` }} /></div><strong>{item.value.toLocaleString()}</strong></div>)}</div>}
          {showLightChart && !numeric && <div className="mini-chart metric-preview"><p className="eyebrow">Light chart</p><strong>No chartable numeric values</strong><span>The result is available as a table because it contains no numeric series to plot.</span></div>}</div>
          <div className="result-section"><SqlViewer result={result} /></div>
          <div className="result-section"><p className="eyebrow">Sources · Origen de datos</p><div className="source-list">{result.sources.map((source) => <p key={`${source.schema_name}.${source.table_name}`}><strong>{source.schema_name}.{source.table_name}</strong><br />{source.columns.join(", ")}</p>)}</div></div>
        </>
      )}
    </section>
  );
}

function SqlViewer({ result }: { result: QueryResult }) {
  const [copied, setCopied] = useState(false);
  const sql = result.sql ?? "";
  const displaySql = result.display_sql ?? sql;
  const lines = displaySql.split(/\r?\n/);
  const mode = result.cache_hit ? "Cache replay" : result.execution_mode === "demo" ? "Prepared demo" : "Generated SQL";

  const copySql = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return <div className="sql-block">
    <div className="sql-toolbar">
      <div><p className="eyebrow">SQL · Consulta ejecutada</p><span className="sql-context">{mode} · DuckDB · read-only</span></div>
      <button type="button" className="secondary-button sql-copy" onClick={() => void copySql()} disabled={!sql} aria-label="Copy SQL query">{copied ? "Copied" : "Copy SQL"}</button>
    </div>
    <pre className="sql-view"><code>{lines.map((line, index) => <span className="sql-line" key={`${index}-${line}`}><span className="sql-line-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span><span>{line || " "}</span></span>)}</code></pre>
  </div>;
}

function numericResult(result: QueryResult) {
  const numericIndex = result.columns.findIndex((_, index) => result.rows.some((row) => Number.isFinite(Number(row[index]))));
  if (numericIndex < 0) return null;
  const values = result.rows.map((row) => Number(row[numericIndex])).filter(Number.isFinite);
  if (!values.length) return null;
  const max = Math.max(...values);
  return { label: result.columns[numericIndex], max, items: result.rows.slice(0, 8).map((row) => ({ label: String(row[0]), value: Number(row[numericIndex]) })).filter((item) => Number.isFinite(item.value)) };
}
