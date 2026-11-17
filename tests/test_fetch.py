from datetime import UTC, datetime

import arxiv
import pytest

from paperfeed import fetch


def result(arxiv_id: str, day: int, **fields) -> arxiv.Result:
    defaults = {
        "entry_id": f"http://arxiv.org/abs/{arxiv_id}",
        "published": datetime(2026, 11, day, tzinfo=UTC),
        "primary_category": "cs.CR",
        "categories": ["cs.CR"],
    }
    return arxiv.Result(**(defaults | fields))


def test_to_paper_cleans_up_the_api_result():
    paper = fetch._to_paper(
        result(
            "2611.00001v3",
            day=10,
            title="A title",
            summary="  First line\n  second line.\n",
            authors=[arxiv.Result.Author("Ada Lovelace")],
            categories=["cs.LG", "cs.CR"],
        )
    )

    assert paper.id == "2611.00001"
    assert paper.url == "https://arxiv.org/abs/2611.00001"
    assert paper.abstract == "First line second line."
    assert paper.authors == ["Ada Lovelace"]
    assert paper.categories == ["cs.CR", "cs.LG"]


def test_recent_stops_at_the_cutoff_and_merges_queries(monkeypatch):
    by_query = {
        "cat:cs.CR": [
            result("2611.00003v1", day=12),
            result("2611.00002v1", day=11),
            result("2611.00001v1", day=3),
        ],
        "cat:cs.NI": [
            result("2611.00004v1", day=12),
            result("2611.00002v1", day=11),
        ],
    }
    monkeypatch.setattr(fetch.client, "results", lambda search: iter(by_query[search.query]))

    since = datetime(2026, 11, 5, tzinfo=UTC)
    papers = fetch.recent(list(by_query), since)

    assert sorted(p.id for p in papers) == ["2611.00002", "2611.00003", "2611.00004"]


def test_by_ids_keeps_the_order_it_was_asked_for(monkeypatch):
    found = [result("2611.00002v1", day=2), result("2611.00001v1", day=1)]
    monkeypatch.setattr(fetch.client, "results", lambda search: iter(found))

    papers = fetch.by_ids(["2611.00001", "2611.00002"])

    assert [p.id for p in papers] == ["2611.00001", "2611.00002"]


def test_by_ids_fails_on_an_id_arxiv_does_not_know(monkeypatch):
    found = [result("2611.00001v1", day=1)]
    monkeypatch.setattr(fetch.client, "results", lambda search: iter(found))

    with pytest.raises(ValueError, match="2611.99999"):
        fetch.by_ids(["2611.00001", "2611.99999"])
