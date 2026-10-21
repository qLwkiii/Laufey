import discord
from discord import app_commands
from discord.ext import commands
import datetime
import os
import json
import asyncio
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# --- Tiny Web Server to satisfy Render's port requirement ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Laufey Bot is alive and running!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()
# -------------------------------------------------------------

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.invites = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Configuration & Storage ---
CONFIG_FILE = "channels.json"
LEVELS_FILE = "levels.json"
INVITES_CACHE = {}  # {guild_id: {invite_code: uses}}

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    
    # Cache all server invites on startup for tracking
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            INVITES_CACHE[guild.id] = {invite.code: invite.uses for invite in invites}
        except discord.Forbidden:
            print(f"Missing Manage Server permissions to fetch invites in {guild.name}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# Cache invite changes when new invites are created/deleted
@bot.event
async def on_invite_create(invite):
    if invite.guild.id not in INVITES_CACHE:
        INVITES_CACHE[invite.guild.id] = {}
    INVITES_CACHE[invite.guild.id][invite.code] = invite.uses

@bot.event
async def on_invite_delete(invite):
    if invite.guild.id in INVITES_CACHE and invite.code in INVITES_CACHE[invite.guild.id]:
        del INVITES_CACHE[invite.guild.id][invite.code]

# ==================== GIVEAWAY SYSTEM ====================

@bot.tree.command(name="gstart", description="Start a giveaway")
@app_commands.checks.has_permissions(manage_events=True)
@app_commands.choices(unit=[
    app_commands.Choice(name="Seconds", value="seconds"),
    app_commands.Choice(name="Minutes", value="minutes"),
    app_commands.Choice(name="Hours", value="hours"),
    app_commands.Choice(name="Days", value="days")
])
async def gstart(interaction: discord.Interaction, duration: int, unit: str, winners: int, prize: str):
    await interaction.response.defer()
    
    # Convert duration to seconds
    if unit == "seconds":
        seconds = duration
    elif unit == "minutes":
        seconds = duration * 60
    elif unit == "hours":
        seconds = duration * 3600
    elif unit == "days":
        seconds = duration * 86400
    else:
        seconds = duration * 60

    end_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    timestamp = f"<t:{int(end_time.timestamp())}:R>"

    embed = discord.Embed(title="🎉 GIVEAWAY STARTED! 🎉", description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** {timestamp}\n**Hosted by:** {interaction.user.mention}", color=discord.Color.gold())
    embed.set_footer(text="React with 🎉 to enter!")

    message = await interaction.followup.send(embed=embed, wait=True)
    await message.add_reaction("🎉")

    await asyncio.sleep(seconds)

    # Fetch updated message to check reactions
    try:
        updated_msg = await interaction.channel.fetch_message(message.id)
    except discord.NotFound:
        return  # Giveaway was deleted or canceled

    reaction = discord.utils.get(updated_msg.reactions, emoji="🎉")
    if not reaction:
        await interaction.channel.send(f"❌ Giveaway for **{prize}** ended, but no reactions were found.")
        return

    users = [user async for user in reaction.users() if not user.bot]
    if not users:
        await interaction.channel.send(f"❌ Giveaway for **{prize}** ended, but no valid entries were made.")
        return

    num_winners = min(len(users), winners)
    winning_users = random.sample(users, num_winners)
    winner_mentions = ", ".join([u.mention for u in winning_users])

    win_embed = discord.Embed(title="🎉 GIVEAWAY ENDED! 🎉", description=f"**Prize:** {prize}\n**Winners:** {winner_mentions}\n**Hosted by:** {interaction.user.mention}", color=discord.Color.green())
    await updated_msg.edit(embed=win_embed)
    await interaction.channel.send(f"🎊 Congratulations {winner_mentions}! You won **{prize}**!")

@bot.tree.command(name="greroll", description="Reroll winners for a giveaway message ID")
@app_commands.checks.has_permissions(manage_events=True)
async def greroll(interaction: discord.Interaction, message_id: str):
    await interaction.response.defer()
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
    except (discord.NotFound, ValueError):
        await interaction.followup.send("❌ Could not find a message with that ID in this channel.", ephemeral=True)
        return

    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    if not reaction:
        await interaction.followup.send("❌ No `🎉` reactions found on that message.", ephemeral=True)
        return

    users = [user async for user in reaction.users() if not user.bot]
    if not users:
        await interaction.followup.send("❌ No valid user entries found to reroll.", ephemeral=True)
        return

    new_winner = random.choice(users)
    await interaction.followup.send(f"🎉 New Winner Rerolled: {new_winner.mention}! Congratulations!")

@bot.tree.command(name="gstop", description="Cancel and stop an active giveaway")
@app_commands.checks.has_permissions(manage_events=True)
async def gstop(interaction: discord.Interaction, message_id: str):
    await interaction.response.defer()
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
        cancel_embed = discord.Embed(title="🛑 GIVEAWAY CANCELED 🛑", description="This giveaway has been canceled by an administrator.", color=discord.Color.red())
        await msg.edit(embed=cancel_embed)
        await interaction.followup.send("✅ Giveaway canceled successfully.", ephemeral=True)
    except (discord.NotFound, ValueError):
        await interaction.followup.send("❌ Could not find a message with that ID in this channel.", ephemeral=True)

# ==================== INVITE TRACKER COMMANDS ====================

@bot.tree.command(name="setinvitracker", description="Choose the channel for invite tracking alerts")
@app_commands.checks.has_permissions(manage_channels=True)
async def setinvitracker(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["invite_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Invite tracking channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="removeinvitracker", description="Disable and stop invite tracking")
@app_commands.checks.has_permissions(manage_channels=True)
async def removeinvitracker(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id in data and "invite_channel" in data[str_guild_id]:
        del data[str_guild_id]["invite_channel"]
        save_json(CONFIG_FILE, data)
        await interaction.response.send_message("✅ Invite tracking has been disabled.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ No invite tracker channel is currently set.", ephemeral=True)

# ==================== SETUP & CONFIG COMMANDS ====================

@bot.tree.command(name="setwelcome", description="Choose the channel for welcome messages")
@app_commands.checks.has_permissions(manage_channels=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["welcome_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="removewelcome", description="Disable and remove the welcome channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def removewelcome(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id in data and "welcome_channel" in data[str_guild_id]:
        del data[str_guild_id]["welcome_channel"]
        save_json(CONFIG_FILE, data)
        await interaction.response.send_message("✅ Welcome messages have been disabled.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ No welcome channel is currently set.", ephemeral=True)

@bot.tree.command(name="setleave", description="Choose the channel for leave messages")
@app_commands.checks.has_permissions(manage_channels=True)
async def setleave(interaction: discord.
