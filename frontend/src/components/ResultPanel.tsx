import { useEffect, useMemo, useState } from "react";
import { QueryResult } from "../types";

export function ResultPanel({ result }: { result: QueryResult }) {
  const [showLightChart, setShowLightChart] = useState(false);
  const chartConfidence = result.chart_recommendation?.confidence ?? 0;
  const chartAvailable = result.status === "success" && result.chart_recommendation?.chart !== "table";
  const chartReady = chartAvailable && chartConfidence >= 0.9;
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
          {result.chart_recommendation && <div className="chart-recommendation"><div><p className="eyebrow">{chartReady ? "Recommended view" : "Possible view"}</p><strong>{result.chart_recommendation.chart} chart</strong><span>{result.chart_recommendation.reason}</span></div><div className="chart-recommendation-action"><b>{Math.round(result.chart_recommendation.confidence * 100)}% confidence</b>{chartAvailable && <button type="button" className="secondary-button" onClick={() => setShowLightChart((visible) => !visible)}>{showLightChart ? "Hide chart" : chartReady ? "View chart" : "Preview chart"}</button>}{chartAvailable && !chartReady && <small className="chart-confidence-note">Preview only · below 90%</small>}</div></div>}
          {result.similar_questions.length > 0 && <div className="language-panel"><p className="eyebrow">Language analysis</p><strong>Related validated patterns</strong>{result.similar_questions.slice(0, 3).map((item) => <span key={item.demo_id}>{Math.round(item.similarity * 100)}% · {item.question}</span>)}</div>}
          <div className="result-section"><p className="eyebrow">Results · Resultado</p><div className="result-table"><div className="column-row column-header">{result.columns.map((column) => <span key={column}>{column}</span>)}</div>{result.rows.slice(0, 100).map((row, index) => <div className="column-row" key={index}>{row.map((value, cell) => <span key={cell}>{String(value)}</span>)}</div>)}</div>
          {showLightChart && <ResultChart result={result} />}</div>
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

function ResultChart({ result }: { result: QueryResult }) {
  const recommendation = result.chart_recommendation;
  if (!recommendation || recommendation.chart === "table") return <ChartUnavailable />;
  const series = chartSeries(result, recommendation.x_field, recommendation.y_field);
  if (recommendation.chart === "metric") {
    const value = series[0]?.value;
    return value === undefined ? <ChartUnavailable /> : <div className="mini-chart metric-preview"><p className="eyebrow">Metric · {recommendation.y_field ?? "value"}</p><strong>{value.toLocaleString()}</strong><span>{recommendation.reason}</span></div>;
  }
  if (!series.length) return <ChartUnavailable />;
  if (recommendation.chart === "line") return <LineChart series={series} label={recommendation.y_field ?? "value"} />;
  if (recommendation.chart === "scatter") return <ScatterChart series={series} />;
  return <BarChart series={series} label={recommendation.y_field ?? "value"} />;
}

function BarChart({ series, label }: { series: ChartPoint[]; label: string }) {
  const max = Math.max(...series.map((item) => item.value), 0);
  return <div className="mini-chart"><p className="eyebrow">Bar chart · {label}</p>{series.slice(0, 8).map((item, index) => <div className="bar-row" key={`${item.label}-${index}`}><span>{item.label}</span><div><i style={{ width: `${max ? Math.max(0, (item.value / max) * 100) : 0}%` }} /></div><strong>{item.value.toLocaleString()}</strong></div>)}</div>;
}

function LineChart({ series, label }: { series: ChartPoint[]; label: string }) {
  const points = svgPoints(series);
  return <div className="mini-chart"><p className="eyebrow">Line chart · {label}</p><svg className="chart-svg" viewBox="0 0 640 220" role="img" aria-label={`Line chart of ${label}`}><polyline points={points} fill="none" stroke="#176b87" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />{series.slice(0, 12).map((item, index) => { const [x, y] = points.split(" ")[index].split(","); return <circle cx={x} cy={y} r="4" fill="#176b87" key={`${item.label}-${index}`} />; })}</svg><ChartLabels series={series} /></div>;
}

function ScatterChart({ series }: { series: ChartPoint[] }) {
  const points = svgPoints(series);
  return <div className="mini-chart"><p className="eyebrow">Scatter chart</p><svg className="chart-svg" viewBox="0 0 640 220" role="img" aria-label="Scatter chart"><line x1="36" y1="188" x2="620" y2="188" stroke="#dbe3ed" /><line x1="36" y1="20" x2="36" y2="188" stroke="#dbe3ed" />{series.slice(0, 40).map((item, index) => { const [x, y] = points.split(" ")[index].split(","); return <circle cx={x} cy={y} r="5" fill="#176b87" fillOpacity=".75" key={`${item.label}-${index}`} />; })}</svg></div>;
}

function ChartLabels({ series }: { series: ChartPoint[] }) {
  return <div className="chart-axis-labels">{series.slice(0, 6).map((item, index) => <span key={`${item.label}-${index}`}>{item.label}</span>)}</div>;
}

type ChartPoint = { label: string; value: number };

function chartSeries(result: QueryResult, xField: string | null, yField: string | null): ChartPoint[] {
  const xIndex = xField ? result.columns.indexOf(xField) : 0;
  const yIndex = yField ? result.columns.indexOf(yField) : result.columns.findIndex((_, index) => result.rows.some((row) => Number.isFinite(Number(row[index]))));
  if (yIndex < 0) return [];
  return result.rows.map((row) => ({ label: String(row[xIndex >= 0 ? xIndex : 0]), value: Number(row[yIndex]) })).filter((item) => Number.isFinite(item.value)).slice(0, 40);
}

function svgPoints(series: ChartPoint[]): string {
  const values = series.map((item) => item.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return series.map((item, index) => `${36 + (index * 584) / Math.max(series.length - 1, 1)},${188 - ((item.value - min) / range) * 168}`).join(" ");
}

function ChartUnavailable() {
  return <div className="mini-chart metric-preview"><p className="eyebrow">Chart</p><strong>No chartable series</strong><span>The result is available as a table because its shape is not suitable for this visual.</span></div>;
}
