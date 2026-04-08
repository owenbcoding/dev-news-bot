import os
import sys
from typing import List, Tuple

# If run with system python, re-exec with project .venv so dependencies are found.
if not (getattr(sys, "base_prefix", sys.prefix) != sys.prefix):
    venv_python = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python"
    )
    if os.path.isfile(venv_python):
        os.execv(venv_python, [venv_python] + sys.argv)

from dotenv import load_dotenv

from news_core import NewsBotConfig, env_flag, run_news_bot

load_dotenv()


FEEDS: List[Tuple[str, str]] = [
    ("Hacker News (Front Page)", "https://hnrss.org/frontpage"),
    ("DEV Community (dev.to)", "https://dev.to/feed"),
    ("daily.dev (Blog)", "https://daily.dev/blog/rss.xml"),
    ("Product Hunt (Main)", "https://www.producthunt.com/feed"),
]


def build_config() -> NewsBotConfig:
    return NewsBotConfig(
        bot_name="dev-news-bot",
        discord_token=os.getenv("DISCORD_TOKEN", ""),
        channel_id=int(os.getenv("DEV_CHANNEL_ID") or os.getenv("CHANNEL_ID", "0")),
        feeds=FEEDS,
        archive_path=os.getenv("ARCHIVE_PATH", "data/dev_news_archive.jsonl"),
        dedupe_index_path=os.getenv("DEDUPE_INDEX_PATH", "data/dev_news_dedupe.json"),
        max_posts_per_run=int(os.getenv("MAX_POSTS_PER_RUN", "8")),
        max_per_source=int(os.getenv("MAX_PER_SOURCE", "2")),
        send_text_digest=env_flag("SEND_TEXT_DIGEST", default=False),
    )


def main() -> None:
    run_news_bot(build_config())


if __name__ == "__main__":
    main()
