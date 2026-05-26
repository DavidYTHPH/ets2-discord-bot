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
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# --- MANUAL STEAM LINKING REGISTRY ---
# Put your numeric Discord User ID here, paired with your Steam username/ID64
# so the bot instantly knows who you are when you choose "me".
DISCORD_TO_STEAM_MAP = {
    714243681428144128: "looksmaxxing",  # Example entry: replace with your actual ID if needed
}

class ConvoyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        if not check_server_id.is_running():
            check_server_id.start()

bot = ConvoyBot()
last_known_id = None
has_posted_initial = False

def fetch_convoy_id():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        cookies = {}
        if PANEL_COOKIE:
            cookies = {"errors": PANEL_COOKIE, "messages": PANEL_COOKIE}
        
        response = requests.get(LOGS_URL, headers=headers, cookies=cookies, timeout=15)
        if response.status_code != 200: return None
        html_text = response.text
        
        match = re.search(r"(\d{14,19}/\d{2,3})", html_text)
        if match: return match.group(1)
        fallback_match = re.search(r"(\d+/\d+)", html_text)
        if fallback_match: return fallback_match.group(1)
        return None
    except Exception as e:
        print(f"Log parser thread error: {e}")
        return None

def resolve_steam_user(input_string):
    if not STEAM_API_KEY:
        return {"error": "Steam API Key variable is missing in Railway configurations."}
        
    clean_input = str(input_string).strip().rstrip('/')
    
    if "steamcommunity.com/id/" in clean_input:
        clean_input = clean_input.split("/id/")[-1]
    elif "steamcommunity.com/profiles/" in clean_input:
        clean_input = clean_input.split("/profiles/")[-1]

    if re.match(r"^\d{17}$", clean_input):
        steam_id_64 = clean_input
    else:
        resolve_url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={clean_input}"
        try:
            res = requests.get(resolve_url, timeout=10).json()
            if res.get("response", {}).get("success") == 1:
                steam_id_64 = res["response"]["steamid"]
            else:
                return {"error": f"Could not find a Steam profile matching `{input_string}`."}
        except Exception:
            return {"error": "Failed to communicate with Steam API servers."}

    summary_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id_64}"
    try:
        summary_res = requests.get(summary_url, timeout=10).json()
        players = summary_res.get("response", {}).get("players", [])
        if not players:
            return {"error": "Profile details are hidden or restricted."}
        
        player_data = players[0]
        id_num = int(steam_id_64)
        steam_id_3 = f"[U:1:{id_num - 76561197960265728}]"
        
        return {
            "name": player_data.get("personaname", "Unknown User"),
            "url": player_data.get("profileurl", ""),
            "avatar": player_data.get("avatarfull", ""),
            "id64": steam_id_64,
            "id3": steam_id_3
        }
    except Exception:
        return {"error": "Error processing profile details."}

def build_steam_embed(result):
    embed = discord.Embed(
        title=f"👤 Steam Account: {result['name']}",
        url=result["url"],
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=result["avatar"])
    embed.add_field(name="🌐 SteamID64 (Default format)", value=f"`{result['id64']}`", inline=False)
    embed.add_field(name="🆔 SteamID3 (Config/Server format)", value=f"`{result['id3']}`", inline=False)
    embed.set_footer(text="Useful for adding admin privileges to server config profiles")
    return embed

@bot.event
async def on_ready():
    print(f"Bot successfully registered on gateway. Online as: {bot.user}")
    try:
        print("Syncing slash command tree...")
        synced = await bot.tree.sync()
        print(f"Successfully synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync command tree: {e}")

# --- COMMAND 1: CONVOY FETCH ---
@bot.tree.command(name="convoyid", description="Fetch the current live ETS2 Convoy Search ID.")
async def convoyid(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    
    if current_id:
        embed = discord.Embed(title="🚚 Live Convoy Status", description=f"**Search ID:** `{current_id}`", color=discord.Color.green())
        await interaction.followup.send(embed=embed)
    else:
        embed = discord.Embed(title="⚠️ Convoy ID Not Found", description="Server is currently offline or crashing.", color=discord.Color.red())
        await interaction.followup.send(embed=embed)

# --- COMMAND 2: SINGLE UNIFIED STEAM ID COMMAND ---
@bot.tree.command(name="steamid", description="Look up yours or a friend's Steam structural ID profiles.")
@app_commands.describe(target="Type 'me' for your own profile, or paste a friend's Steam URL/username.")
async def steamid(interaction: discord.Interaction, target: str):
    await interaction.response.defer(ephemeral=False)
    
    # Check if user wants their own logged profile info
    if target.strip().lower() == "me":
        user_discord_id = interaction.user.id
        if user_discord_id not in DISCORD_TO_STEAM_MAP:
            embed = discord.Embed(
                title="❌ Profile Not Linked", 
                description=(
                    f"Your personal Discord account isn't mapped inside the code yet!\n\n"
                    f"**To link yourself:** Open `main.py` on GitHub and add your Discord ID (`{user_discord_id}`) "
                    f"to the `DISCORD_TO_STEAM_MAP` list near the top."
                ), 
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed)
            return
        steam_target = DISCORD_TO_STEAM_MAP[user_discord_id]
    else:
        # Otherwise, treat the input as a friend's custom string link
        steam_target = target

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, resolve_steam_user, steam_target)
    
    if "error" in result:
        await interaction.followup.send(embed=discord.Embed(title="❌ Search Failed", description=result["error"], color=discord.Color.red()))
    else:
        await interaction.followup.send(embed=build_steam_embed(result))

# --- BACKGROUND AUTOMATION LOOP ---
@tasks.loop(seconds=60)
async def check_server_id():
    global last_known_id, has_posted_initial
    if CHANNEL_ID == 0: return
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return

    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        has_posted_initial = True
        embed = discord.Embed(title="🚚 Euro Truck Simulator 2 Server Online!", description=f"**Search ID:** `{current_id}`", color=discord.Color.green())
        await channel.send(embed=embed)
    elif not current_id and not has_posted_initial:
        has_posted_initial = True
        embed = discord.Embed(title="🚚 ETS2 Lobby Monitor Connected", description="The bot is online and waiting for your server hosting node memory to clear!", color=discord.Color.blue())
        await channel.send(embed=embed)

bot.run(TOKEN)
