export type View = "ask" | "catalog" | "history";
export type ChartKind = "bar" | "line" | "metric" | "table";

export type Example = {
  id: string;
  title: string;
  question: string;
  category: string;
  tables: string[];
  chart: ChartKind;
};

export type Column = {
  name: string;
  data_type: string;
  nullable: boolean;
  sample_values: unknown[];
  description: string | null;
  unit: string | null;
};

export type CatalogTable = {
  schema_name: string;
  name: string;
  columns: Column[];
  description: string | null;
};

export type Catalog = {
  table_count: number;
  tables: CatalogTable[];
};

export type DemoHistoryItem = {
  id: string;
  source: "demo";
  created_at: string;
  user: string;
  question: string;
  status: "ready_to_run";
  tables: string[];
  chart: ChartKind;
  explanation: string;
  result_summary: string;
  sql: null;
};

export type QueryResult = {
  status: "success" | "failure" | "clarification" | "no_answer";
  question: string;
  sql: string | null;
  columns: string[];
  rows: unknown[][];
  sources: { schema_name: string; table_name: string; columns: string[] }[];
  retry_count: number;
  latency_ms: number;
  blocked: boolean;
  error: string | null;
  explanation: string | null;
  clarification: string | null;
  no_answer: string | null;
  cache_hit: boolean;
  execution_mode: "llm" | "cache" | "demo";
};
