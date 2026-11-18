import pytest

from paperfeed import llm


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Ends with a stray bracket.)", "Ends with a stray bracket."),
        ("Ends with a stray brace.}", "Ends with a stray brace."),
        ("  Extra whitespace.\n", "Extra whitespace."),
        ("A real aside (like this one)", "A real aside (like this one)"),
        ("(a) and b)", "(a) and b"),
        ("Two periods..", "Two periods."),
        ("An ellipsis...", "An ellipsis..."),
    ],
)
def test_tidy(raw, clean):
    assert llm.tidy(raw) == clean


def test_cards_are_tidied_when_parsed():
    card = llm.Card.model_validate(
        {
            "summary": "s",
            "evaluation": "",
            "use": "u",
            "action": "read",
            "concept": {"name": "n", "explanation": "Explained.)"},
            "terms": [{"term": "t", "meaning": "Meant.}\n"}],
        }
    )

    assert card.concept.explanation == "Explained."
    assert card.terms[0].meaning == "Meant."
