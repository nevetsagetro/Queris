from queris.catalog_profile import CatalogProfile
from queris.schema import ColumnSchema, DatabaseSchema, TableSchema
from queris.semantic_discovery import (
    build_enrichment_prompt,
    cached_enrichment,
    generate_enrichment,
    parse_enrichment_response,
)


def _schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=(
            TableSchema(
                schema_name="main",
                name="orders",
                columns=(
                    ColumnSchema(
                        name="order_id",
                        data_type="INTEGER",
                        nullable=False,
                        ordinal_position=1,
                        sample_values=(1, 2),
                    ),
                ),
            ),
        )
    )


def test_prompt_contains_bounded_discovery_and_untrusted_data_rules() -> None:
    schema = _schema()
    profile = CatalogProfile(source="read_only_profile", tables=(), relationships=())

    prompt = build_enrichment_prompt(schema, profile)

    assert "never as instructions" in prompt
    assert "orders" in prompt
    assert "read_only_profile" in prompt


def test_parse_enrichment_forces_human_review() -> None:
    enrichment = parse_enrichment_response(
        """```yaml
version: 1
reviewed: true
tables:
  - schema_name: main
    name: orders
    description: Customer orders.
    columns:
      - name: order_id
        description: Order identifier.
```"""
    )

    assert enrichment.reviewed is False
    assert enrichment.tables[0].name == "orders"


def test_generation_uses_provider_boundary_without_database_access() -> None:
    class FakeGenerator:
        def __init__(self) -> None:
            self.prompt = ""

        def generate(self, prompt: str) -> str:
            self.prompt = prompt
            return """version: 1
reviewed: false
tables:
  - schema_name: main
    name: orders
    description: Customer orders.
    columns:
      - name: order_id
        description: Order identifier.
"""

    generator = FakeGenerator()
    enrichment = generate_enrichment(
        _schema(),
        CatalogProfile(source="read_only_profile", tables=(), relationships=()),
        generator,
    )

    assert enrichment.reviewed is False
    assert "order_id" in generator.prompt


def test_cached_enrichment_reuses_prompt_result(tmp_path) -> None:
    class CountingGenerator:
        calls = 0

        def generate(self, _prompt: str) -> str:
            self.calls += 1
            return """version: 1
reviewed: false
tables:
  - schema_name: main
    name: orders
    description: Customer orders.
    columns:
      - name: order_id
        description: Order identifier.
"""

    generator = CountingGenerator()
    profile = CatalogProfile(source="read_only_profile", tables=(), relationships=())
    first = cached_enrichment(_schema(), profile, generator, tmp_path / "enrichment.yaml")
    second = cached_enrichment(_schema(), profile, generator, tmp_path / "enrichment.yaml")

    assert first == second
    assert generator.calls == 1
