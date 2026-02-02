import os
import sys

# If run with system python, re-exec with project .venv so dependencies are found
if not (getattr(sys, "base_prefix", sys.prefix) != sys.prefix):
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
    if os.path.isfile(venv_python):
        os.execv(venv_python, [venv_python] + sys.argv)

import json
import asyncio
import re
from typing import Dict, List, Set, Tuple
from html import unescape

import aiohttp
import feedparser
import discord
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
POLL_HOURS = float(os.getenv("POLL_HOURS", "3"))

# Comma-separated Slack incoming webhooks (one per channel is typical).
# Example: SLACK_WEBHOOK_URLS="https://hooks.slack.com/services/AAA/BBB/CCC,https://hooks.slack.com/services/DDD/EEE/FFF"
SLACK_WEBHOOK_URLS = [
    u.strip() for u in os.getenv("SLACK_WEBHOOK_URLS", "").split(",") if u.strip()
]

# Swapped feeds: Hacker News, DEV Community, daily.dev, Product Hunt.
FEEDS: List[Tuple[str, str]] = [
    ("Hacker News (Front Page)", "https://hnrss.org/frontpage"),
    # Alternative HN feeds if you want them:
    # ("Hacker News (Newest)", "https://hnrss.org/newest"),
    # ("Hacker News (Show HN)", "https://hnrss.org/show"),
    ("DEV Community (dev.to)", "https://dev.to/feed"),
    ("daily.dev (Blog)", "https://daily.dev/blog/rss.xml"),
    ("Product Hunt (Main)", "https://www.producthunt.com/feed"),
]

SEEN_PATH = "seen.json"
MAX_POSTS_PER_RUN = 2  # Post items from all feeds in each batch
MAX_PER_SOURCE = 3  # Max items per source per batch

intents = discord.Intents.default()  # posting only; no message-content needed
client = discord.Client(intents=intents)


def load_seen() -> Set[str]:
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()
    except Exception:
        return set()


def save_seen(seen: Set[str]) -> None:
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(seen)[-2000:], f)  # keep last ~2000 IDs


async def fetch_feed(session: aiohttp.ClientSession, name: str, url: str) -> List[Dict]:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
        resp.raise_for_status()
        data = await resp.read()

    parsed = feedparser.parse(data)
    items = []
    for entry in parsed.entries:
        link = entry.get("link")
        title = entry.get("title", "(no title)")
        uid = entry.get("id") or entry.get("guid") or link  # fall back to link
        if not uid or not link:
            continue
        
        # Extract description/summary from feed entry
        description = entry.get("summary") or entry.get("description") or ""
        # Clean HTML tags and decode HTML entities
        if description:
            # Remove HTML tags
            description = re.sub(r'<[^>]+>', '', description)
            # Decode HTML entities
            description = unescape(description)
            # Clean up whitespace
            description = re.sub(r'\s+', ' ', description).strip()
            # Limit length for Discord embed (max 4096 chars, but we'll use 500 for readability)
            if len(description) > 500:
                description = description[:497] + "..."
        
        items.append(
            {
                "source": name,
                "uid": str(uid),
                "title": str(title),
                "link": str(link),
                "description": description,
            }
        )
    return items


def to_embed(item: Dict) -> discord.Embed:
    embed = discord.Embed(title=item["title"], url=item["link"])
    
    # Add description if available
    description = item.get("description", "")
    if description:
        embed.description = description
    else:
        embed.description = f"Read more from {item['source']}"
    
    embed.set_footer(text=item["source"])
    return embed


async def post_to_slack(session: aiohttp.ClientSession, item: Dict) -> None:
    if not SLACK_WEBHOOK_URLS:
        return

    text = f"*{item['title']}*\n{item['link']}\n_{item['source']}_"
    payload = {"text": text, "unfurl_links": True, "unfurl_media": True}

    for webhook_url in SLACK_WEBHOOK_URLS:
        try:
            async with session.post(
                webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    print(f"[Slack] Webhook error {resp.status}: {body[:200]}")
        except Exception as e:
            print(f"[Slack] Post failed: {e}")


@tasks.loop(hours=POLL_HOURS)
async def poll_and_post():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        channel = await client.fetch_channel(CHANNEL_ID)

    seen = load_seen()

    headers = {
        # Some feeds are picky; a browser-like UA reduces random 403/400s.
        "User-Agent": "Mozilla/5.0 (compatible; dev-news-bot/1.0; +https://example.com/bot)"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        results = await asyncio.gather(
            *(fetch_feed(session, name, url) for name, url in FEEDS),
            return_exceptions=True,
        )

        # Group items by source
        items_by_source: Dict[str, List[Dict]] = {}
        
        for i, res in enumerate(results):
            source_name = FEEDS[i][0]
            if isinstance(res, Exception):
                print(f"[Error] Feed fetch failed for {source_name}: {res}")
                items_by_source[source_name] = []
                continue
            
            source_items = []
            for item in res:
                if item["uid"] not in seen:
                    source_items.append(item)
            items_by_source[source_name] = source_items

    # Distribute items from all sources in round-robin fashion
    new_items: List[Dict] = []
    source_indices = {source: 0 for source in items_by_source.keys()}
    
    # Round-robin: take up to MAX_PER_SOURCE from each source
    while len(new_items) < MAX_POSTS_PER_RUN:
        added_any = False
        for source_name in items_by_source.keys():
            if len(new_items) >= MAX_POSTS_PER_RUN:
                break
            source_items = items_by_source[source_name]
            idx = source_indices[source_name]
            
            # Take items from this source (up to MAX_PER_SOURCE per source)
            items_taken = 0
            while idx < len(source_items) and items_taken < MAX_PER_SOURCE and len(new_items) < MAX_POSTS_PER_RUN:
                new_items.append(source_items[idx])
                idx += 1
                items_taken += 1
                added_any = True
            source_indices[source_name] = idx
        
        # If we didn't add any items, break to avoid infinite loop
        if not added_any:
            break

    if not new_items:
        print("[Info] No new items to post")
        return

    # Post to Discord
    for item in new_items:
        try:
            embed = to_embed(item)
            await channel.send(embed=embed)
            seen.add(item["uid"])
            print(f"[Posted] {item['source']}: {item['title'][:50]}...")
        except Exception as e:
            print(f"[Error] Failed to post {item['title'][:50]}: {e}")

    # Post to Slack (if configured)
    if SLACK_WEBHOOK_URLS:
        async with aiohttp.ClientSession(headers=headers) as session:
            for item in new_items:
                await post_to_slack(session, item)

    save_seen(seen)


@client.event
async def on_ready():
    print(f"✓ Logged in as {client.user}")
    print(f"✓ Watching {len(FEEDS)} feeds")
    poll_and_post.start()


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN not set in .env")
        exit(1)
    if CHANNEL_ID == 0:
        print("ERROR: CHANNEL_ID not set in .env")
        exit(1)
    client.run(DISCORD_TOKEN)
