import { Catalog, CatalogProfile, DatasetInfo, DemoHistoryItem, EnrichmentStatus, Example, QueryResult, RecommendedRun } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export function loadDiscovery(): Promise<[Example[], Catalog, DemoHistoryItem[], DatasetInfo[], CatalogProfile, EnrichmentStatus, RecommendedRun[]]> {
  return Promise.all([
    fetchJson<Example[]>("/examples"),
    fetchJson<Catalog>("/catalog"),
    fetchJson<DemoHistoryItem[]>("/history/demo"),
    fetchJson<DatasetInfo[]>("/datasets"),
    fetchJson<CatalogProfile>("/catalog/profile"),
    fetchJson<EnrichmentStatus>("/catalog/enrichment"),
    fetchJson<RecommendedRun[]>("/recommendations"),
  ]);
}

export function selectDataset(datasetId: string): Promise<DatasetInfo[]> {
  return fetchJson<DatasetInfo[]>("/datasets/select", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId }),
  });
}

export function queryData(question: string, demoId?: string): Promise<QueryResult> {
  return fetchJson<QueryResult>("/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, ...(demoId ? { demo_id: demoId.replace("history-", "") } : {}) }),
  });
}

export function replayQuery(question: string, sql: string): Promise<QueryResult> {
  return fetchJson<QueryResult>("/query/replay", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, sql }),
  });
}
