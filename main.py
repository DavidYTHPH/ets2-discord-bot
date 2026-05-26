import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
import os
import re
import requests

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
LOGS_URL = "https://de4.assettohosting.com:60081/logs"
PANEL_COOKIE = os.getenv("PANEL_COOKIE")

class ConvoyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Registers the slash commands with Discord's systems
        print("Registering slash commands...")
        await self.tree.sync()

bot = ConvoyBot()
last_known_id = None
has_posted_initial = False

def fetch_convoy_id():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        
        cookies = {}
        if PANEL_COOKIE:
            cookies = {
                "errors": PANEL_COOKIE,
                "messages": PANEL_COOKIE
            }
        
        response = requests.get(LOGS_URL, headers=headers, cookies=cookies, timeout=15)
        if response.status_code != 200:
            return None
            
        html_text = response.text
        
        # Primary Regex Pattern Match for Convoy formatting
        match = re.search(r"(\d{14,19}/\d{2,3})", html_text)
        if match:
            return match.group(1)
            
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
        check_server_id.start()

# --- THE SLASH COMMAND ---
@bot.tree.command(name="convoyid", description="Fetch the current live ETS2 Convoy Search ID.")
async def convoyid(interaction: discord.Interaction):
    # Let the user know the bot is thinking while it requests the website data
    await interaction.response.defer(ephemeral=False)
    
    # Run the live scrape request
    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    
    if current_id:
        embed = discord.Embed(
            title="🚚 Live Convoy Status",
            description=f"The server is active! Join using the ID below:\n\n**Search ID:** `{current_id}`",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)
    else:
        embed = discord.Embed(
            title="⚠️ Convoy ID Not Found",
            description=(
                "The bot connected to the panel, but couldn't find an active Search ID string.\n\n"
                "**Possible Reasons:**\n"
                "* The server is currently offline or crashing.\n"
                "* The log buffer has cleared out."
            ),
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

# --- BACKGROUND AUTOMATION LOOP ---
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
    print(f"Loop Scraped Output: {current_id}")
    
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        has_posted_initial = True
        
        embed = discord.Embed(
            title="🚚 Euro Truck Simulator 2 Server Online!",
            description=f"A new Search ID has been successfully detected.\n\n**Search ID:** `{current_id}`",
            color=discord.Color.green()
        )
        await channel.send(embed=embed)
        
    elif not current_id and not has_posted_initial:
        has_posted_initial = True
        embed = discord.Embed(
            title="🚚 ETS2 Lobby Monitor Connected",
            description=(
                f"The bot has successfully authenticated using your session cookies!\n\n"
                f"⚠️ *The server manager is currently responding cleanly. Once your support ticket is handled "
                f"and the server boots past the virtual memory error, the live ID will post here instantly!*"
            ),
            color=discord.Color.blue()
        )
        await channel.send(embed=embed)

bot.run(TOKEN)
