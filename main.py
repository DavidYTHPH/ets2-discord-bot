import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
import os
import re
import json
import aiohttp
from aiohttp import web
import yt_dlp

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
LOGS_URL = "https://de4.assettohosting.com:60081/logs"
PANEL_COOKIE = os.getenv("PANEL_COOKIE")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# 🔒 DIRECT LOCK SERVER ID
GUILD_ID = 1508575872976949411  
SERVER_OBJ = discord.Object(id=GUILD_ID)

# --- LOCAL STORAGE DATABASE (NOW PERSISTENT) ---
# This checks if you added the Railway Volume. If yes, it saves it there permanently!
DB_DIR = "/app/data"
if os.path.exists(DB_DIR):
    DB_FILE = os.path.join(DB_DIR, "users.json")
else:
    DB_FILE = "users.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

# --- MUSIC BOT SETTINGS & QUEUE ---
music_queues = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch', # Bypasses YouTube IP bans!
    'source_address': '0.0.0.0'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

def play_next(guild_id, vc):
    if guild_id in music_queues and len(music_queues[guild_id]) > 0:
        song = music_queues[guild_id].pop(0)
        vc.play(discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS), after=lambda e: play_next(guild_id, vc))
    else:
        if vc and vc.is_connected():
            asyncio.run_coroutine_threadsafe(vc.disconnect(), bot.loop)

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
                
                personastate = player_data.get("personastate", 0)
                state_colors = {0: 0x747f8d, 1: 0x43b581, 2: 0xf04747, 3: 0xfaa61a, 4: 0xfaa61a, 5: 0x43b581, 6: 0x43b581}
                state_text = {0: "⚫ Offline", 1: "🟢 Online", 2: "🔴 Busy", 3: "🟡 Away", 4: "🌙 Snooze", 5: "📦 Looking to Trade", 6: "🎮 Looking to Play"}
                
                return {
                    "name": player_data.get("personaname", "Unknown User"),
                    "url": player_data.get("profileurl", ""),
                    "avatar": player_data.get("avatarfull", ""),
                    "id64": str(steam_id_64),
                    "id3": steam_id_3,
                    "status": state_text.get(personastate, "⚫ Offline"),
                    "color": state_colors.get(personastate, 0x3498db),
                    "realname": player_data.get("realname"),
                    "country": player_data.get("loccountrycode"),
                    "timecreated": player_data.get("timecreated")
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

# --- UI BUILDERS ---
def build_steam_embed(result):
    embed = discord.Embed(title=f"👤 {result['name']}", color=result["color"])
    embed.set_thumbnail(url=result["avatar"])
    
    desc = f"**Status:** {result['status']}\n"
    if result.get('realname'):
        desc += f"**Name:** {result['realname']}\n"
    if result.get('country'):
        desc += f"**Region:** :flag_{result['country'].lower()}:\n"
    if result.get('timecreated'):
        desc += f"**Joined Steam:** <t:{result['timecreated']}:R>\n"
        
    embed.description = desc + "\n"
    embed.add_field(name="🌐 SteamID64", value=f"```\n{result['id64']}\n```", inline=True)
    embed.add_field(name="🆔 SteamID3", value=f"```\n{result['id3']}\n```", inline=True)
    embed.set_footer(text="Verified via Native Server Integration", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/512px-Steam_icon_logo.svg.png")
    return embed

class SteamProfileView(discord.ui.View):
    def __init__(self, url):
        super().__init__()
        self.add_item(discord.ui.Button(label="View Steam Profile", url=url, style=discord.ButtonStyle.link, emoji="🔗"))

# --- NATIVE WEB SERVER ROUTES ---
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
    
    try:
        user_obj = await bot.fetch_user(int(discord_id))
        if user_obj:
            res_data = await resolve_steam_user(steam_id)
            if "error" not in res_data:
                await user_obj.send(content="🎉 Your Steam account has been securely linked to the server!", embed=build_steam_embed(res_data), view=SteamProfileView(res_data["url"]))
    except Exception:
        pass

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
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=SERVER_OBJ)
        await self.tree.sync(guild=SERVER_OBJ)
        
        if not check_server_id.is_running():
            check_server_id.start()
            
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

# --- 🎵 MUSIC COMMANDS ---
@bot.tree.command(name="play", description="[MUSIC] Search and play a song in your voice channel.")
@app_commands.describe(search="The song name")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer(ephemeral=False)
    
    if not interaction.user.voice:
        await interaction.followup.send("❌ You need to be in a voice channel to use this!")
        return
        
    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()
        
    loop = asyncio.get_event_loop()
    try:
        # We explicitly force the search to SoundCloud to completely bypass the YouTube IP ban!
        if not search.startswith("http"):
            search_query = f"scsearch:{search}"
        else:
            search_query = search
            
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
        if 'entries' in data and len(data['entries']) > 0:
            song_info = data['entries'][0]
        else:
            song_info = data
            
        song_dict = {'url': song_info['url'], 'title': song_info.get('title', 'Unknown Audio')}
        
        guild_id = interaction.guild.id
        if guild_id not in music_queues:
            music_queues[guild_id] = []
            
        music_queues[guild_id].append(song_dict)
        
        if not vc.is_playing() and not vc.is_paused():
            play_next(guild_id, vc)
            await interaction.followup.send(f"▶️ **Now Playing:** `{song_dict['title']}`")
        else:
            await interaction.followup.send(f"📝 **Added to Queue:** `{song_dict['title']}` (Position: {len(music_queues[guild_id])})")
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error finding song. Please try a different track name.")

@bot.tree.command(name="skip", description="[MUSIC] Skip the currently playing song.")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop() 
        await interaction.response.send_message("⏭️ **Skipped!**")
    else:
        await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

@bot.tree.command(name="stop", description="[MUSIC] Stop the music and clear the queue.")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in music_queues:
        music_queues[guild_id] = []
        
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("⏹️ **Music stopped and disconnected.**")
    else:
        await interaction.response.send_message("❌ I am not in a voice channel.", ephemeral=True)

@bot.tree.command(name="queue", description="[MUSIC] View the upcoming songs in the queue.")
async def queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in music_queues and len(music_queues[guild_id]) > 0:
        q_list = "\n".join([f"{i+1}. {song['title']}" for i, song in enumerate(music_queues[guild_id][:10])])
        embed = discord.Embed(title="🎶 Current Queue", description=f"```{q_list}```", color=discord.Color.blurple())
        if len(music_queues[guild_id]) > 10:
            embed.set_footer(text=f"...and {len(music_queues[guild_id]) - 10} more songs.")
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("📂 The queue is currently empty.")

# --- UTILITY COMMANDS ---
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

@bot.tree.command(name="link", description="Securely log in and link your official Steam account.")
async def link(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    db = load_db()
    if str(interaction.user.id) in db:
        await interaction.followup.send("✅ You are already verified and securely linked! If you need to change your linked account, please ask a Server Admin.", ephemeral=True)
        return

    base_url = os.getenv("PUBLIC_URL", "").rstrip('/')
    if not base_url:
        await interaction.followup.send("❌ Missing `PUBLIC_URL` variable.", ephemeral=True)
        return
        
    secure_route = f"{base_url}/login/{interaction.user.id}"
    embed = discord.Embed(
        title="🔒 Steam Account Identity Link",
        description=(f"Hey {interaction.user.mention}! Click the button below to sign in directly via Steam. "
                     f"Your credentials remain 100% hidden and secure."),
        color=discord.Color.blurple()
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="🔐 Sign In With Steam", url=secure_route))
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="steamid", description="Look up a server member's profile.")
@app_commands.describe(
    target_member="Tag a user to fetch their secure profile data.",
    manual_search="Alternatively, paste a custom text username or direct URL link here."
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
            description=f"Could not automatically resolve that user.\n💡 Have them use `/link` to log in, OR paste their URL into `manual_search`!",
            color=discord.Color.orange()
        ))
    else:
        await interaction.followup.send(embed=build_steam_embed(result), view=SteamProfileView(result["url"]))

