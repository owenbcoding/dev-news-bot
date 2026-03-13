# Dev News Bot

A bot that automatically posts daily developer news from various platforms.

## Overview

This bot collects and posts the latest developer news from multiple sources, keeping developers informed about the latest trends, updates, and happenings in the tech world.

## Features

- Aggregates news from various developer platforms
- Posts daily updates automatically
- Curates relevant content for developers

## Setup

1. Clone this repository
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate  # On Linux/Mac
   # or
   .venv\Scripts\activate  # On Windows
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Run manually
```bash
python3 bot.py
# or
./run
```

### Run with PM2 (recommended on Pi)
The bot is configured to run under PM2 and **auto-start when the Pi boots**.

- **Start the bot:** `pm2 start ecosystem.config.cjs`
- **Stop:** `pm2 stop dev-news-bot`
- **Restart:** `pm2 restart dev-news-bot`
- **Logs:** `pm2 logs dev-news-bot`
- **Status:** `pm2 status`

After changing the process list (start/stop apps), run `pm2 save` so it persists across reboots. Startup on boot is already enabled via `pm2 startup`.

### Run with Docker (Raspberry Pi / Portainer)

The image is multi-arch (ARM64/ARMv7) and works on Raspberry Pi.

**Local (docker compose):**

```bash
cp .env.example .env   # edit with your DISCORD_TOKEN and CHANNEL_ID
docker compose build && docker compose up -d
```

**Portainer:**

1. In Portainer, create a new **Stack** (or use **App Templates** and paste the compose).
2. Build and deploy from this repo (clone URL or upload `Dockerfile` + `docker-compose.yml` + `bot.py` + `requirements.txt`).
3. Add environment variables in the stack:
   - `DISCORD_TOKEN` (required)
   - `CHANNEL_ID` (required)
   - `POLL_HOURS` (optional, default `3`)
   - `SLACK_WEBHOOK_URLS` (optional, comma-separated webhook URLs)
4. The stack uses a named volume `dev-news-bot-data` for `seen.json` so state persists across restarts.

No port mapping is needed; the bot only makes outbound requests.

## License

_To be determined_
