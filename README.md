# Dev News Bot

A Discord bot that aggregates developer news from RSS feeds and posts them to Discord using a shared pipeline that can be reused by other news bots with different feed lists and channel IDs.

## Features

- **RSS aggregation** from Hacker News, DEV Community, daily.dev, Product Hunt
- **Shared pipeline** in `news_core.py` for fetch, URL normalization, dedupe, archive, and formatting
- **Discord embeds** with clickable title, cleaned summary, explicit `Read article` field, and source/date footer
- **Deduplication** via `sha256(canonical_url)` instead of feed GUIDs
- **Persistent archive** in append-only `.jsonl` format with full posted history
- **Slash command** `/latestlinks` to show recent saved links from the archive
- **Round-robin batching**: 8 posts per run, 2 per source (4 feeds)
- **Scheduled posting** twice daily at `09:00 UTC` and `17:00 UTC`

## Project Structure

- `news_core.py`: shared logic for fetching feeds, normalizing URLs, dedupe, storage, embed formatting, and Discord command handling
- `dev_news_bot.py`: dev-news-specific feed list and environment-driven config
- `bot.py`: compatibility shim that runs `dev_news_bot.py`

## Quick Setup

1. Clone and configure:
   ```bash
   cp .env.example .env
   # Edit .env with your DISCORD_TOKEN and CHANNEL_ID
   ```

2. See [Verifying the Bot](#verifying-the-bot) before running 24/7.

## Verifying the Bot

Before running 24/7, verify the bot works correctly:

1. **Test Discord posting** (requires `.env` with valid `DISCORD_TOKEN` and `CHANNEL_ID`):
   ```bash
   python3 test_post.py
   ```
   This sends a test embed to your channel. If it succeeds, the bot can connect and post.

2. **Run the bot locally** (optional dry run):
   ```bash
   python3 dev_news_bot.py
   ```
   You should see:
   - `✓ Logged in as <BotName>`
   - `✓ Watching 4 feeds`
   - `✓ Scheduled posts at 09:00 UTC and 17:00 UTC`
   The bot will wait until the next scheduled run time before posting. Press Ctrl+C to stop.

## Setup (Local Development)

1. Clone this repository
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/Mac
   # or  .venv\Scripts\activate  # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure `.env` (see `.env.example`)

## Usage

### Run manually
```bash
python3 dev_news_bot.py
# or
./run
```

### Run with PM2 (on Pi, no Docker)
- **Start:** `pm2 start ecosystem.config.cjs`
- **Stop:** `pm2 stop dev-news-bot`
- **Logs:** `pm2 logs dev-news-bot`
- Run `pm2 save` after changes so it persists across reboots.

### Run with Docker (Raspberry Pi 24/7)

The image is ARM-compatible and works on Raspberry Pi 4/5 (64-bit) and Pi 3/Zero 2 W.

**On the Pi:**

```bash
# 1. Clone and configure
git clone <your-repo-url> dev-news-bot
cd dev-news-bot
cp .env.example .env
nano .env   # set DISCORD_TOKEN and CHANNEL_ID

# 2. Build and run
docker compose build && docker compose up -d

# 3. Check logs
docker compose logs -f dev-news-bot
```

**Using Portainer:**

1. Create a new **Stack** from this repo
2. Add environment variables in the stack:
   - `DISCORD_TOKEN` (required)
   - `CHANNEL_ID` (required)
   - `DEV_CHANNEL_ID` (optional override for dev bot channel)
   - `ARCHIVE_PATH` (optional, default `/data/dev_news_archive.jsonl`)
   - `DEDUPE_INDEX_PATH` (optional, default `/data/dev_news_dedupe.json`)
   - `SEND_TEXT_DIGEST` (optional, default `false`)
3. The named volume `dev-news-bot-data` persists the archive and dedupe index across restarts

**Behavior in Docker:**
- `restart: unless-stopped` keeps it running 24/7
- Posts are sent automatically at `09:00 UTC` and `17:00 UTC`
- No inbound ports; bot only makes outbound requests
- State is stored in a Docker volume:
  - archive at `/data/dev_news_archive.jsonl`
  - dedupe index at `/data/dev_news_dedupe.json`

## Stored Article Fields

Each successfully posted article is saved with:

- `source`
- `title`
- `url`
- `canonical_url`
- `published_at`
- `posted_at`
- `discord_message_id`

## License

_To be determined_
