from queris.demo_registry import get_demo_definition, get_demo_registry
from queris.sql_validation import parse_read_only


def test_registry_contains_one_executable_definition_per_demo() -> None:
    registry = get_demo_registry()

    assert len(registry) == 100
    assert len({item.example.id for item in registry}) == 100
    for item in registry:
        assert item.sql_builder(item.variant)
        parse_read_only(item.sql_builder(item.variant))


def test_registry_resolves_demo_without_interpreting_identifier() -> None:
    definition = get_demo_definition("revenue-03")

    assert definition is not None
    assert definition.example.question == "What was total revenue by month?"
    assert "DATE_TRUNC('month'" in definition.sql_builder(definition.variant)
