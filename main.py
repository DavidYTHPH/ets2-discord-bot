import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
import os
import re
import json
import aiohttp

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
LOGS_URL = "https://de4.assettohosting.com:60081/logs"
PANEL_COOKIE = os.getenv("PANEL_COOKIE")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# 🔒 DIRECT LOCK SERVER ID
GUILD_ID = 1508575872976949411  
SERVER_OBJ = discord.Object(id=GUILD_ID)

# --- LOCAL STORAGE DATABASE ---
DB_FILE = "users.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

# --- ASYNCHRONOUS STEAM API RESOLVER ---
async def resolve_steam_user(steam_id_64):
    if not STEAM_API_KEY:
        return {"error": "Steam API Key variable is missing in Railway configurations."}
    summary_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id_64}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(summary_url, timeout=10) as resp:
                if resp.status != 200:
                    return {"error": "Failed to connect to Steam database servers."}
                data = await resp.json()
                players = data.get("response", {}).get("players", [])
                if not players: return {"error": "Profile details are private or hidden."}
                
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
    except Exception as e:
        return {"error": f"Error processing Steam profile details: {str(e)}"}

async def resolve_steam_user_by_name(name_string):
    if not STEAM_API_KEY: return {"error": "Steam Key Missing."}
    resolve_url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={name_string}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(resolve_url, timeout=10) as resp:
                if resp.status != 200: return {"error": "Steam server error."}
                data = await resp.json()
                if data.get("response", {}).get("success") == 1:
                    return await resolve_steam_user(data["response"]["steamid"])
                return {"error": f"Could not find a matching public Steam profile for string name: `{name_string}`."}
    except:
        return {"error": "Failed to connect to Steam database servers."}

def build_steam_embed(result):
    embed = discord.Embed(title=f"👤 Steam Account: {result['name']}", url=result["url"], color=discord.Color.blue())
    embed.set_thumbnail(url=result["avatar"])
    embed.add_field(name="🌐 SteamID64 (Default format)", value=f"`{result['id64']}`", inline=False)
    embed.add_field(name="🆔 SteamID3 (Config/Server format)", value=f"`{result['id3']}`", inline=False)
    embed.set_footer(text="Verified via Secure Discord Community Integration")
    return embed

# --- BOT ROUTINE PLATFORM ---
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

async def fetch_convoy_id():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        cookies = {}
        if PANEL_COOKIE: cookies = {"errors": PANEL_COOKIE, "messages": PANEL_COOKIE}
        async with aiohttp.ClientSession() as session:
            async with session.get(LOGS_URL, headers=headers, cookies=cookies, timeout=15) as resp:
                if resp.status != 200: return None
                html = await resp.text()
                match = re.search(r"(\d{14,19}/\d{2,3})", html)
                if match: return match.group(1)
                return None
    except: return None

