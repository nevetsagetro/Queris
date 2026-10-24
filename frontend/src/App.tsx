import { FormEvent, useEffect, useState } from "react";
import { loadDiscovery, queryData, replayQuery, selectDataset } from "./api/client";
import { Catalog, CatalogProfile, DatasetInfo, DemoHistoryItem, EnrichmentStatus, Example, QueryResult, RecommendedRun, View } from "./types";
import { AskView } from "./components/AskView";
import { CatalogView } from "./components/CatalogView";
import { HistoryView } from "./components/HistoryView";
import { ResultPanel } from "./components/ResultPanel";

const navItems: { id: View; label: string }[] = [
  { id: "ask", label: "Ask" },
  { id: "catalog", label: "Data catalog" },
  { id: "history", label: "History" },
];

function App() {
  const [view, setView] = useState<View>("ask");
  const [question, setQuestion] = useState("");
  const [selectedDemoId, setSelectedDemoId] = useState<string | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [demoHistory, setDemoHistory] = useState<DemoHistoryItem[]>([]);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [profile, setProfile] = useState<CatalogProfile | null>(null);
  const [enrichment, setEnrichment] = useState<EnrichmentStatus | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendedRun[]>([]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [history, setHistory] = useState<QueryResult[]>(() => readHistory());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const publicDatasets = datasets.filter((dataset) => dataset.source_url);
  const activeDataset = publicDatasets.find((dataset) => dataset.active) ?? null;
  const datasetAvailable = activeDataset !== null;

  useEffect(() => {
    void loadDiscovery()
      .then(([loadedExamples, loadedCatalog, loadedDemoHistory, loadedDatasets, loadedProfile, loadedEnrichment, loadedRecommendations]) => {
        setExamples(loadedExamples);
        setCatalog(loadedCatalog);
        setDemoHistory(loadedDemoHistory);
        setDatasets(loadedDatasets);
        setProfile(loadedProfile);
        setEnrichment(loadedEnrichment);
        setRecommendations(loadedRecommendations);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  const runQuery = async (event?: FormEvent, overrides?: { question: string; demoId?: string }) => {
    event?.preventDefault();
    const nextQuestion = overrides?.question ?? question;
    const nextDemoId = overrides?.demoId ?? selectedDemoId;
    if (!nextQuestion.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const savedAnalysis = history.find((item) => item.sql && normalizeQuestion(item.question) === normalizeQuestion(nextQuestion));
      const nextResult = savedAnalysis?.sql
        ? await replayQuery(nextQuestion, savedAnalysis.sql)
        : await queryData(nextQuestion, nextDemoId ?? undefined);
      setResult(nextResult);
      setSelectedDemoId(null);
      if (!nextResult.cache_hit) {
        const nextHistory = [nextResult, ...history].slice(0, 20);
        setHistory(nextHistory);
        window.localStorage.setItem("queris.history", JSON.stringify(nextHistory));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The query could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  const runExample = (example: Example) => {
    setQuestion(example.question);
    setSelectedDemoId(example.id.replace("history-", ""));
    setView("ask");
    setError(null);
    void runQuery(undefined, { question: example.question, demoId: example.id.replace("history-", "") });
  };

  const changeDataset = async (datasetId: string) => {
    setError(null);
    try {
      const loadedDatasets = await selectDataset(datasetId);
      const [loadedExamples, loadedCatalog, loadedDemoHistory, , loadedProfile, loadedEnrichment, loadedRecommendations] = await loadDiscovery();
      setDatasets(loadedDatasets);
      setExamples(loadedExamples);
      setCatalog(loadedCatalog);
      setDemoHistory(loadedDemoHistory);
      setProfile(loadedProfile);
      setEnrichment(loadedEnrichment);
      setRecommendations(loadedRecommendations);
      setResult(null);
      setSelectedDemoId(null);
      setQuestion("");
      setHistory([]);
      window.localStorage.removeItem("queris.history");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The dataset could not be selected.");
    }
  };

  const useExample = (example: Example) => {
    setQuestion(example.question);
    setSelectedDemoId(example.id.startsWith("history-") ? example.id : example.id);
    setView("ask");
    setResult(null);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">Q</span>
          <span>Queris</span>
          <small>SAFE ANALYTICS</small>
        </div>
        <nav aria-label="Main navigation">
          {navItems.map((item) => (
            <button
              className={view === item.id ? "nav-button active" : "nav-button"}
              key={item.id}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="dataset-picker" aria-label="Dataset context">
          <span className={datasetAvailable ? "dataset-status" : "dataset-status unavailable"} aria-label={datasetAvailable ? "Public dataset available locally" : "No public dataset available"}><span className="status-dot" aria-hidden="true" /><span>{datasetAvailable ? "Ready" : "Unavailable"}</span></span>
          <label className="dataset-select"><span className="sr-only">Active public dataset</span><select aria-label="Active public dataset" value={activeDataset?.id ?? ""} onChange={(event) => void changeDataset(event.target.value)} disabled={!publicDatasets.length}><option value="">No public dataset</option>{publicDatasets.map((dataset) => <option value={dataset.id} key={dataset.id}>{dataset.name}</option>)}</select></label>
          {activeDataset?.source_url && <a className="source-link" href={activeDataset.source_url} target="_blank" rel="noreferrer" aria-label={`Verify ${activeDataset.name} source`} title="Open original dataset source">Verify source <span aria-hidden="true">↗</span></a>}
        </div>
      </header>

      <main className="main-content">
        {error && <div className="alert error">{error}</div>}
        {view === "ask" && (
          <AskView
            question={question}
            setQuestion={setQuestion}
            clearDemo={() => setSelectedDemoId(null)}
            onSubmit={runQuery}
            busy={busy}
            examples={examples}
            onUseExample={useExample}
            result={result}
          />
        )}
        {view === "catalog" && <CatalogView catalog={catalog} profile={profile} enrichment={enrichment} dataset={activeDataset} onUseExample={useExample} examples={examples} />}
        {view === "history" && <HistoryView history={history} demoHistory={demoHistory} recommendations={recommendations} onSelect={setResult} onRunExample={runExample} />}
      </main>
    </div>
  );
}

function readHistory(): QueryResult[] {
  try { return JSON.parse(window.localStorage.getItem("queris.history") ?? "[]") as QueryResult[]; } catch { return []; }
}

function normalizeQuestion(question: string): string {
  return question.trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

export default App;
