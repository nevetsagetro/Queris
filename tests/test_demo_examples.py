from queris.demo_examples import get_demo_examples


def test_demo_examples_are_exactly_one_hundred_and_unique() -> None:
    examples = get_demo_examples()

    assert len(examples) == 100
    assert len({example.id for example in examples}) == 100
    assert all(example.question and example.tables for example in examples)
