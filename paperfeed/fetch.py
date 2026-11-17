import re
from dataclasses import dataclass
from datetime import datetime

import arxiv

# One shared client, so the delay between requests holds across all queries.
# arXiv asks for at most one request every 3 seconds.
client = arxiv.Client(page_size=200, delay_seconds=5, num_retries=5)


@dataclass
class Paper:
    id: str
    title: str
    abstract: str
    authors: list[str]
    published: datetime
    categories: list[str]

    @property
    def url(self) -> str:
        return f"https://arxiv.org/abs/{self.id}"


def _to_paper(result: arxiv.Result) -> Paper:
    primary = result.primary_category
    return Paper(
        id=re.sub(r"v\d+$", "", result.get_short_id()),
        title=result.title,
        abstract=" ".join(result.summary.split()),
        authors=[author.name for author in result.authors],
        published=result.published,
        categories=[primary] + [c for c in result.categories if c != primary],
    )


def recent(queries: list[str], since: datetime) -> list[Paper]:
    """Papers submitted after `since` that match at least one query."""
    papers = {}
    for query in queries:
        search = arxiv.Search(
            query=query,
            max_results=None,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        # Newest first, so the first paper that is too old ends the query.
        for result in client.results(search):
            if result.published < since:
                break
            paper = _to_paper(result)
            papers[paper.id] = paper
    return list(papers.values())


def by_ids(ids: list[str]) -> list[Paper]:
    """The papers with these arXiv ids, in the order given."""
    if not ids:
        return []
    search = arxiv.Search(id_list=ids, max_results=len(ids))
    found = {paper.id: paper for paper in map(_to_paper, client.results(search))}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValueError(f"not found on arXiv: {', '.join(missing)}")
    return [found[i] for i in ids]