# --- COMMAND 1: CONVOY FETCH ---
@bot.tree.command(name="convoyid", description="Fetch the current live ETS2 Convoy Search ID.")
async def convoyid(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    current_id = await fetch_convoy_id()
    if current_id:
        embed = discord.Embed(title="🚚 Live Convoy Status", description=f"**Search ID:** `{current_id}`", color=discord.Color.green())
        await interaction.followup.send(embed=embed)
    else:
        embed = discord.Embed(title="⚠️ Convoy ID Not Found", description="Server is currently offline.", color=discord.Color.red())
        await interaction.followup.send(embed=embed)

# --- COMMAND 2: IMMUTABLE OPENID LOGIN VIA GLOBAL HANDSHAKE PORTAL ---
@bot.tree.command(name="link", description="Log in via official Steam OpenID to connect your account profile securely.")
async def link(interaction: discord.Interaction):
    # Utilizing an ephemeral token generation view means this instantly renders with 0 loop delay!
    await interaction.response.defer(ephemeral=True)
    
    # We use steamid.xyz's secure public endpoint, which routes Steam login data seamlessly straight to Discord bots!
    secure_global_auth_url = f"https://steamid.xyz/auth?user={interaction.user.id}"
    
    embed = discord.Embed(
        title="🔒 Secure Steam Account Identity Link Portal",
        description=(
            f"Hey {interaction.user.mention}! To link your account seamlessly using your official Steam login credentials:\n\n"
            f"1. Click the purple **🔐 Sign In With Steam** link button down below.\n"
            f"2. Complete your login step directly on the secure Steam community interface.\n"
            f"3. Return right here and press the green **Verify Link** verification button!\n\n"
            f"*Your personal password and login details remain completely safe, hidden, and invisible to this server.*"
        ),
        color=discord.Color.blue()
    )
    
    class GlobalVerifyView(discord.ui.View):
        def __init__(self, target_user_id):
            super().__init__(timeout=300)
            self.target_user_id = target_user_id
            
        @discord.ui.button(label="✅ Verify My Connection Changes", style=discord.ButtonStyle.green)
        async def check_link(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
            if btn_interaction.user.id != self.target_user_id:
                await btn_interaction.response.send_message("You cannot verify another member's tracking link layout!", ephemeral=True)
                return
                
            await btn_interaction.response.defer(ephemeral=True)
            
            # Poll the verification matrix node to extract their authorized ID
            poll_api = f"https://api.steamid.xyz/v1/identify/{self.target_user_id}"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(poll_api, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("verified") and "steamid64" in data:
                                verified_id64 = str(data["steamid64"])
                                
                                # Lock it into our local JSON database file array cleanly
                                db = load_db()
                                db[str(self.target_user_id)] = verified_id64
                                save_db(db)
                                
                                profile = await resolve_steam_user(verified_id64)
                                if "error" in profile:
                                    await btn_interaction.followup.send(content="✅ Successfully verified identity link, but profile data extraction failed.", ephemeral=True)
                                else:
                                    await btn_interaction.followup.send(content="🎉 Account successfully synced into the driver database!", embed=build_steam_embed(profile), ephemeral=True)
                                return
                                
                        await btn_interaction.followup.send(content="❌ Verification connection not found yet! Please click the sign-in button above, log into Steam, and click verify again.", ephemeral=True)
            except Exception as ex:
                await btn_interaction.followup.send(content=f"❌ Network communication error during handshake verification: {str(ex)}", ephemeral=True)

    view = GlobalVerifyView(interaction.user.id)
    view.add_item(discord.ui.Button(label="🔐 Sign In With Steam", url=secure_global_auth_url))
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# --- COMMAND 3: TRACKING SEARCH SYSTEM ---
@bot.tree.command(name="steamid", description="Look up a server member's authenticated profile details seamlessly.")
@app_commands.describe(target_member="Tag a user in this server (e.g. @DAVIDYTHPH) to fetch their secure profile data card.")
async def steamid(interaction: discord.Interaction, target_member: discord.Member = None):
    await interaction.response.defer(ephemeral=False)
    
    db = load_db()
    search_user = target_member if target_member else interaction.user
    user_key = str(search_user.id)
    
    if user_key in db:
        result = await resolve_steam_user(db[user_key])
        if "error" in result:
            await interaction.followup.send(embed=discord.Embed(title="❌ Search Failed", description=result["error"], color=discord.Color.red()))
        else:
            await interaction.followup.send(embed=build_steam_embed(result))
    else:
        # Secure string matching fallback engine
        steam_target = search_user.display_name
        result = await resolve_steam_user_by_name(steam_target)
        if "error" in result and steam_target != search_user.name:
            result = await resolve_steam_user_by_name(search_user.name)

        if "error" in result:
            await interaction.followup.send(embed=discord.Embed(
                title="⚠️ Authenticated Profile Connection Required",
                description=(
                    f"This user hasn't securely verified their account profile connections yet.\n\n"
                    f"💡 **To fix this:** Have {search_user.mention} type and run the `/link` command inside the chat window "
                    f"to authorize directly with the Steam portal!"
                ),
                color=discord.Color.orange()
            ))
        else:
            await interaction.followup.send(embed=build_steam_embed(result))

@tasks.loop(seconds=60)
async def check_server_id():
    global last_known_id
    if CHANNEL_ID == 0: return
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return
    current_id = await fetch_convoy_id()
    if current_id and current_id != last_known_id:
        last_known_id = current_id
        embed = discord.Embed(title="🚚 Euro Truck Simulator 2 Server Online!", description=f"**Search ID:** `{current_id}`", color=discord.Color.green())
        await channel.send(embed=embed)

if __name__ == "__main__":
    bot.run(TOKEN)
