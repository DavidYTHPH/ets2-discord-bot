import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
import os
import re
import json
import aiohttp
from aiohttp import web

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
        return {"error": "Steam API Key variable is missing."}
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
        return {"error": f"Error processing Steam details: {str(e)}"}

async def resolve_steam_user_by_name(name_string):
    if not STEAM_API_KEY: return {"error": "Steam Key Missing."}
    
    clean_input = str(name_string).strip().rstrip('/')
    if "steamcommunity.com/id/" in clean_input:
        clean_input = clean_input.split("/id/")[-1]
    elif "steamcommunity.com/profiles/" in clean_input:
        clean_input = clean_input.split("/profiles/")[-1]

    if re.match(r"^\d{17}$", clean_input):
        return await resolve_steam_user(clean_input)

    resolve_url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={clean_input}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(resolve_url, timeout=10) as resp:
                if resp.status != 200: return {"error": "Steam server error."}
                data = await resp.json()
                if data.get("response", {}).get("success") == 1:
                    return await resolve_steam_user(data["response"]["steamid"])
                return {"error": f"Could not find a matching public Steam profile for: `{name_string}`."}
    except:
        return {"error": "Failed to connect to Steam database servers."}

def build_steam_embed(result):
    embed = discord.Embed(title=f"👤 Steam Account: {result['name']}", url=result["url"], color=discord.Color.blue())
    embed.set_thumbnail(url=result["avatar"])
    embed.add_field(name="🌐 SteamID64 (Default format)", value=f"`{result['id64']}`", inline=False)
    embed.add_field(name="🆔 SteamID3 (Config/Server format)", value=f"`{result['id3']}`", inline=False)
    embed.set_footer(text="Verified via Official Server Integration")
    return embed

# --- NATIVE WEB SERVER ROUTES (Runs seamlessly with Discord) ---
async def web_login(request):
    discord_id = request.match_info.get('discord_id')
    base_url = os.getenv("PUBLIC_URL", "").rstrip('/')
    
    return_to = f"{base_url}/verify?discord_id={discord_id}"
    steam_openid_url = (
        "https://steamcommunity.com/openid/login"
        "?openid.ns=http://specs.openid.net/auth/2.0"
        "&openid.mode=checkid_setup"
        f"&openid.return_to={return_to}"
        f"&openid.realm={base_url}"
        "&openid.identity=http://specs.openid.net/auth/2.0/identifier_select"
        "&openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select"
    )
    raise web.HTTPFound(steam_openid_url)

async def web_verify(request):
    discord_id = request.query.get("discord_id")
    claimed_id = request.query.get("openid.claimed_id")
    
    if not discord_id or not claimed_id:
        return web.Response(text="❌ Authentication arguments missing.", status=400)
        
    steam_id = claimed_id.split("/id/")[-1]
    
    db = load_db()
    db[str(discord_id)] = str(steam_id)
    save_db(db)
    
    # Try sending a DM to the user to confirm
    try:
        user_obj = await bot.fetch_user(int(discord_id))
        if user_obj:
            res_data = await resolve_steam_user(steam_id)
            if "error" not in res_data:
                await user_obj.send(content="🎉 Your Steam account has been securely linked!", embed=build_steam_embed(res_data))
    except Exception as e:
        print(f"DM Failed: {e}")

    html_content = """
    <body style="font-family: sans-serif; background: #1a1c1e; color: white; text-align: center; padding-top: 100px;">
        <h1 style="color: #43b581;">✅ Steam Profile Securely Linked!</h1>
        <p style="font-size: 18px; color: #b9bbbe;">You can safely close this browser tab and return right to Discord now.</p>
    </body>
    """
    return web.Response(text=html_content, content_type='text/html')

# --- BOT ROUTINE PLATFORM ---
class ConvoyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        # 1. Sync Discord Commands
        self.tree.copy_global_to(guild=SERVER_OBJ)
        await self.tree.sync(guild=SERVER_OBJ)
        
        # 2. Start Background Loop
        if not check_server_id.is_running():
            check_server_id.start()
            
        # 3. Start Native Web Server inside Discord's event loop
        app = web.Application()
        app.add_routes([
            web.get('/login/{discord_id}', web_login),
            web.get('/verify', web_verify)
        ])
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", "8080"))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"Native Auth Server running on port {port}")

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

# --- COMMAND 2: SECURE LINK PORTAL ---
@bot.tree.command(name="link", description="Securely log in and link your official Steam account.")
async def link(interaction: discord.Interaction):
    base_url = os.getenv("PUBLIC_URL", "").rstrip('/')
    if not base_url:
        await interaction.response.send_message("❌ The bot host configuration is missing the `PUBLIC_URL` variable.", ephemeral=True)
        return
        
    secure_route = f"{base_url}/login/{interaction.user.id}"
    
    embed = discord.Embed(
        title="🔒 Steam Account Identity Link",
        description=(
            f"Hey {interaction.user.mention}! To link your account natively:\n\n"
            f"1. Click the **🔐 Sign In With Steam** button below.\n"
            f"2. Complete your login directly on Steam.\n"
            f"3. You will instantly get a DM confirming you are linked!\n\n"
            f"*Your account password remains completely safe and invisible to this server.*"
        ),
        color=discord.Color.blue()
    )
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="🔐 Sign In With Steam", url=secure_route))
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --- COMMAND 3: TRACKING SEARCH SYSTEM ---
@bot.tree.command(name="steamid", description="Look up a server member's profile.")
@app_commands.describe(
    target_member="Tag a user in this server to fetch their secure profile data.",
    manual_search="Alternatively, paste a custom text username or direct Steam URL link here."
)
async def steamid(interaction: discord.Interaction, target_member: discord.Member = None, manual_search: str = None):
    await interaction.response.defer(ephemeral=False)
    db = load_db()
    
    if manual_search:
        result = await resolve_steam_user_by_name(manual_search)
    else:
        search_user = target_member if target_member else interaction.user
        user_key = str(search_user.id)
        
        if user_key in db:
            result = await resolve_steam_user(db[user_key])
        else:
            steam_target = search_user.display_name
            result = await resolve_steam_user_by_name(steam_target)
            if "error" in result and steam_target != search_user.name:
                result = await resolve_steam_user_by_name(search_user.name)

    if "error" in result:
        await interaction.followup.send(embed=discord.Embed(
            title="⚠️ Profile Not Found",
            description=(f"I could not automatically resolve that user.\n\n"
                         f"💡 **The Fix:** Have them use `/link` to log in, OR paste their Steam URL into the `manual_search` option!"),
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
