import discord
from discord.ext import tasks, commands
import asyncio
import os
import re
import requests

# --- CONFIGURATION ---
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
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(LOGS_URL, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return None
            
        html_text = response.text
        
        # Search for the standard ETS2 Search ID format (e.g., 12345678901234567/101)
        match = re.search(r"(\d{14,19}/\d{2,3})", html_text)
        if match:
            return match.group(1)
            
        fallback_match = re.search(r"(\d+/\d+)", html_text)
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
    global last_known_id, has_posted_initial
    
    if CHANNEL_ID == 0:
        return
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    print(f"Log Scan Result: {current_id}")
    
    # Scenario A: The bot found the ID in the console stream
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        has_posted_initial = True
        embed = discord.Embed(
            title="🚚 ETS2 Server Online!",
            description=f"A fresh Search ID has been detected in the console logs.\n\n**Search ID:** `{current_id}`",
            color=discord.Color.green()
        )
        embed.set_footer(text="Auto-extracted from Live Server Logs")
        await channel.send(embed=embed)
        
    # Scenario B: The server is running but the ID has scrolled out of view
    elif not current_id and not has_posted_initial:
        has_posted_initial = True # Only alert once per startup so it doesn't spam
        embed = discord.Embed(
            title="🚚 ETS2 Server Monitor Active",
            description=f"The server is currently running, but the startup Search ID has scrolled out of the console memory buffer.\n\n🔗 **[Click here to view live server log stream]({LOGS_URL})** to grab the ID manually, or trigger a server restart to republish it here automatically!",
            color=discord.Color.orange()
        )
        await channel.send(embed=embed)

bot.run(TOKEN)
