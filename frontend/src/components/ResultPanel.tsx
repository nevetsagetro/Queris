import { useMemo } from "react";
import { QueryResult } from "../types";

export function ResultPanel({ result }: { result: QueryResult }) {
  const numeric = useMemo(() => numericResult(result), [result]);
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
          <div className="result-section"><p className="eyebrow">Results · Resultado</p><div className="result-table"><div className="column-row column-header">{result.columns.map((column) => <span key={column}>{column}</span>)}</div>{result.rows.slice(0, 100).map((row, index) => <div className="column-row" key={index}>{row.map((value, cell) => <span key={cell}>{String(value)}</span>)}</div>)}</div>
          {numeric && <div className="mini-chart"><p className="eyebrow">Quick chart · {numeric.label}</p>{numeric.items.map((item) => <div className="bar-row" key={item.label}><span>{item.label}</span><div><i style={{ width: `${(item.value / numeric.max) * 100}%` }} /></div><strong>{item.value.toLocaleString()}</strong></div>)}</div>}</div>
          <div className="result-section"><p className="eyebrow">SQL · Consulta ejecutada</p><pre className="sql-view">{result.sql}</pre></div>
          <div className="result-section"><p className="eyebrow">Sources · Origen de datos</p><div className="source-list">{result.sources.map((source) => <p key={`${source.schema_name}.${source.table_name}`}><strong>{source.schema_name}.{source.table_name}</strong><br />{source.columns.join(", ")}</p>)}</div></div>
        </>
      )}
    </section>
  );
}

function numericResult(result: QueryResult) {
  if (result.columns.length < 2) return null;
  const values = result.rows.map((row) => Number(row[row.length - 1])).filter(Number.isFinite);
  if (!values.length) return null;
  const max = Math.max(...values);
  return { label: result.columns[result.columns.length - 1], max, items: result.rows.slice(0, 8).map((row) => ({ label: String(row[0]), value: Number(row[row.length - 1]) })).filter((item) => Number.isFinite(item.value)) };
}
