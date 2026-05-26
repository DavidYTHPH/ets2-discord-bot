import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
import os
import re
import json
import requests
import random

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
PENDING_VERIFICATIONS = {} # Memory cache for generated codes

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

# --- UTILITY ENGINES ---
def resolve_steam_user_by_name(name_string):
    if not STEAM_API_KEY: return {"error": "Steam API Key is missing in Railway variables."}
    
    clean_input = str(name_string).strip().rstrip('/')
    if "steamcommunity.com/id/" in clean_input:
        clean_input = clean_input.split("/id/")[-1]
    elif "steamcommunity.com/profiles/" in clean_input:
        clean_input = clean_input.split("/profiles/")[-1]

    if re.match(r"^\d{17}$", clean_input):
        steam_id_64 = clean_input
    else:
        url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={clean_input}"
        try:
            res = requests.get(url, timeout=10).json()
            if res.get("response", {}).get("success") == 1:
                steam_id_64 = res["response"]["steamid"]
            else:
                return {"error": f"Could not find a public Steam profile matching: `{name_string}`"}
        except:
            return {"error": "Failed to communicate with Steam servers."}
            
    return fetch_profile_summary(steam_id_64)

def fetch_profile_summary(steam_id_64):
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
            "bio": player_data.get("summary", ""),
            "id64": str(steam_id_64),
            "id3": steam_id_3
        }
    except:
        return {"error": "Error reading Steam data."}

def build_steam_embed(result):
    embed = discord.Embed(title=f"👤 Steam Account: {result['name']}", url=result["url"], color=discord.Color.blue())
    embed.set_thumbnail(url=result["avatar"])
    embed.add_field(name="🌐 SteamID64 (Default format)", value=f"`{result['id64']}`", inline=False)
    embed.add_field(name="🆔 SteamID3 (Config/Server format)", value=f"`{result['id3']}`", inline=False)
    return embed

# --- BOT INTERFACE ---
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
    from main import fetch_convoy_id # Local encapsulation mapping
    loop = asyncio.get_event_loop()
    current_id = await loop.run_in_executor(None, fetch_convoy_id)
    if current_id:
        embed = discord.Embed(title="🚚 Live Convoy Status", description=f"**Search ID:** `{current_id}`", color=discord.Color.green())
        await interaction.followup.send(embed=embed)
    else:
        embed = discord.Embed(title="⚠️ Convoy ID Not Found", description="Server is currently offline.", color=discord.Color.red())
        await interaction.followup.send(embed=embed)

# --- COMMAND 2: INTERACTIVE BIO VERIFICATION LINK ENGINE ---
@bot.tree.command(name="link", description="Securely verify and pair your identity to your Steam profile account.")
@app_commands.describe(steam_profile_name="Enter your custom Steam profile URL link, username text, or 64-bit ID string.")
async def link(interaction: discord.Interaction, steam_profile_name: str):
    await interaction.response.defer(ephemeral=True)
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, resolve_steam_user_by_name, steam_profile_name)
    
    if "error" in result:
        await interaction.followup.send(content=f"❌ Initialization failed: {result['error']}", ephemeral=True)
        return
        
    # Generate a completely secure 6-digit pin verification sequence key string
    verification_pin = f"ETS2-{random.randint(100000, 999999)}"
    PENDING_VERIFICATIONS[interaction.user.id] = {"steam_id": result["id64"], "pin": verification_pin}
    
    embed = discord.Embed(
        title="🔒 Steam Profile Identity Verification Step",
        description=(
            f"Hey {interaction.user.mention}! To securely verify that you own **{result['name']}**:\n\n"
            f"1. Open your browser or your Steam application on your desktop PC.\n"
            f"2. Go to your **Edit Profile** layout settings page.\n"
            f"3. Copy and paste your secure verification code below into your profile **Summary / About Me** bio text box area:\n\n"
            f"👉 **`{verification_pin}`**\n\n"
            f"4. Click **Save Changes** on Steam, return right here, and click the green **Confirm Verification** button below!"
        ),
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=result["avatar"])
    embed.set_footer(text="This security verification step ensures players cannot impersonate other drivers.")
    
    class ConfirmVerificationView(discord.ui.View):
        def __init__(self, user_id):
            super().__init__(timeout=300)
            self.user_id = user_id
            
        @discord.ui.button(label="✅ Confirm Verification Changes", style=discord.ButtonStyle.green)
        async def verify_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
            if btn_interaction.user.id != self.user_id:
                await btn_interaction.response.send_message("You cannot complete another member's tracking sequence!", ephemeral=True)
                return
                
            await btn_interaction.response.defer(ephemeral=True)
            user_data = PENDING_VERIFICATIONS.get(self.user_id)
            
            if not user_data:
                await btn_interaction.followup.send("❌ Setup session has timed out. Please execute the `/link` command layout loop again!", ephemeral=True)
                return
                
            # Scan their profile summaries live to check for the validation code token matches
            profile_check = await loop.run_in_executor(None, fetch_profile_summary, user_data["steam_id"])
            
            if "error" in profile_check:
                await btn_interaction.followup.send(content=f"❌ Sync verification check failed: {profile_check['error']}", ephemeral=True)
                return
                
            if user_data["pin"] in profile_check["bio"]:
                db = load_db()
                db[str(self.user_id)] = user_data["steam_id"]
                save_db(db)
                
                # Delete memory tracking token keys
                PENDING_VERIFICATIONS.pop(self.user_id, None)
                
                await btn_interaction.followup.send(
                    content="🎉 Identity verified successfully! You can safely delete the verification pin out of your Steam bio now.",
                    embed=build_steam_embed(profile_check),
                    ephemeral=True
                )
            else:
                await btn_interaction.followup.send(
                    content=(
                        f"❌ Verification mismatch! I could not detect the verification token string code value inside your Bio summary text yet.\n\n"
                        f"**Current detected Steam bio summary text contains:**\n"
                        f"`{profile_check['bio'] if profile_check['bio'] else '[Your Steam Bio is Empty]'}`\n\n"
                        f"Please verify you have saved your edits on Steam containing code **`{user_data['pin']}`** and click confirm again!"
                    ),
                    ephemeral=True
                )
                
    await interaction.followup.send(embed=embed, view=ConfirmVerificationView(interaction.user.id), ephemeral=True)

# --- COMMAND 3: TRACK PASSENGER CARD DATA LAYOUT MAPPING ---
@bot.tree.command(name="steamid", description="Look up a server member's authenticated profile details seamlessly.")
@app_commands.describe(target_member="Tag a user in this server (e.g. @DAVIDYTHPH) to fetch their secure profile data card.")
async def steamid(interaction: discord.Interaction, target_member: discord.Member = None):
    await interaction.response.defer(ephemeral=False)
    
    db = load_db()
    search_user = target_member if target_member else interaction.user
    user_key = str(search_user.id)
    
    if user_key in db:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, fetch_profile_summary, db[user_key])
        if "error" in result:
            await interaction.followup.send(embed=discord.Embed(title="❌ Search Failed", description=result["error"], color=discord.Color.red()))
        else:
            await interaction.followup.send(embed=build_steam_embed(result))
    else:
        await interaction.followup.send(embed=discord.Embed(
            title="⚠️ Authenticated Profile Not Found",
            description=(
                f"This driver hasn't verified their profile tracking parameters yet.\n\n"
                f"💡 **To fix this:** Have {search_user.mention} run the `/link` command inside the channel chat window "
                f"to link their Steam ID securely to our server data systems!"
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

if __name__ == "__main__":
    bot.run(TOKEN)
