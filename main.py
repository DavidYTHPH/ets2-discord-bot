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

def fetch_convoy_id():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        print(f"Checking server logs at: {LOGS_URL}")
        response = requests.get(LOGS_URL, headers=headers, timeout=15)
        
        print(f"Log page HTTP Status: {response.status_code}")
        
        # If the log page requires a login, it will redirect us or return a 401/403/302
        if response.status_code != 200:
            print("Warning: Log page is protected or unreachable.")
            return None
            
        html_text = response.text
        
        # Look for the standard ETS2 Search ID format (e.g., 12345678901234567/101)
        match = re.search(r"(\d{14,19}/\d{2,3})", html_text)
        if match:
            return match.group(1)
            
        # Fallback broad match for any 'digits/digits' format
        fallback_match = re.search(r"(\d+/\d+)", html_text)
        if fallback_match:
            return fallback_match.group(1)
            
        print("No convoy ID format found in the text.")
        return None
    except Exception as e:
        print(f"Log parser error: {e}")
        return None

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    # Force start the loop if it hasn't started yet
    if not check_server_id.is_running():
        print("Starting background loop task...")
        check_server_id.start()

@tasks.loop(seconds=60)
async def check_server_id():
    global last_known_id
    print("--- Running Log Scan Loop ---")
    
    if CHANNEL_ID == 0:
        print("Error: DISCORD_CHANNEL_ID is not set.")
        return
        
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Error: Discord channel {CHANNEL_ID} could not be found.")
        return

    # Run the scraping function in a separate thread so it doesn't freeze the bot
    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    print(f"Current Loop Result: {current_id}")
    
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        print(f"New ID Detected! Sending to channel: {current_id}")
        embed = discord.Embed(
            title="🚚 ETS2 Server Updated / Restarted!",
            description=f"AssettoHosting has generated a new Search ID for the lobby.\n\n**Search ID:** `{current_id}`",
            color=discord.Color.orange()
        )
        embed.set_footer(text="Auto-extracted from Live Server Logs")
        await channel.send(embed=embed)

bot.run(TOKEN)
