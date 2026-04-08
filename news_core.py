import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp
import discord
import feedparser
from discord import app_commands
from discord.ext import tasks


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; dev-news-bot/2.0; +https://example.com/bot)"
}

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}


@dataclass(frozen=True)
class NewsBotConfig:
    bot_name: str
    discord_token: str
    channel_id: int
    feeds: Sequence[Tuple[str, str]]
    archive_path: str
    dedupe_index_path: str
    max_posts_per_run: int = 8
    max_per_source: int = 2
    send_text_digest: bool = False


UTC_POST_TIMES = (
    time(hour=9, tzinfo=timezone.utc),
    time(hour=17, tzinfo=timezone.utc),
)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")

    filtered_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith(TRACKING_QUERY_PREFIXES):
            continue
        if lowered in TRACKING_QUERY_KEYS:
            continue
        filtered_query.append((key, value))

    query = urlencode(sorted(filtered_query), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def canonical_hash(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()


def clean_summary(value: str, limit: int = 500) -> str:
    if not value:
        return ""

    cleaned = re.sub(r"<[^>]+>", "", value)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > limit:
        return cleaned[: limit - 3].rstrip() + "..."
    return cleaned


def to_iso_datetime(entry: feedparser.FeedParserDict) -> Optional[str]:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc).isoformat()

    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            continue

    return None


def load_dedupe_index(path: str) -> Dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return {}


def save_dedupe_index(path: str, entries: Dict[str, str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2, sort_keys=True)


def append_archive_entry(path: str, article: Dict[str, str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(article, ensure_ascii=True) + "\n")


def read_archive(path: str) -> List[Dict[str, str]]:
    archive_path = Path(path)
    if not archive_path.exists():
        return []

    entries: List[Dict[str, str]] = []
    with open(archive_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
    return entries


def build_dedupe_index_from_archive(path: str) -> Dict[str, str]:
    rebuilt: Dict[str, str] = {}
    for entry in read_archive(path):
        canonical_url = entry.get("canonical_url")
        if not canonical_url:
            continue
        rebuilt[canonical_hash(str(canonical_url))] = str(canonical_url)
    return rebuilt


async def fetch_feed(
    session: aiohttp.ClientSession, source_name: str, feed_url: str
) -> List[Dict[str, Optional[str]]]:
    async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=25)) as response:
        response.raise_for_status()
        data = await response.read()

    parsed = feedparser.parse(data)
    items: List[Dict[str, Optional[str]]] = []
    for entry in parsed.entries:
        url = entry.get("link")
        title = str(entry.get("title", "(no title)")).strip()
        if not url or not title:
            continue

        canonical_url = normalize_url(str(url))
        items.append(
            {
                "source": source_name,
                "title": title,
                "url": str(url),
                "canonical_url": canonical_url,
                "canonical_hash": canonical_hash(canonical_url),
                "published_at": to_iso_datetime(entry),
                "summary": clean_summary(
                    str(entry.get("summary") or entry.get("description") or "")
                ),
            }
        )
    return items


def select_round_robin(
    items_by_source: Dict[str, List[Dict[str, Optional[str]]]],
    max_posts_per_run: int,
    max_per_source: int,
) -> List[Dict[str, Optional[str]]]:
    selected: List[Dict[str, Optional[str]]] = []
    source_indices = {source: 0 for source in items_by_source}

    while len(selected) < max_posts_per_run:
        added_any = False
        for source_name, source_items in items_by_source.items():
            if len(selected) >= max_posts_per_run:
                break

            idx = source_indices[source_name]
            taken = 0
            while idx < len(source_items) and taken < max_per_source:
                selected.append(source_items[idx])
                idx += 1
                taken += 1
                added_any = True
                if len(selected) >= max_posts_per_run:
                    break
            source_indices[source_name] = idx

        if not added_any:
            break

    return selected


def build_embed(article: Dict[str, Optional[str]]) -> discord.Embed:
    embed = discord.Embed(
        title=article["title"] or "(no title)",
        url=article["url"] or article["canonical_url"] or "",
        description=article.get("summary") or f"Read more from {article['source']}",
    )
    embed.add_field(
        name="Read article",
        value=article["url"] or article["canonical_url"] or "No URL available",
        inline=False,
    )

    published_at = article.get("published_at")
    footer_bits = [str(article["source"])]
    if published_at:
        footer_bits.append(format_footer_date(str(published_at)))
    embed.set_footer(text=" | ".join(footer_bits))
    return embed


def format_footer_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return value


def build_digest_message(articles: Sequence[Dict[str, Optional[str]]]) -> str:
    lines = ["Latest links:"]
    for article in articles:
        lines.append(f"- {article['title']} - {article['url']}")
    return "\n".join(lines)


class NewsBotClient(discord.Client):
    def __init__(self, config: NewsBotConfig) -> None:
        super().__init__(intents=discord.Intents.default())
        self.config = config
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        @self.tree.command(
            name="latestlinks",
            description="Show the most recent links saved in the archive.",
        )
        @app_commands.describe(count="How many recent links to show (1-10).")
        async def latestlinks(interaction: discord.Interaction, count: int = 5) -> None:
            count = max(1, min(count, 10))
            entries = read_archive(self.config.archive_path)[-count:]
            if not entries:
                await interaction.response.send_message(
                    "No archived links have been posted yet.",
                    ephemeral=True,
                )
                return

            lines = []
            for entry in reversed(entries):
                lines.append(
                    f"{entry.get('title', '(no title)')}\n"
                    f"{entry.get('url', '')}\n"
                    f"{entry.get('source', 'Unknown source')}"
                )
            await interaction.response.send_message(
                "\n\n".join(lines),
                ephemeral=True,
            )

        await self.tree.sync()

    async def fetch_channel_or_fail(self) -> discord.abc.Messageable:
        channel = self.get_channel(self.config.channel_id)
        if channel is None:
            channel = await self.fetch_channel(self.config.channel_id)
        return channel

    @tasks.loop(time=UTC_POST_TIMES)
    async def poll_and_post(self) -> None:
        channel = await self.fetch_channel_or_fail()
        dedupe_index = load_dedupe_index(self.config.dedupe_index_path)
        if not dedupe_index:
            dedupe_index = build_dedupe_index_from_archive(self.config.archive_path)

        async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
            results = await asyncio.gather(
                *(fetch_feed(session, name, url) for name, url in self.config.feeds),
                return_exceptions=True,
            )

        items_by_source: Dict[str, List[Dict[str, Optional[str]]]] = {}
        for index, result in enumerate(results):
            source_name = self.config.feeds[index][0]
            if isinstance(result, Exception):
                print(f"[Error] Feed fetch failed for {source_name}: {result}")
                items_by_source[source_name] = []
                continue

            filtered = []
            for article in result:
                article_hash = str(article["canonical_hash"])
                if article_hash not in dedupe_index:
                    filtered.append(article)
            items_by_source[source_name] = filtered

        new_items = select_round_robin(
            items_by_source,
            max_posts_per_run=self.config.max_posts_per_run,
            max_per_source=self.config.max_per_source,
        )
        if not new_items:
            print(f"[Info] No new items to post for {self.config.bot_name}")
            return

        posted_items: List[Dict[str, Optional[str]]] = []
        for article in new_items:
            try:
                message = await channel.send(embed=build_embed(article))
                stored_article = {
                    "source": str(article["source"]),
                    "title": str(article["title"]),
                    "url": str(article["url"]),
                    "canonical_url": str(article["canonical_url"]),
                    "published_at": article.get("published_at"),
                    "posted_at": utc_now_iso(),
                    "discord_message_id": str(message.id),
                    "summary": str(article.get("summary") or ""),
                    "canonical_hash": str(article["canonical_hash"]),
                }
                append_archive_entry(self.config.archive_path, stored_article)
                dedupe_index[str(article["canonical_hash"])] = str(article["canonical_url"])
                posted_items.append(stored_article)
                print(f"[Posted] {article['source']}: {article['title'][:70]}")
            except Exception as exc:
                print(f"[Error] Failed to post {article['title'][:70]}: {exc}")

        if posted_items:
            save_dedupe_index(self.config.dedupe_index_path, dedupe_index)
            if self.config.send_text_digest:
                await channel.send(build_digest_message(posted_items))

    @poll_and_post.before_loop
    async def before_poll_and_post(self) -> None:
        await self.wait_until_ready()

    async def on_ready(self) -> None:
        print(f"✓ Logged in as {self.user}")
        print(f"✓ Watching {len(self.config.feeds)} feeds for {self.config.bot_name}")
        print("✓ Scheduled posts at 09:00 UTC and 17:00 UTC")
        if not self.poll_and_post.is_running():
            self.poll_and_post.start()


def run_news_bot(config: NewsBotConfig) -> None:
    if not config.discord_token:
        raise SystemExit("ERROR: DISCORD_TOKEN not set in environment")
    if config.channel_id == 0:
        raise SystemExit("ERROR: CHANNEL_ID or DEV_CHANNEL_ID not set in environment")
    client = NewsBotClient(config)
    client.run(config.discord_token)
