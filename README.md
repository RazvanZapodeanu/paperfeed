# paperfeed

A daily shortlist of new arXiv papers, picked for what I'm working on and turned
into short study cards I can read on my phone.

## How it works

1. Fetch the last 7 days of papers from a few arXiv categories.
2. A small model (Claude Haiku) reads every new abstract next to a description of
   my thesis and my reading list, and sorts the paper into one of three tiers:
   `thesis`, `field` or `skip`, with a score from 1 to 10.
3. Each day the best papers of the first two tiers get a card written by a larger
   model (Claude Sonnet): what the paper did, how it was evaluated, what I can do
   with it, and one concept explained properly. Papers under a minimum score never
   get a card, and papers over the daily limit wait for a later day while they are
   still recent.
4. A GitHub Actions job runs this twice a day and commits `feed.json` to the `data`
   branch. `screened.json` next to it keeps the verdict for every paper, so nothing
   is screened twice and I can check what was left out and why.

Everything that decides what ends up in the feed is in `config.toml`.

## Setup

Needs Python 3.11 or newer.

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

## Usage

Both commands need an Anthropic API key in `ANTHROPIC_API_KEY`.

```
python -m paperfeed --dry-run    # screen and print today's picks, write nothing
python -m paperfeed              # write the cards to data/feed.json
pytest
```

The scheduled job reads the key from a repository secret with the same name, and
expects an empty `data` branch to commit to:

```
git switch --orphan data
git commit --allow-empty -m "Start the data branch"
git push origin data
git switch main
git branch -D data
```
