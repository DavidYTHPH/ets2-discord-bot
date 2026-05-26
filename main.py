import discord
from discord.ext import tasks, commands
import asyncio
import os
import re
import requests

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
# Target the direct raw log endpoint on your assettohosting server
LOGS_URL = "https://de4.assettohosting.com:60081/logs"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

last_known_id = None

def fetch_convoy_id():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(LOGS_URL, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"Failed to fetch logs page. Status: {response.status_code}")
            return None
            
        # Search the server logs text for the standard ETS2 Search ID format (digits/digits)
        match = re.search(r"(\d{14,19}/\d{2,3})", response.text)
        if match:
            return match.group(1)
            
        fallback_match = re.search(r"(\d+/\d+)", response.text)
        if fallback_match:
            return fallback_match.group(1)
            
        return None
    except Exception as e:
        print(f"Log parser error: {e}")
        return None

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    if not check_server_id.is_running():
        check_server_id.start()

@tasks.loop(seconds=60)
async def check_server_id():
    global last_known_id
    if CHANNEL_ID == 0:
        return
        
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    current_id = fetch_convoy_id()
    print(f"Log Scan Result: {current_id}")
    
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        embed = discord.Embed(
            title="🚚 ETS2 Server Updated / Restarted!",
            description=f"AssettoHosting has generated a new Search ID for the lobby.\n\n**Search ID:** `{current_id}`",
            color=discord.Color.orange()
        )
        embed.set_footer(text="Auto-extracted from Live Server Logs")
        await channel.send(embed=embed)

bot.run(TOKEN)
