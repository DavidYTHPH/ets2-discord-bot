import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
import os
import re
import json
import requests
import quart
from quart import Quart, request, redirect

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
LOGS_URL = "https://de4.assettohosting.com:60081/logs"
PANEL_COOKIE = os.getenv("PANEL_COOKIE")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
BASE_URL = os.getenv("RAILWAY_STATIC_URL", "").rstrip('/')

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

# --- EMBED GRAPHICS GENERATORS ---
def resolve_steam_user(steam_id_64):
    if not STEAM_API_KEY:
        return {"error": "Steam API Key variable is missing in Railway configurations."}
    summary_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id_64}"
    try:
        summary_res = requests.get(summary_url, timeout=10).json()
        players = summary_res.get("response", {}).get("players", [])
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
    except Exception:
        return {"error": "Error processing Steam profile details."}

def build_steam_embed(result):
    embed = discord.Embed(title=f"👤 Steam Account: {result['name']}", url=result["url"], color=discord.Color.blue())
    embed.set_thumbnail(url=result["avatar"])
    embed.add_field(name="🌐 SteamID64 (Default format)", value=f"`{result['id64']}`", inline=False)
    embed.add_field(name="🆔 SteamID3 (Config/Server format)", value=f"`{result['id3']}`", inline=False)
    embed.set_footer(text="Verified via Official Steam Login Integration")
    return embed

# --- INTEGRATED WEB SERVER FOR STEAM LOGIN HANDSHAKES ---
app = Quart(__name__)

@app.route("/login/<int:discord_id>")
async def web_login(discord_id):
    return_to = f"{BASE_URL}/verify?discord_id={discord_id}"
    steam_openid_url = (
        "https://steamcommunity.com/openid/login"
        f"?openid.ns=http://specs.openid.net/auth/2.0"
        f"&openid.mode=checkid_setup"
        f"&openid.return_to={return_to}"
        f"&openid.realm={BASE_URL}"
        f"&openid.identity=http://specs.openid.net/auth/2.0/identifier_select"
        f"&openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select"
    )
    return redirect(steam_openid_url)

@app.route("/verify")
async def web_verify():
    params = request.args
    discord_id = params.get("discord_id")
    claimed_id = params.get("openid.claimed_id")
    
    if not discord_id or not claimed_id:
        return "<h3>❌ Authentication parameters are invalid or corrupted.</h3>", 400
        
    steam_id = claimed_id.split("/id/")[-1]
    
    db = load_db()
    db[str(discord_id)] = str(steam_id)
    save_db(db)
    
    return """
    <body style="font-family: sans-serif; background: #1a1c1e; color: white; text-align: center; padding-top: 100px;">
        <h1 style="color: #43b581;">✅ Steam Profile Securely Linked!</h1>
        <p style="font-size: 18px; color: #b9bbbe;">You can safely close this browser tab and return right to your Discord app window now.</p>
    </body>
    """

# --- BOT CONFIGURATION ---
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
        embed = discord.Embed(title="⚠️ Convoy ID Not Found", description="Server is currently offline.", color=discord.Color.red())
        await interaction.followup.send(embed=embed)

# --- COMMAND 2: SECURE STEAM CONNECTION LINKER ---
@bot.tree.command(name="link", description="Securely log in and verify your actual Steam profile with the bot sync database.")
async def link(interaction: discord.Interaction):
    if not BASE_URL:
        await interaction.response.send_message("❌ The bot host configuration is missing the `RAILWAY_STATIC_URL` variable settings.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    custom_login_route = f"{BASE_URL}/login/{interaction.user.id}"
    
    embed = discord.Embed(
        title="🔒 Steam Account Secure Identity Verification",
        description=(
            f"Hey {interaction.user.mention}! To securely link your account:\n\n"
            f"1. Click the custom entry button below to open the official secure login portal.\n"
            f"2. Sign in with your real account credentials directly on Steam's network.\n"
            f"3. Done! The system will automatically map your unique identifiers to your Discord ID.\n\n"
            f"*Your account details and password remain completely hidden from this bot.*"
        ),
        color=discord.Color.blue()
    )
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="🔐 Sign In With Steam", url=custom_login_route))
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# --- COMMAND 3: SEARCH PROFILE ---
@bot.tree.command(name="steamid", description="Look up a server member's authenticated profile details seamlessly.")
@app_commands.describe(
    target_member="Tag a user in this server (e.g. @DAVIDYTHPH) to fetch their secure profile data card.",
    text_fallback="Alternatively, paste a custom text username string or direct Steam URL link here."
)
async def steamid(interaction: discord.Interaction, target_member: discord.Member = None, text_fallback: str = None):
    await interaction.response.defer(ephemeral=False)
    
    db = load_db()
    steam_target = None
    
    if target_member:
        user_key = str(target_member.id)
        if user_key in db:
            steam_target = db[user_key]
        else:
            steam_target = target_member.display_name
    elif text_fallback:
        steam_target = text_fallback
    else:
        user_key = str(interaction.user.id)
        if user_key in db:
            steam_target = db[user_key]
        else:
            steam_target = interaction.user.display_name

    loop = asyncio.get_event_loop()
    
    if steam_target and str(steam_target).isdigit() and len(str(steam_target)) == 17:
        result = await loop.run_in_executor(None, resolve_steam_user, steam_target)
    else:
        from main import resolve_steam_user_by_name
        result = await loop.run_in_executor(None, resolve_steam_user_by_name, steam_target)
        if "error" in result and target_member and steam_target != target_member.name:
            result = await loop.run_in_executor(None, resolve_steam_user_by_name, target_member.name)

    if "error" in result:
        await interaction.followup.send(embed=discord.Embed(
            title="❌ Profile Connection Setup Required", 
            description=(
                f"I could not automatically resolve that user's profile identifiers.\n\n"
                f"💡 **The Fix:** Have that user run the `/link` command inside the chat channel to verify their Steam account!\n\n"
                f"*Alternatively, you can skip the lookup and paste their direct Steam URL link into the text_fallback box prompt.*"
            ), 
            color=discord.Color.orange()
        ))
    else:
        await interaction.followup.send(embed=build_steam_embed(result))

def resolve_steam_user_by_name(name_string):
    if not STEAM_API_KEY: return {"error": "Steam Key Missing."}
    resolve_url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={name_string}"
    try:
        res = requests.get(resolve_url, timeout=10).json()
        if res.get("response", {}).get("success") == 1:
            return resolve_steam_user(res["response"]["steamid"])
        return {"error": f"Could not find a matching public Steam profile for string name: `{name_string}`."}
    except:
        return {"error": "Failed to connect to Steam database servers."}

def fetch_convoy_id():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        cookies = {}
        if PANEL_COOKIE: cookies = {"errors": PANEL_COOKIE, "messages": PANEL_COOKIE}
        res = requests.get(LOGS_URL, headers=headers, cookies=cookies, timeout=15)
        if res.status_code != 200: return None
        html = res.text
        match = re.search(r"(\d{14,19}/\d{2,3})", html)
        if match: return match.group(1)
        fallback = re.search(r"(\d+/\d+)", html)
        if fallback: return fallback.group(1)
        return None
    except: return None

# --- BACKGROUND LOOP ---
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

# --- BACKEND RUNNER ---
async def main():
    import hypercorn.asyncio
    from hypercorn.config import Config
    
    web_config = Config()
    web_config.bind = [f"0.0.0.0:{os.getenv('PORT', '8080')}"]
    
    await asyncio.gather(
        bot.start(TOKEN),
        hypercorn.asyncio.serve(app, web_config)
    )

if __name__ == "__main__":
    asyncio.run(main())
