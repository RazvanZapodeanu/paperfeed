import argparse
import logging
import os
import sys

from . import pipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="paperfeed", description="Build the paper feed.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="screen the new papers and print today's picks, without writing cards or files",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")

    logging.basicConfig(format="%(message)s")
    logging.getLogger("paperfeed").setLevel(logging.INFO)

    pipeline.update(pipeline.load_config(), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
