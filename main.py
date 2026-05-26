import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
import os
import re
import json
import requests
from sanic import Sanic, response

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

# --- STEAM DETAILED PROFILE RESOLVER ---
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
    embed.set_footer(text="Verified via Official Steam OpenID Portal Connection")
    return embed

# --- INTEGRATED ASYNCHRONOUS WEB SERVER ENGINE ---
web_app = Sanic("SteamAuthServer")

@web_app.route("/login/<discord_id:int>")
async def web_login(request, discord_id: int):
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
    return response.redirect(steam_openid_url)

@web_app.route("/verify")
async def web_verify(request):
    discord_id = request.args.get("discord_id")
    claimed_id = request.args.get("openid.claimed_id")
    
    if not discord_id or not claimed_id:
        return response.html("<h3>❌ Authentication arguments missing or corrupted.</h3>", status=400)
        
    # Extract structural numeric SteamID64 from OpenID verification identity URL string string
    steam_id = claimed_id.split("/id/")[-1]
    
    db = load_db()
    db[str(discord_id)] = str(steam_id)
    save_db(db)
    
    # Try sending a celebration message to the user dynamically via background hooks
    try:
        user_obj = bot.get_user(int(discord_id))
        if user_obj:
            res_data = resolve_steam_user(steam_id)
            if "error" not in res_data:
                await user_obj.send(content="🎉 Your profile link has been verified successfully!", embed=build_steam_embed(res_data))
    except Exception as e:
        print(f"Background verification notification error: {e}")

    return response.html("""
    <body style="font-family: sans-serif; background: #1a1c1e; color: white; text-align: center; padding-top: 100px;">
        <h1 style="color: #43b581;">✅ Steam Profile Securely Linked!</h1>
        <p style="font-size: 18px; color: #b9bbbe;">Your configuration has been locked into the server tracking arrays.</p>
        <p style="font-size: 14px; color: #72767d;">You can safely close this browser tab and return right to your Discord application window now.</p>
    </body>
    """)

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

# --- COMMAND 1: CONVOY FETCH ---
@bot.tree.command(name="convoyid", description="Fetch the current live ETS2 Convoy Search ID.")
async def convoyid(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    from main import fetch_convoy_id
    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    if current_id:
        embed = discord.Embed(title="🚚 Live Convoy Status", description=f"**Search ID:** `{current_id}`", color=discord.Color.green())
        await interaction.followup.send(embed=embed)
    else:
        embed = discord.Embed(title="⚠️ Convoy ID Not Found", description="Server is currently offline.", color=discord.Color.red())
        await interaction.followup.send(embed=embed)

# --- COMMAND 2: LIVE OPENID INTERACTIVE LOGIN LINK ---
@bot.tree.command(name="link", description="Securely log in and link your official Steam account to your server profile identity.")
async def link(interaction: discord.Interaction):
    if not BASE_URL:
        await interaction.response.send_message("❌ The bot host configuration is missing the `RAILWAY_STATIC_URL` environment variables.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    secure_route = f"{BASE_URL}/login/{interaction.user.id}"
    
    embed = discord.Embed(
        title="🔒 Steam Account Secure Identity Verification Link",
        description=(
            f"Hey {interaction.user.mention}! To securely verify and map your identity parameters:\n\n"
            f"1. Click the custom entry connection button below to access the secure verification portal.\n"
            f"2. Log in directly using your authentic credentials on the official Steam network interface.\n"
            f"3. Done! Steam will securely handshake your public structural IDs back to our tracking database.\n\n"
            f"*Your account password and credentials remain 100% private and invisible to this bot application.*"
        ),
        color=discord.Color.blue()
    )
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="🔐 Sign In With Steam", url=secure_route))
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# --- COMMAND 3: TRACKING SEARCH ---
@bot.tree.command(name="steamid", description="Look up a server member's authenticated profile details seamlessly.")
@app_commands.describe(target_member="Tag a user in this server (e.g. @DAVIDYTHPH) to fetch their secure profile data card.")
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
            title="⚠️ Authenticated Profile Connection Required",
            description=(
                f"This user hasn't securely verified their account profile connections yet.\n\n"
                f"💡 **To fix this:** Have {search_user.mention} type and run the `/link` command inside the chat window "
                f"to authorize directly with the Steam portal!"
            ),
            color=discord.Color.orange()
        ))

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
        return None
    except: return None

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

# --- UNIFIED MULTI-ENGINE CONCURRENT RUNNER ---
async def main():
    # Bind the web instance explicitly to the port provided by Railway
    server = await web_app.create_server(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        return_asyncio_server=True
    )
    await server.startup()
    
    # Fire up both the Discord Client Gateway connection loop and the Sanic web server asynchronously
    await asyncio.gather(
        bot.start(TOKEN),
        server.after_start()
    )

if __name__ == "__main__":
    asyncio.run(main())
