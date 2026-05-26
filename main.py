import discord
from discord.ext import tasks, commands
import asyncio
import os
import requests

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
# We target the exact backend JSON stats endpoint for port 60081
API_URL = "https://de4.assettohosting.com:60081/api/stats"
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

last_known_id = None

def fetch_convoy_id():
    try:
        # Use a generic browser identifier so the panel doesn't block the cloud request
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(API_URL, headers=headers, timeout=15)
        
        if response.status_code == 204 or response.status_code == 401:
            print("Panel returned auth/empty status. Retrying via general scrape...")
            return None
            
        # Try to parse the panel's direct data values
        data = response.json()
        
        # Check standard game panel API keys for the lobby search ID
        search_id = data.get("searchId") or data.get("search_id") or data.get("convoyId")
        if search_id:
            return str(search_id)
            
        # Fallback: check nested server status info if present
        server_info = data.get("server", {}) or data.get("status", {})
        search_id = server_info.get("searchId") or server_info.get("search_id")
        if search_id:
            return str(search_id)
            
        return None
    except Exception as e:
        print(f"Error reading API endpoint: {e}")
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
        print("Error: DISCORD_CHANNEL_ID is missing.")
        return
        
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Error: Cannot find channel {CHANNEL_ID}")
        return

    current_id = fetch_convoy_id()
    print(f"API Check Result: {current_id}")
    
    # If API fails or is protected, fallback to alternative endpoint parsing
    if not current_id:
        try:
            # Alternate fallback to read general control string data directly
            alt_res = requests.get("https://de4.assettohosting.com:60081/server-control", timeout=15)
            import re
            match = re.search(r"(\d+/\d+)", alt_res.text)
            if match:
                current_id = match.group(1)
                print(f"Fallback Regex Scraped ID: {current_id}")
        except:
            pass

    if current_id and current_id != last_known_id:
        last_known_id = current_id
        embed = discord.Embed(
            title="🚚 ETS2 Server Updated / Restarted!",
            description=f"AssettoHosting has generated a new Search ID for the lobby.\n\n**Search ID:** `{current_id}`",
            color=discord.Color.orange()
        )
        embed.set_footer(text="Auto-detected from AssettoHosting API")
        await channel.send(embed=embed)

bot.run(TOKEN)
