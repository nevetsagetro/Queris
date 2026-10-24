import { FormEvent, useEffect, useState } from "react";
import { loadDiscovery, queryData } from "./api/client";
import { DemoHistoryItem, Example, QueryResult, View } from "./types";
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
  const [result, setResult] = useState<QueryResult | null>(null);
  const [history, setHistory] = useState<QueryResult[]>(() => readHistory());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadDiscovery()
      .then(([loadedExamples, loadedCatalog, loadedDemoHistory]) => {
        setExamples(loadedExamples);
        setCatalog(loadedCatalog);
        setDemoHistory(loadedDemoHistory);
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
      const nextResult = await queryData(nextQuestion, nextDemoId ?? undefined);
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
    void runQuery(undefined, { question: example.question, demoId: example.id });
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
        <div className="connection"><span className="status-dot" /> Local DuckDB</div>
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
        {view === "catalog" && <CatalogView catalog={catalog} onUseExample={useExample} examples={examples} />}
        {view === "history" && <HistoryView history={history} demoHistory={demoHistory} onSelect={setResult} onRunExample={runExample} />}
      </main>
    </div>
  );
}

function readHistory(): QueryResult[] {
  try { return JSON.parse(window.localStorage.getItem("queris.history") ?? "[]") as QueryResult[]; } catch { return []; }
}

export default App;
