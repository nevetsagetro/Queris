import { useEffect, useState } from "react";
import { Catalog, CatalogProfile, DatasetInfo, EnrichmentStatus, Example } from "../types";

type CatalogViewProps = {
  catalog: Catalog | null;
  profile: CatalogProfile | null;
  enrichment: EnrichmentStatus | null;
  dataset: DatasetInfo | null;
  examples: Example[];
  onUseExample: (example: Example) => void;
};

export function CatalogView({ catalog, profile, enrichment, dataset, examples, onUseExample }: CatalogViewProps) {
  const [selected, setSelected] = useState(0);
  const table = catalog?.tables[selected];
  const selectedProfile = profile?.tables.find((item) => item.name === table?.name);

  useEffect(() => {
    setSelected(0);
  }, [catalog]);

  return (
    <section>
      {dataset && (
        <div className="dataset-context">
          <div>
            <p className="eyebrow">Active dataset</p>
            <h2>{dataset.name}</h2>
            <p className="dataset-tagline">{dataset.source_name ?? "Local DuckDB file"}</p>
          </div>
          <div className="dataset-facts">
            <span><small>Local file</small><strong>{dataset.id}</strong></span>
            {dataset.license && <span><small>License</small><strong>{dataset.license}</strong></span>}
            {dataset.source_url ? <a href={dataset.source_url} target="_blank" rel="noreferrer" aria-label={`Open public source for ${dataset.name}`} title="Open public source">Source ↗</a> : null}
          </div>
        </div>
      )}
      <div className="page-heading">
        <div><p className="eyebrow">Understand the source</p><h1>Data catalog</h1><p className="lede">See what Queris can use before asking a question.</p></div>
        <span className="catalog-stat">{catalog?.table_count ?? 0} tables · Catalog {enrichment?.status ?? "unknown"}</span>
      </div>
      <div className="catalog-layout">
        <div className="table-list">{catalog?.tables.map((item, index) => <button className={index === selected ? "table-nav selected" : "table-nav"} key={item.name} onClick={() => setSelected(index)}><strong>{item.name}</strong><span>{item.columns.length} columns</span></button>)}</div>
        <div className="table-detail">
          {table ? <>
            <div className="detail-heading"><div><p className="eyebrow">main.{table.name}</p><h2>{table.description ?? "Source table"}</h2></div><span className="tag">Live schema</span></div>
            {selectedProfile && <div className="profile-strip"><span><strong>{selectedProfile.row_count.toLocaleString()}</strong> rows</span><span><strong>{selectedProfile.columns.length}</strong> columns</span><span><strong>{profile?.relationships.filter((item) => item.left_table === table.name || item.right_table === table.name).length ?? 0}</strong> relationships</span></div>}
            <div className="column-table"><div className="column-row column-header"><span>Column</span><span>Type</span><span>Examples</span></div>{table.columns.map((column) => { const profileColumn = selectedProfile?.columns.find((item) => item.name === column.name); const nullRate = profileColumn && profileColumn.row_count ? profileColumn.null_count / profileColumn.row_count * 100 : 0; return <div className="column-row" key={column.name}><div><strong>{column.name}</strong><small>{column.description ?? "No description yet"}</small>{profileColumn && <small>{profileColumn.distinct_count.toLocaleString()} distinct · {nullRate.toFixed(1)}% nulls</small>}</div><span className="mono">{column.data_type}</span><span>{column.sample_values.slice(0, 3).map(String).join(", ") || "—"}</span></div>; })}</div>
          </> : <div className="empty-state">Catalog unavailable.</div>}
        </div>
      </div>
      {profile?.relationships.length ? <div className="relationship-panel"><div className="panel-heading"><div><p className="eyebrow">Structure</p><h2>Detected relationships</h2></div><span className="count-badge">{profile.relationships.length}</span></div>{profile.relationships.map((relationship) => <div className="relationship-row" key={`${relationship.left_table}.${relationship.left_column}-${relationship.right_table}.${relationship.right_column}`}><span><strong>{relationship.left_table}.{relationship.left_column}</strong> → <strong>{relationship.right_table}.{relationship.right_column}</strong></span><span>{relationship.cardinality} · {relationship.coverage_percent.toFixed(1)}% coverage · {relationship.confidence}</span></div>)}</div> : null}
      <div className="catalog-examples"><div className="panel-heading"><div><p className="eyebrow">Browse all samples</p><h2>{examples.length} dataset starters</h2></div></div><div className="example-grid">{examples.map((example) => <button className="example-card" key={example.id} onClick={() => onUseExample(example)}><span className="example-category">{example.category}</span><strong>{example.title}</strong><span>{example.question}</span></button>)}</div></div>
    </section>
  );
}
