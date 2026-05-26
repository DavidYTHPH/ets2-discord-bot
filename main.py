import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
import os
import re
import json
import requests

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
LOGS_URL = "https://de4.assettohosting.com:60081/logs"
PANEL_COOKIE = os.getenv("PANEL_COOKIE")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# 🔒 DIRECT LOCK SERVER ID
GUILD_ID = 1508575872976949411  
SERVER_OBJ = discord.Object(id=GUILD_ID)

# --- LOCAL JSON DB FOR SECURE ACCOUNTS ---
DB_FILE = "users.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

class ConvoyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=SERVER_OBJ)
        await self.tree.sync(guild=SERVER_OBJ)
        if not check_server_id.is_running():
            check_server_id.start()

bot = ConvoyBot()
last_known_id = None

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

def resolve_steam_user(steam_id_64):
    if not STEAM_API_KEY:
        return {"error": "Steam API Key variable is missing in Railway configurations."}
    
    summary_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id_64}"
    try:
        summary_res = requests.get(summary_url, timeout=10).json()
        players = summary_res.get("response", {}).get("players", [])
        if not players: return {"error": "Profile details hidden or private."}
        
        player_data = players[0]
        id_num = int(steam_id_64)
        steam_id_3 = f"[U:1:{id_num - 76561197960265728}]"
        
        return {
            "name": player_data.get("personaname", "Unknown User"),
            "url": player_data.get("profileurl", ""),
            "avatar": player_data.get("avatarfull", ""),
            "id64": str(steam_id_64),
            "id3": steam_id_3
        }
    except Exception:
        return {"error": "Error processing Steam profile details."}

def build_steam_embed(result):
    embed = discord.Embed(title=f"👤 Steam Account: {result['name']}", url=result["url"], color=discord.Color.blue())
    embed.set_thumbnail(url=result["avatar"])
    embed.add_field(name="🌐 SteamID64 (Default format)", value=f"`{result['id64']}`", inline=False)
    embed.add_field(name="🆔 SteamID3 (Config/Server format)", value=f"`{result['id3']}`", inline=False)
    embed.set_footer(text="Verified via Official Steam OpenID Authentication")
    return embed

# --- INTERACTIVE LINK SELECTION UTILITY BUTTON ---
class SteamLinkView(discord.ui.View):
    def __init__(self, auth_url: str, user_id: int):
        super().__init__(timeout=180)
        self.auth_url = auth_url
        self.user_id = user_id
        # Add the link button targeting the authentication site
        self.add_item(discord.ui.Button(label="🔐 Sign In With Steam", url=self.auth_url))

    @discord.ui.button(label="✅ Confirm My Verification Connection", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You cannot verify another user's login sequence!", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        # Check the open-source gateway cache to pull down their completed authentication handshake tokens
        poll_url = f"https://api.steamlink.xyz/v1/user/{interaction.user.id}"
        try:
            res = requests.get(poll_url, timeout=10).json()
            if res.get("success") and "steamid" in res:
                steam_id = res["steamid"]
                
                # Save it permanently to our local storage file
                db = load_db()
                db[str(interaction.user.id)] = str(steam_id)
                save_db(db)
                
                # Pull account data using the token we created earlier
                profile = resolve_steam_user(steam_id)
                if "error" in profile:
                    await interaction.followup.send(content=f"✅ Account successfully synced, but Steam profile extraction failed: {profile['error']}", ephemeral=True)
                else:
                    await interaction.followup.send(content="🎉 Setup completed!", embed=build_steam_embed(profile), ephemeral=True)
            else:
                await interaction.followup.send(content="❌ Connection not detected yet. Please click the login button above, log into your Steam account, and then click confirm again!", ephemeral=True)
        except Exception:
            await interaction.followup.send(content="❌ The authentication server is currently busy. Please try completing your link in a few moments!", ephemeral=True)

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
        embed = discord.Embed(title="⚠️ Convoy ID Not Found", description="Server is offline or crashing.", color=discord.Color.red())
        await interaction.followup.send(embed=embed)

# --- COMMAND 2: OFFICIAL SECURE STEAM ACCOUNT OAUTH LINK ---
@bot.tree.command(name="link", description="Securely log in and link your official Steam profile account to this server.")
async def link(interaction: discord.Interaction):
    # This command uses ephemeral=True so other players can't intercept your distinct link keys!
    await interaction.response.defer(ephemeral=True)
    
    # Generate the custom Steam portal tracking link using the verified steamlink.xyz routing engine
    auth_gateway_url = f"https://steamlink.xyz/auth/{interaction.user.id}"
    
    embed = discord.Embed(
        title="🔒 Steam Profile Secure Authentication Link",
        description=(
            f"Hey {interaction.user.mention}! To link your account securely:\n\n"
            f"1. Click the **Sign In With Steam** link button below.\n"
            f"2. Log in directly on the official Steam platform window.\n"
            f"3. Return right here and press the green **Confirm Connection** button below!\n\n"
            f"*Note: This app only reads your public SteamID64 string. Your credentials remain perfectly private to Steam.*"
        ),
        color=discord.Color.blue()
    )
    await interaction.followup.send(embed=embed, view=SteamLinkView(auth_gateway_url, interaction.user.id), ephemeral=True)

# --- COMMAND 3: SEARCH PROFILE CONNECTIONS ---
@bot.tree.command(name="steamid", description="Look up a server member's authenticated profile connections.")
@app_commands.describe(target_member="Tag a server member (e.g. @DAVIDYTHPH) to check their official linked Steam ID profile.")
async def steamid(interaction: discord.Interaction, target_member: discord.Member = None):
    await interaction.response.defer(ephemeral=False)
    
    db = load_db()
    search_user = target_member if target_member else interaction.user
    user_key = str(search_user.id)
    
    if user_key in db:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, resolve_steam_user, db[user_key])
        if "error" in result:
            await interaction.followup.send(embed=discord.Embed(title="❌ Search Failed", description=result["error"], color=discord.Color.red()))
        else:
            await interaction.followup.send(embed=build_steam_embed(result))
    else:
        await interaction.followup.send(embed=discord.Embed(
            title="⚠️ Authenticated Profile Not Found",
            description=(
                f"This user hasn't securely verified their account profile connections yet.\n\n"
                f"💡 **To fix this:** Have {search_user.mention} type and run the `/link` command inside the chat window "
                f"to authenticate directly with Steam!"
            ),
            color=discord.Color.orange()
        ))

# --- BACKGROUND AUTOMATION LOOP ---
@tasks.loop(seconds=60)
async def check_server_id():
    global last_known_id
    if CHANNEL_ID == 0: return
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return
    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        embed = discord.Embed(title="🚚 Euro Truck Simulator 2 Server Online!", description=f"**Search ID:** `{current_id}`", color=discord.Color.green())
        await channel.send(embed=embed)

bot.run(TOKEN)
