# Dev News Bot

A Discord bot that aggregates developer news from RSS feeds (Hacker News, DEV Community, daily.dev, Product Hunt) and posts them automatically to a Discord channel (and optionally Slack).

## Features

- **RSS aggregation** from Hacker News, DEV Community, daily.dev, Product Hunt
- **Discord embeds** with title, link, description, and source
- **Optional Slack** posting via webhook URLs
- **Deduplication** via `seen.json` (keeps last ~2000 IDs)
- **Round-robin batching**: 2 posts per run, max 3 per source
- **Scheduled polling** every `POLL_HOURS` (default 3)

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
   This sends a test message to your channel. If it succeeds, the bot can connect and post.

2. **Run the bot locally** (optional dry run):
   ```bash
   python3 bot.py
   ```
   You should see:
   - `✓ Logged in as <BotName>`
   - `✓ Watching 4 feeds`
   - Within a few seconds, either `[Posted] ...` or `[Info] No new items to post`
   Press Ctrl+C to stop.

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
python3 bot.py
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
   - `POLL_HOURS` (optional, default `3`)
   - `SLACK_WEBHOOK_URLS` (optional, comma-separated)
3. The named volume `dev-news-bot-data` persists `seen.json` across restarts

**Behavior in Docker:**
- `restart: unless-stopped` keeps it running 24/7
- No inbound ports; bot only makes outbound requests
- State is stored in a Docker volume (`dev-news-bot-data` → `/data/seen.json`)

## License

_To be determined_