# --- ADMIN COMMANDS ---
@bot.tree.command(name="admin_forcelink", description="[ADMIN] Force link a user to a specific Steam ID.")
@app_commands.default_permissions(administrator=True)
async def admin_forcelink(interaction: discord.Interaction, target: discord.Member, steam_id: str):
    if not steam_id.isdigit() or len(steam_id) != 17:
        await interaction.response.send_message("❌ Invalid Steam ID. It must be the raw 17-digit SteamID64.", ephemeral=True)
        return
        
    db = load_db()
    db[str(target.id)] = steam_id
    save_db(db)
    await interaction.response.send_message(f"✅ Successfully force-linked {target.mention} to SteamID: `{steam_id}`", ephemeral=True)

@bot.tree.command(name="admin_unlink", description="[ADMIN] Wipe a user's Steam profile from the database.")
@app_commands.default_permissions(administrator=True)
async def admin_unlink(interaction: discord.Interaction, target: discord.Member):
    db = load_db()
    user_key = str(target.id)
    if user_key in db:
        del db[user_key]
        save_db(db)
        await interaction.response.send_message(f"🗑️ Successfully unlinked and wiped data for {target.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ {target.mention} is not currently linked in the database.", ephemeral=True)

@bot.tree.command(name="admin_stats", description="[ADMIN] View database driver verification statistics.")
@app_commands.default_permissions(administrator=True)
async def admin_stats(interaction: discord.Interaction):
    db = load_db()
    count = len(db)
    embed = discord.Embed(title="📊 Server Tracking Database", description=f"Total Verified Drivers Linked: **{count}**", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- BACKGROUND TASKS ---
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
