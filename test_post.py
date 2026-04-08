#!/usr/bin/env python3
"""Test script to manually trigger a post to Discord"""
import asyncio
import os
import sys
from dotenv import load_dotenv
import discord

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DEV_CHANNEL_ID") or os.getenv("CHANNEL_ID", "0"))

if not DISCORD_TOKEN or CHANNEL_ID == 0:
    print("ERROR: Missing DISCORD_TOKEN or CHANNEL_ID in .env")
    sys.exit(1)

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✓ Logged in as {client.user}")
    try:
        channel = await client.fetch_channel(CHANNEL_ID)
        print(f"✓ Fetched channel: {channel.name}")
        
        embed = discord.Embed(
            title="Test Post - Dev News Bot",
            url="https://example.com/dev-news-bot",
            description="This is a test embed to verify the bot can post article-style messages.",
        )
        embed.add_field(
            name="Read article",
            value="https://example.com/dev-news-bot",
            inline=False,
        )
        embed.set_footer(text="dev-news-bot | test message")

        await channel.send(embed=embed)
        print("✓ Test embed sent successfully!")
        
    except discord.NotFound:
        print(f"ERROR: Channel {CHANNEL_ID} not found")
    except discord.Forbidden:
        print("ERROR: Missing permissions to post in this channel")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await client.close()

try:
    client.run(DISCORD_TOKEN)
except KeyboardInterrupt:
    print("\nInterrupted")
