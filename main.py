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

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
LOGS_URL = "https://de4.assettohosting.com:60081/logs"
PANEL_COOKIE = os.getenv("PANEL_COOKIE")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
GUILD_ID = 1508575872976949411
SERVER_OBJ = discord.Object(id=GUILD_ID)

# --- DATABASE ---
DB_DIR = "/app/data"
DB_FILE = os.path.join(DB_DIR, "users.json") if os.path.exists(DB_DIR) else "users.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

# --- MUSIC QUEUE ---
music_queues = {}
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
}
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# --- BOT CLASS ---
class ConvoyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=SERVER_OBJ)
        await self.tree.sync(guild=SERVER_OBJ)
        check_server_id.start()
        app = web.Application()
        app.add_routes([web.get('/login/{discord_id}', web_login), web.get('/verify', web_verify)])
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", "8080")))
        await site.start()

bot = ConvoyBot()

# --- TASKS ---
@tasks.loop(seconds=60)
async def check_server_id():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return
    current_id = await fetch_convoy_id()
    if current_id:
        embed = discord.Embed(title="🚚 Live Convoy Status", description=f"**Search ID:** `{current_id}`", color=discord.Color.green())
        await channel.send(embed=embed)

# --- MUSIC LOGIC ---
@bot.event
async def on_voice_state_update(member, before, after):
    vc = member.guild.voice_client
    if vc and vc.channel and len(vc.channel.members) == 1:
        await asyncio.sleep(5)
        if len(vc.channel.members) == 1:
            music_queues[member.guild.id] = []
            await vc.disconnect()

def play_next(guild_id, vc):
    if guild_id in music_queues and music_queues[guild_id]:
        song = music_queues[guild_id].pop(0)
        vc.play(discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS), after=lambda e: play_next(guild_id, vc))
    elif vc and vc.is_connected() and len(vc.channel.members) == 1:
        asyncio.run_coroutine_threadsafe(vc.disconnect(), bot.loop)

# --- COMMANDS ---
@bot.tree.command(name="play", description="Play a song")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    if not interaction.user.voice: return await interaction.followup.send("❌ Join a VC first!")
    vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect()
    
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{search}", download=False))
    info = data['entries'][0] if 'entries' in data else data
    
    guild_id = interaction.guild.id
    if guild_id not in music_queues: music_queues[guild_id] = []
    music_queues[guild_id].append({'url': info['url'], 'title': info.get('title')})
    
    if not vc.is_playing(): play_next(guild_id, vc)
    await interaction.followup.send(f"▶️ Playing: `{info.get('title')}`")

@bot.tree.command(name="link", description="Link Steam")
async def link(interaction: discord.Interaction):
    db = load_db()
    if str(interaction.user.id) in db: return await interaction.response.send_message("✅ Already linked!", ephemeral=True)
    await interaction.response.send_message(f"🔗 [Sign In]( {os.getenv('PUBLIC_URL')}/login/{interaction.user.id} )", ephemeral=True)

# --- CORE WEB/STEAM LOGIC ---
async def web_login(request):
    discord_id = request.match_info.get('discord_id')
    base_url = os.getenv("PUBLIC_URL")
    raise web.HTTPFound(f"https://steamcommunity.com/openid/login?openid.ns=http://specs.openid.net/auth/2.0&openid.mode=checkid_setup&openid.return_to={base_url}/verify?discord_id={discord_id}&openid.realm={base_url}&openid.identity=http://specs.openid.net/auth/2.0/identifier_select&openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select")

async def web_verify(request):
    discord_id = request.query.get("discord_id")
    steam_id = request.query.get("openid.claimed_id").split("/id/")[-1]
    db = load_db()
    db[str(discord_id)] = str(steam_id)
    save_db(db)
    return web.Response(text="✅ Linked! Close this tab.", content_type='text/html')

async def fetch_convoy_id():
    async with aiohttp.ClientSession() as session:
        async with session.get(LOGS_URL, cookies={"errors": PANEL_COOKIE} if PANEL_COOKIE else {}) as resp:
            html = await resp.text()
            match = re.search(r"(\d{14,19}/\d{2,3})", html)
            return match.group(1) if match else None

bot.run(TOKEN)
