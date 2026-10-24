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

export type DatasetInfo = {
  id: string;
  name: string;
  source_name: string | null;
  source_url: string | null;
  license: string | null;
  size_bytes: number;
  modified_at: string;
  active: boolean;
};

export type CatalogProfile = {
  source: "read_only_profile";
  tables: TableProfile[];
  relationships: RelationshipProfile[];
};

export type TableProfile = {
  schema_name: string;
  name: string;
  row_count: number;
  columns: ColumnProfile[];
};

export type ColumnProfile = {
  name: string;
  data_type: string;
  row_count: number;
  null_count: number;
  distinct_count: number;
  min_value: unknown;
  max_value: unknown;
};

export type RelationshipProfile = {
  left_table: string;
  left_column: string;
  right_table: string;
  right_column: string;
  cardinality: "1:1" | "1:N" | "N:1" | "N:N";
  coverage_percent: number;
  confidence: "low" | "medium" | "high";
};

export type EnrichmentStatus = {
  status: "raw" | "approved" | "stale";
  reviewed: boolean;
  table_count: number;
  issues: unknown[];
};

export type RecommendedRun = {
  id: string;
  demo_id: string;
  question: string;
  reason: string;
  tables: string[];
  chart: ChartKind;
  priority: number;
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
  chart_recommendation: ChartRecommendation | null;
};

export type ChartRecommendation = {
  chart: "bar" | "line" | "scatter" | "metric" | "table";
  confidence: number;
  x_field: string | null;
  y_field: string | null;
  reason: string;
};
