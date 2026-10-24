import { Catalog, DemoHistoryItem, Example, QueryResult } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export function loadDiscovery(): Promise<[Example[], Catalog, DemoHistoryItem[]]> {
  return Promise.all([
    fetchJson<Example[]>("/examples"),
    fetchJson<Catalog>("/catalog"),
    fetchJson<DemoHistoryItem[]>("/history/demo"),
  ]);
}

export function queryData(question: string, demoId?: string): Promise<QueryResult> {
  return fetchJson<QueryResult>("/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, ...(demoId ? { demo_id: demoId.replace("history-", "") } : {}) }),
  });
}
