from queris.language_similarity import analyze_question, find_similar_questions


def test_language_analysis_extracts_slots() -> None:
    intent = analyze_question("How many customers were there in December?")

    assert intent.entity == "customer"
    assert intent.filters == ("december",)
    assert intent.time_grain == "month"


def test_language_similarity_finds_a_reusable_customer_pattern() -> None:
    similar = find_similar_questions("How many customers were there in December?")

    assert similar
    assert any(item.intent.entity == "customer" for item in similar)
