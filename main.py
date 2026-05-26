import discord
from discord.ext import tasks, commands
import asyncio
import os
import re
import requests

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
PANEL_URL = "https://de4.assettohosting.com:60081/server-control"
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

last_known_id = None

def fetch_convoy_id():
    try:
        # Pretend to be a normal browser request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        print(f"Requesting panel HTML from: {PANEL_URL}")
        response = requests.get(PANEL_URL, headers=headers, timeout=15)
        
        # Log the status code to see if it's blocking us
        print(f"Panel response status code: {response.status_code}")
        
        html_text = response.text
        
        # Look for the classic Euro Truck Simulator 2 convoy ID format (e.g., 12345678901234567/101)
        # It's usually a long string of digits followed by a slash and 2-3 digits
        match = re.search(r"(\d{14,19}/\d{2,3})", html_text)
        if match:
            return match.group(1)
            
        # Fallback broad match for any 'digits/digits' format just in case
        fallback_match = re.search(r"(\d+/\d+)", html_text)
        if fallback_match:
            return fallback_match.group(1)
            
        return None
    except Exception as e:
        print(f"Scraping error: {e}")
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
        print("Error: DISCORD_CHANNEL_ID environment variable is missing.")
        return
        
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Error: Cannot find channel with ID {CHANNEL_ID}")
        return

    current_id = fetch_convoy_id()
    print(f"Scraped Convoy ID Result: {current_id}")
    
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        embed = discord.Embed(
            title="🚚 ETS2 Server Updated / Restarted!",
            description=f"AssettoHosting has generated a new Search ID for the lobby.\n\n**Search ID:** `{current_id}`",
            color=discord.Color.orange()
        )
        embed.set_footer(text="Auto-detected from AssettoHosting Panel")
        await channel.send(embed=embed)

bot.run(TOKEN)
