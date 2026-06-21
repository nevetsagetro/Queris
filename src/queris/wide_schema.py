"""Deterministic wide-schema fixture for retrieval evaluation."""

import argparse
import json
from pathlib import Path
from typing import Annotated, Literal, Self

import duckdb
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

WIDE_TABLE_NAMES = (
    "accounts_receivable",
    "ad_campaigns",
    "asset_register",
    "billing_adjustments",
    "budget_allocations",
    "cash_transactions",
    "customer_accounts",
    "delivery_routes",
    "employee_shifts",
    "energy_usage",
    "expense_claims",
    "facility_checks",
    "freight_charges",
    "inventory_balances",
    "invoice_snapshots",
    "loyalty_activity",
    "maintenance_jobs",
    "manufacturing_runs",
    "marketing_leads",
    "order_backlog",
    "payment_attempts",
    "payroll_entries",
    "procurement_lines",
    "product_returns",
    "project_forecasts",
    "quality_inspections",
    "refund_requests",
    "sales_pipeline",
    "service_tickets",
    "shipment_events",
    "subscription_usage",
    "supplier_scores",
)

LabelString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ColumnReference(BaseModel):
    """One hand-labeled schema column relevant to a retrieval question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: LabelString
    table_name: LabelString
    column_name: LabelString


class RetrievalLabel(BaseModel):
    """One retrieval question and its expected schema columns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    question: LabelString
    relevant_columns: tuple[ColumnReference, ...]

    @model_validator(mode="after")
    def require_unique_columns(self) -> Self:
        if not self.relevant_columns:
            raise ValueError("retrieval label must contain at least one relevant column")
        if len(self.relevant_columns) != len(set(self.relevant_columns)):
            raise ValueError("relevant columns must be unique")
        return self


class RetrievalLabelSet(BaseModel):
    """Versioned retrieval ground truth for the wide schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    cases: tuple[RetrievalLabel, ...]

    @model_validator(mode="after")
    def require_unique_cases(self) -> Self:
        if not self.cases:
            raise ValueError("retrieval label set must contain at least one case")
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("retrieval label ids must be unique")
        return self


def create_wide_schema_database(database_path: str | Path) -> Path:
    """Create the deterministic wide fixture without replacing an existing path."""
    path = Path(database_path)
    if path.exists():
        raise FileExistsError(f"Refusing to replace existing path: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(database=str(path))
    try:
        for index, table_name in enumerate(WIDE_TABLE_NAMES, start=1):
            _create_table(connection, table_name)
            _load_rows(connection, table_name, index)
    except Exception:
        connection.close()
        path.unlink(missing_ok=True)
        raise
    else:
        connection.close()
    return path


def load_retrieval_labels(path: str | Path) -> RetrievalLabelSet:
    """Load and validate versioned wide-schema retrieval ground truth."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return RetrievalLabelSet.model_validate(document)


def _create_table(connection: duckdb.DuckDBPyConnection, table_name: str) -> None:
    table = _quote_identifier(table_name)
    connection.execute(
        f"""
        CREATE TABLE {table} (
            row_id INTEGER PRIMARY KEY,
            entity_id INTEGER NOT NULL,
            amt DECIMAL(12, 2) NOT NULL,
            qty INTEGER NOT NULL,
            flg_x BOOLEAN NOT NULL,
            event_date DATE NOT NULL
        )
        """
    )


def _load_rows(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    table_index: int,
) -> None:
    table = _quote_identifier(table_name)
    month = ((table_index - 1) % 12) + 1
    connection.executemany(
        f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                1,
                table_index * 100 + 1,
                f"{table_index * 10}.25",
                table_index,
                False,
                f"2026-{month:02d}-01",
            ),
            (
                2,
                table_index * 100 + 2,
                f"{table_index * 10 + 5}.75",
                table_index + 1,
                True,
                f"2026-{month:02d}-15",
            ),
        ],
    )


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the Queris wide-schema fixture")
    parser.add_argument("database", type=Path, help="Output .duckdb path")
    args = parser.parse_args()
    print(create_wide_schema_database(args.database))


if __name__ == "__main__":
    main()
