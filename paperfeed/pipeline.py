import json
import logging
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import anthropic

from . import fetch, llm

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"
DATA = ROOT / "data"
TIERS = ("thesis", "field")

log = logging.getLogger(__name__)


def load_config() -> dict:
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def load(name: str, default):
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(name: str, content) -> None:
    DATA.mkdir(exist_ok=True)
    text = json.dumps(content, ensure_ascii=False, indent=2)
    (DATA / name).write_text(text + "\n", encoding="utf-8")


def prune(feed: list[dict], seeds: list[str], cutoff: date) -> list[dict]:
    """Drop cards added before `cutoff`. Seed cards stay while they are in the config."""

    def keep(card: dict) -> bool:
        if card["seed"]:
            return card["id"] in seeds
        return card["added"] >= cutoff.isoformat()

    return [card for card in feed if keep(card)]


def entry(
    paper: fetch.Paper,
    card: llm.Card,
    today: date,
    *,
    tier: str,
    reason: str,
    score: int | None = None,
    seed: bool = False,
) -> dict:
    return {
        "id": paper.id,
        "url": paper.url,
        "title": paper.title,
        "authors": paper.authors,
        "published": paper.published.date().isoformat(),
        "categories": paper.categories,
        "abstract": paper.abstract,
        "added": today.isoformat(),
        "seed": seed,
        "tier": tier,
        "score": score,
        "reason": reason,
        "card": card.model_dump(),
    }


def update(cfg: dict, dry_run: bool = False) -> None:
    """Screen the new papers, write today's cards and save both data files."""
    client = anthropic.Anthropic(max_retries=5)
    now = datetime.now(UTC)
    today = now.date()
    lookback = timedelta(days=cfg["lookback_days"])

    old_feed = load("feed.json", {"cards": []})["cards"]
    old_screened = load("screened.json", {})
    feed = prune(old_feed, cfg["seeds"], today - timedelta(days=cfg["keep_days"]))
    # arXiv can return a paper for as long as the lookback window, so a verdict
    # has to be remembered a little longer than that.
    oldest = (today - lookback - timedelta(days=1)).isoformat()
    screened = {i: s for i, s in old_screened.items() if s["date"] >= oldest}
    in_feed = {card["id"] for card in feed}
    known = in_feed | set(cfg["seeds"])

    log.info("fetching the last %d days from arXiv", cfg["lookback_days"])
    seeds = fetch.by_ids(cfg["seeds"])
    reading_list = [seed.title for seed in seeds]
    papers = {paper.id: paper for paper in fetch.recent(cfg["queries"], now - lookback)}
    if not papers:
        raise RuntimeError("arXiv returned no recent papers")
    fresh = [p for p in papers.values() if p.id not in screened and p.id not in known]

    log.info("screening %d new papers out of %d", len(fresh), len(papers))
    # A few requests at a time: the first run has a whole week to get through.
    with ThreadPoolExecutor(max_workers=3) as pool:
        verdicts = pool.map(lambda paper: llm.screen(client, paper, reading_list, cfg), fresh)
        for paper, verdict in zip(fresh, verdicts, strict=True):
            if verdict:
                record = {"date": today.isoformat(), "title": paper.title, **verdict.model_dump()}
                screened[paper.id] = record
                log.info("%-6s %2d  %s", verdict.tier, verdict.score, paper.title[:90])

    def waiting(tier: str) -> list[str]:
        """Recent papers of this tier that score high enough and have no card, best first."""
        ids = [
            i
            for i in papers
            if i not in known
            and screened.get(i, {}).get("tier") == tier
            and screened[i]["score"] >= cfg["min_score"]
        ]
        # On equal scores, the paper that has waited longest goes first.
        return sorted(ids, key=lambda i: (-screened[i]["score"], screened[i]["date"]))

    def room(tier: str) -> int:
        added = sum(
            c["added"] == today.isoformat() and c["tier"] == tier and not c["seed"] for c in feed
        )
        return max(cfg["per_day"][tier] - added, 0)

    if dry_run:
        picks = [i for tier in TIERS for i in waiting(tier)[: room(tier)]]
        print(f"\n{len(picks)} papers would get a card today:\n")
        for i in picks:
            v = screened[i]
            print(f"{v['tier']:6} {v['score']:2}  {i}  {papers[i].title[:70]}")
            print(f"{'':11}{v['reason']}")
        return

    new = []
    for seed in seeds:
        if seed.id in in_feed:
            continue
        reason = "It is on the reader's reading list."
        card = llm.write_card(client, seed, "thesis", reason, reading_list, cfg)
        if card:
            new.append(entry(seed, card, today, tier="thesis", reason=reason, seed=True))

    # A paper whose card fails stays in the queue and is tried again on the next run.
    for tier in TIERS:
        left = room(tier)
        for i in waiting(tier):
            if left == 0:
                break
            v = screened[i]
            card = llm.write_card(client, papers[i], tier, v["reason"], reading_list, cfg)
            if card:
                new.append(
                    entry(papers[i], card, today, tier=tier, reason=v["reason"], score=v["score"])
                )
                left -= 1

    feed = new + feed
    if feed != old_feed:
        save("feed.json", {"updated": now.isoformat(timespec="seconds"), "cards": feed})
    if screened != old_screened:
        save("screened.json", screened)
    log.info("%d new cards, %d in the feed", len(new), len(feed))
