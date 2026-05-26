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

GUILD_ID = 1508575872976949411  
SERVER_OBJ = discord.Object(id=GUILD_ID)

# --- LOCAL STORAGE DATABASE (PERSISTENT) ---
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
    'default_search': 'ytsearch', 
    'source_address': '0.0.0.0',
    'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
}

if os.path.exists("cookies.txt"):
    YTDL_OPTIONS['cookiefile'] = 'cookies.txt'
elif os.path.exists("www.youtube.com_cookies.txt"):
    YTDL_OPTIONS['cookiefile'] = 'www.youtube.com_cookies.txt'

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -sn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# --- THE BOT CLASS ---
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

# --- AUTO-DISCONNECT MONITOR ---
@bot.event
async def on_voice_state_update(member, before, after):
    # If the bot is in a voice channel
    voice_client = member.guild.voice_client
    if voice_client and voice_client.channel:
        # Check if the channel is empty (only the bot left)
        if len(voice_client.channel.members) == 1 and voice_client.channel.members[0] == bot.user:
            await asyncio.sleep(5) # Wait 5 seconds to ensure no one is re-joining
            if len(voice_client.channel.members) == 1:
                music_queues[member.guild.id] = []
                await voice_client.disconnect()

# --- MUSIC PLAYER LOGIC ---
def play_next(guild_id, vc):
    if guild_id in music_queues and len(music_queues[guild_id]) > 0:
        song = music_queues[guild_id].pop(0)
        vc.play(discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS), after=lambda e: play_next(guild_id, vc))
    else:
        # Only auto-disconnect if the channel is already empty
        if vc and vc.is_connected() and len(vc.channel.members) == 1:
            asyncio.run_coroutine_threadsafe(vc.disconnect(), bot.loop)

# ( ... keep your resolve_steam_user, web_login, web_verify, and command functions exactly as they were ... )

# Keep all existing commands (/play, /link, /steamid, etc) here below.
# I have omitted them in this snippet to keep it clean, just append them to the end of the file.

if __name__ == "__main__":
    bot.run(TOKEN)
