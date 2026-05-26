import discord
from discord.ext import tasks, commands
import asyncio
import os
import re
import sys
from playwright.async_api import async_playwright

# --- AUTOMATIC BROWSER + SYSTEM DEPENDENCY INSTALLATION ---
# This forces the Railway Linux container to install both Chromium and its missing system libraries on startup
print("Installing missing Linux system dependencies and Chromium... Please wait.")
os.system("python -m playwright install --with-deps chromium")
print("Installation complete! Starting bot...")

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
PANEL_URL = "https://de4.assettohosting.com:60081/server-control"
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

last_known_id = None

async def fetch_convoy_id():
    async with async_playwright() as p:
        try:
            # Launched with cloud-compatible arguments to bypass security sandbox errors
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-setuid-sandbox', '--single-process']
            )
            page = await browser.new_page()
            await page.goto(PANEL_URL, timeout=60000)
            await page.wait_for_load_state("networkidle")
            
            text_content = await page.locator("body").inner_text()
            match = re.search(r"(\d+/\d+)", text_content)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            print(f"Error scraping panel: {e}")
            return None
        finally:
            try:
                await browser.close()
            except:
                pass

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    if not check_server_id.is_running():
        check_server_id.start()

@tasks.loop(seconds=60)
async def check_server_id():
    global last_known_id
    if CHANNEL_ID == 0:
        print("Error: DISCORD_CHANNEL_ID environment variable is missing or set to 0.")
        return
        
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Error: Could not find channel with ID {CHANNEL_ID}. Make sure the bot is invited to that server.")
        return

    current_id = await fetch_convoy_id()
    print(f"Scraped ID from panel: {current_id}")
    
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
