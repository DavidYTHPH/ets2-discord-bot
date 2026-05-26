import discord
from discord.ext import tasks, commands
import asyncio
import os
import re
import requests

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
LOGS_URL = "https://de4.assettohosting.com:60081/logs"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

last_known_id = None
has_posted_initial = False

def fetch_convoy_id():
    try:
        # Emulate a standard browser frame header connection
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        
        response = requests.get(LOGS_URL, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Panel connection refused or shifted. HTTP Status: {response.status_code}")
            return None
            
        html_text = response.text
        
        # 1. Primary Regex Pattern Match (Traditional ETS2/ATS Convoy formatting)
        match = re.search(r"(\d{14,19}/\d{2,3})", html_text)
        if match:
            return match.group(1)
            
        # 2. Secondary Broad Match (Catches any numerical ID patterns isolated by slashes)
        fallback_match = re.search(r"(\d+/\d+)", html_text)
        if fallback_match:
            return fallback_match.group(1)
            
        return None
    except Exception as e:
        print(f"Log parser thread error: {e}")
        return None

@bot.event
async def on_ready():
    print(f"Bot successfully registered on gateway. Online as: {bot.user}")
    if not check_server_id.is_running():
        print("Initializing monitoring task loop...")
        check_server_id.start()

@tasks.loop(seconds=60)
async def check_server_id():
    global last_known_id, has_posted_initial
    print("--- Executing Log Frame Check ---")
    
    if CHANNEL_ID == 0:
        print("Configuration Error: DISCORD_CHANNEL_ID key value is empty or 0.")
        return
        
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Channel Error: Text channel ID {CHANNEL_ID} couldn't be retrieved.")
        return

    # Offload the synchronous HTTP scraper to a separate process thread to protect the gateway connection
    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    print(f"Active Scraped Target Output: {current_id}")
    
    # CASE A: A fresh Convoy Search ID string was discovered in the read-out
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        has_posted_initial = True
        
        embed = discord.Embed(
            title="🚚 Euro Truck Simulator 2 Server Online!",
            description=f"A new Search ID has been successfully detected.\n\n**Search ID:** `{current_id}`",
            color=discord.Color.green()
        )
        embed.set_footer(text="Auto-extracted from AssettoHosting Console Stream")
        await channel.send(embed=embed)
        
    # CASE B: The server is open, but the terminal log frame doesn't contain the initial boot-up text lines anymore
    elif not current_id and not has_posted_initial:
        has_posted_initial = True
        
        embed = discord.Embed(
            title="🚚 ETS2 Lobby Monitor Connected",
            description=(
                f"The bot is officially connected and reading your server panel.\n\n"
                f"⚠️ *Note: If the Search ID has already scrolled away from the live terminal frame buffer, "
                f"it will automatically populate right here the next time the server undergoes a **Restart**.*"
            ),
            color=discord.Color.blue()
        )
        embed.add_field(name="🔗 Quick Actions", value=f"[Open Live Server Panel Logs]({LOGS_URL})", inline=False)
        await channel.send(embed=embed)

bot.run(TOKEN)
