import discord
from discord import app_commands
from discord.ext import commands
import datetime
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from deep_translator import MyMemoryTranslator

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

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Configuration Storage (channels.json & levels.json) ---
CONFIG_FILE = "channels.json"
LEVELS_FILE = "levels.json"

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
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# ==================== PREFIX COMMANDS ====================

@bot.command(name="translate")
async def translate_prefix(ctx, language: str, *, text: str):
    """Usage: !translate spanish hello how are you"""
    try:
        # Translate text
        translator = MyMemoryTranslator(source='auto', target=language.lower())
        translated_text = translator.translate(text)
        
        embed = discord.Embed(title="🌐 Translation Result", color=discord.Color.blue())
        embed.add_field(name="Original Text", value=text, inline=False)
        embed.add_field(name=f"Translated ({language.capitalize()})", value=translated_text, inline=False)
        embed.set_footer(text=f"Requested by {ctx.author.name}")
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Failed to translate. Make sure you typed a valid target language first.\nExample: `!translate spanish hello how are you`\nError: `{e}`")

@translate_prefix.error
async def translate_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("⚠️ Usage format: `!translate <language> <text>`\nExample: `!translate french Hello world`", delete_after=10)

@bot.command(name="clear")
async def clear(ctx, amount: int = 5):
    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send("❌ You do not have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 Successfully deleted {len(deleted)} messages.", delete_after=5)

@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("⚠️ Please specify how many messages to clear, e.g., `!clear 10`", delete_after=5)

# ==================== SETUP & CONFIG SLASH COMMANDS ====================

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
async def setleave(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["leave_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Leave channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="removeleave", description="Disable and remove the leave channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def removeleave(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id in data and "leave_channel" in data[str_guild_id]:
        del data[str_guild_id]["leave_channel"]
        save_json(CONFIG_FILE, data)
        await interaction.response.send_message("✅ Leave messages have been disabled.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ No leave channel is currently set.", ephemeral=True)

@bot.tree.command(name="setlevel", description="Choose the channel for level-up announcements")
@app_commands.checks.has_permissions(manage_channels=True)
async def setlevel(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["level_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Level-up channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="enablelevels", description="Turn on the server leveling system")
@app_commands.checks.has_permissions(manage_channels=True)
async def enablelevels(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["levels_enabled"] = True
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Leveling system has been **enabled**!", ephemeral=True)

@bot.tree.command(name="disablelevels", description="Turn off and disable the server leveling system")
@app_commands.checks.has_permissions(manage_channels=True)
async def disablelevels(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id in data:
        data[str_guild_id]["levels_enabled"] = False
        save_json(CONFIG_FILE, data)
    await interaction.response.send_message("❌ Leveling system has been **disabled**.", ephemeral=True)

# ==================== EVENTS (Welcome, Leave & Levels) ====================

@bot.event
async def on_member_join(member: discord.Member):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(member.guild.id)
    if str_guild_id in data and "welcome_channel" in data[str_guild_id]:
        channel_id = data[str_guild_id]["welcome_channel"]
        channel = member.guild.get_channel(channel_id)
        if channel:
            await channel.send(f"👋 Welcome to the server, {member.mention}! We're glad to have you here.")

@bot.event
async def on_member_remove(member: discord.Member):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(member.guild.id)
    if str_guild_id in data and "leave_channel" in data[str_guild_id]:
        channel_id = data[str_guild_id]["leave_channel"]
        channel = member.guild.get_channel(channel_id)
        if channel:
            await channel.send(f"👋 **{member.name}** has left the server.")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    config_data = load_json(CONFIG_FILE)
    guild_id = str(message.guild.id)
    
    if guild_id in config_data and config_data[guild_id].get("levels_enabled", False):
        levels_data = load_json(LEVELS_FILE)
        user_id = str(message.author.id)

        if guild_id not in levels_data:
            levels_data[guild_id] = {}
        if user_id not in levels_data[guild_id]:
            levels_data[guild_id][user_id] = {"xp": 0, "level": 1}

        user_data = levels_data[guild_id][user_id]
        user_data["xp"] += 10
        
        next_level_xp = user_data["level"] * 100
        if user_data["xp"] >= next_level_xp:
            user_data["level"] += 1
            user_data["xp"] = 0
            
            announcement_channel = message.channel
            if "level_channel" in config_data[guild_id]:
                custom_chan = message.guild.get_channel(config_data[guild_id]["level_channel"])
                if custom_chan:
                    announcement_channel = custom_chan

            await announcement_channel.send(f"🎉 Congrats {message.author.mention}, you leveled up to **Level {user_data['level']}**!")

        save_json(LEVELS_FILE, levels_data)

    await bot.process_commands(message)

# ==================== MODERATION SLASH COMMANDS ====================

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer()
    await member.kick(reason=reason)
    await interaction.followup.send(f"✅ {member.mention} was kicked. Reason: {reason}")

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer()
    await member.ban(reason=reason)
    await interaction.followup.send(f"⛔ {member.mention} was banned. Reason: {reason}")

@bot.tree.command(name="timeout", description="Timeout a member for a set duration and unit")
@app_commands.choices(unit=[
    app_commands.Choice(name="Seconds", value="seconds"),
    app_commands.Choice(name="Minutes", value="minutes"),
    app_commands.Choice(name="Hours", value="hours"),
    app_commands.Choice(name="Days", value="days")
])
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int, unit: str, reason: str = "No reason provided"):
    await interaction.response.defer()
    
    if unit == "seconds":
        delta = datetime.timedelta(seconds=duration)
    elif unit == "minutes":
        delta = datetime.timedelta(minutes=duration)
    elif unit == "hours":
        delta = datetime.timedelta(hours=duration)
    elif unit == "days":
        delta = datetime.timedelta(days=duration)
    else:
        delta = datetime.timedelta(minutes=duration)

    await member.timeout(delta, reason=reason)
    await interaction.followup.send(f"🔇 {member.mention} has been timed out for {duration} {unit}. Reason: {reason}")

@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    await member.timeout(None)
    await interaction.followup.send(f"🔊 Timeout removed for {member.mention}.")

@bot.tree.command(name="warn", description="Issue a warning to a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer()
    try:
        await member.send(f"⚠️ You have been warned in **{interaction.guild.name}**. Reason: {reason}")
    except discord.Forbidden:
        pass
    await interaction.followup.send(f"⚠️ {member.mention} has been warned. Reason: {reason}")

# Error Handler
@kick.error
@ban.error
@timeout.error
@untimeout.error
@warn.error
@setwelcome.error
@removewelcome.error
@setleave.error
@removeleave.error
@setlevel.error
@enablelevels.error
@disablelevels.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        else:
            await interaction.followup.send("❌ You do not have permission to use this command.", ephemeral=True)

bot.run(os.environ.get("DISCORD_TOKEN"))
