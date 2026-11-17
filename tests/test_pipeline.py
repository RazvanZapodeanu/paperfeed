import json
from datetime import UTC, date, datetime, timedelta

import pytest

from paperfeed import fetch, llm, pipeline
from paperfeed.fetch import Paper

CFG = {
    "queries": ["cat:cs.CR"],
    "lookback_days": 7,
    "keep_days": 30,
    "per_day": {"thesis": 2, "field": 1},
    "min_score": 5,
    "seeds": [],
}
CARD = llm.Card(
    summary="s",
    evaluation="",
    use="u",
    action="note",
    concept=llm.Concept(name="n", explanation="e"),
    terms=[],
)


def paper(arxiv_id: str) -> Paper:
    return Paper(
        id=arxiv_id,
        title=f"Paper {arxiv_id}",
        abstract="An abstract.",
        authors=["Ada Lovelace"],
        published=datetime(2026, 11, 10, tzinfo=UTC),
        categories=["cs.CR"],
    )


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """No arXiv, no Claude, and the data files go to a temp folder."""
    monkeypatch.setattr(pipeline, "DATA", tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(fetch, "by_ids", lambda ids: [paper(i) for i in ids])
    monkeypatch.setattr(llm, "write_card", lambda client, paper, *args: CARD)


def set_papers(monkeypatch, verdicts: dict[str, tuple[str, int]]) -> list[str]:
    """arXiv returns these ids and screening gives each its (tier, score).

    Returns the list that collects the ids as they get screened.
    """
    calls = []

    def screen(client, paper, reading_list, cfg):
        calls.append(paper.id)
        tier, score = verdicts[paper.id]
        return llm.Verdict(reason="because", tier=tier, score=score)

    monkeypatch.setattr(fetch, "recent", lambda queries, since: [paper(i) for i in verdicts])
    monkeypatch.setattr(llm, "screen", screen)
    return calls


def feed_ids() -> list[str]:
    return [card["id"] for card in pipeline.load("feed.json", {"cards": []})["cards"]]


def move_to_yesterday() -> None:
    """Make it look as if the last run happened a day ago."""
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    feed = pipeline.load("feed.json", None)
    for card in feed["cards"]:
        card["added"] = yesterday
    pipeline.save("feed.json", feed)
    screened = pipeline.load("screened.json", None)
    for verdict in screened.values():
        verdict["date"] = yesterday
    pipeline.save("screened.json", screened)


def test_thesis_papers_come_first_then_the_best_field_paper(monkeypatch):
    set_papers(
        monkeypatch,
        {
            "a": ("thesis", 6),
            "b": ("field", 9),
            "c": ("field", 5),
            "d": ("skip", 1),
            "e": ("thesis", 8),
        },
    )

    pipeline.update(CFG)

    assert feed_ids() == ["e", "a", "b"]


def test_verdicts_are_remembered_so_nothing_is_screened_twice(monkeypatch):
    calls = set_papers(
        monkeypatch, {"a": ("thesis", 9), "b": ("thesis", 8), "c": ("thesis", 7), "d": ("skip", 1)}
    )
    pipeline.update(CFG)
    before = (pipeline.DATA / "feed.json").read_text(encoding="utf-8")
    calls.clear()

    pipeline.update(CFG)

    assert calls == []
    assert (pipeline.DATA / "feed.json").read_text(encoding="utf-8") == before


def test_papers_over_the_daily_limit_wait_for_the_next_day(monkeypatch):
    set_papers(
        monkeypatch,
        {
            "a": ("thesis", 9),
            "b": ("thesis", 8),
            "c": ("thesis", 7),
            "x": ("field", 6),
            "y": ("field", 5),
        },
    )

    pipeline.update(CFG)
    assert feed_ids() == ["a", "b", "x"]

    move_to_yesterday()
    pipeline.update(CFG)
    assert feed_ids() == ["c", "y", "a", "b", "x"]


def test_on_equal_scores_the_paper_that_waited_longest_goes_first(monkeypatch):
    set_papers(monkeypatch, {"x": ("field", 5), "y": ("field", 5)})
    pipeline.update(CFG)
    assert feed_ids() == ["x"]

    move_to_yesterday()
    set_papers(monkeypatch, {"z": ("field", 5), "x": ("field", 5), "y": ("field", 5)})
    pipeline.update(CFG)
    assert feed_ids() == ["y", "x"]


def test_papers_under_the_minimum_score_never_get_a_card(monkeypatch):
    calls = set_papers(monkeypatch, {"a": ("thesis", 4), "b": ("field", 5)})

    pipeline.update(CFG)
    move_to_yesterday()
    pipeline.update(CFG)

    assert feed_ids() == ["b"]
    assert calls == ["a", "b"]


def test_a_failed_card_gives_its_place_away_and_is_tried_again(monkeypatch):
    set_papers(monkeypatch, {"a": ("thesis", 9), "b": ("thesis", 8), "c": ("thesis", 7)})
    monkeypatch.setattr(
        llm, "write_card", lambda client, paper, *args: None if paper.id == "a" else CARD
    )
    pipeline.update(CFG)
    assert feed_ids() == ["b", "c"]

    monkeypatch.setattr(llm, "write_card", lambda client, paper, *args: CARD)
    move_to_yesterday()
    pipeline.update(CFG)
    assert feed_ids() == ["a", "b", "c"]


def test_reading_list_gets_cards_once_and_is_never_screened(monkeypatch):
    calls = set_papers(monkeypatch, {"seed": ("thesis", 9), "a": ("thesis", 9)})
    reading_lists = []
    screen = llm.screen

    def spy(client, paper, reading_list, cfg):
        reading_lists.append(reading_list)
        return screen(client, paper, reading_list, cfg)

    monkeypatch.setattr(llm, "screen", spy)
    cfg = CFG | {"seeds": ["seed"]}

    pipeline.update(cfg)
    pipeline.update(cfg)

    feed = pipeline.load("feed.json", None)["cards"]
    assert [(card["id"], card["seed"]) for card in feed] == [("seed", True), ("a", False)]
    assert calls == ["a"]
    assert reading_lists == [["Paper seed"]]


def test_dry_run_writes_nothing(monkeypatch, capsys):
    set_papers(monkeypatch, {"a": ("thesis", 9), "b": ("skip", 1)})

    pipeline.update(CFG, dry_run=True)

    assert list(pipeline.DATA.iterdir()) == []
    assert "Paper a" in capsys.readouterr().out


def test_old_verdicts_are_forgotten(monkeypatch):
    set_papers(monkeypatch, {"a": ("skip", 1)})
    pipeline.save("screened.json", {"old": {"date": "2026-01-01", "tier": "skip"}})

    pipeline.update(CFG)

    assert list(json.loads((pipeline.DATA / "screened.json").read_text())) == ["a"]


def test_prune_drops_old_cards_but_keeps_seeds():
    feed = [
        {"id": "new", "added": "2026-11-10", "seed": False},
        {"id": "old", "added": "2026-10-01", "seed": False},
        {"id": "seed", "added": "2026-10-01", "seed": True},
        {"id": "removed-seed", "added": "2026-11-10", "seed": True},
    ]

    kept = pipeline.prune(feed, seeds=["seed"], cutoff=date(2026, 10, 15))

    assert [card["id"] for card in kept] == ["new", "seed"]
