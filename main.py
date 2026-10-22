import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import datetime

import discord
from discord import app_commands
from discord.ext import commands

# ==========================================
# 1. KEEP-ALIVE WEB SERVER (Background Thread)
# ==========================================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Laufey Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. DISCORD BOT INITIALIZATION & JSON DATA
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

WARNINGS_FILE = "warnings.json"

def load_warnings():
    if os.path.exists(WARNINGS_FILE):
        try:
            with open(WARNINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_warnings(data):
    with open(WARNINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

warning_database = load_warnings()

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Ready and synced public slash commands!")


# ==========================================
# ALL 18 MODERATION & UTILITY COMMANDS (PUBLIC)
# ==========================================

# 1. Ban
@bot.tree.command(name="ban", description="Permanently bans a user from the server.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_message_days: int = 0):
    await member.ban(reason=reason, delete_message_days=delete_message_days)
    await interaction.response.send_message(f"🔨 Successfully banned **{member}**. Reason: {reason}")

# 2. Unban
@bot.tree.command(name="unban", description="Lifts a ban using a User ID.")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        await interaction.response.send_message(f"✅ Successfully unbanned **{user}**. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to unban. Check if the User ID is valid. Error: {e}")

# 3. Softban
@bot.tree.command(name="softban", description="Bans and unbans a user to clear their recent messages.")
@app_commands.checks.has_permissions(ban_members=True)
async def softban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.guild.ban(member, reason=reason, delete_message_days=1)
    await interaction.guild.unban(member, reason=f"Softban cleanup: {reason}")
    await interaction.response.send_message(f"🧹 Softbanned **{member}** to clear their messages. Reason: {reason}")

# 4. Kick
@bot.tree.command(name="kick", description="Kicks a user from the server.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 Successfully kicked **{member}**. Reason: {reason}")

# 5. Timeout (Clickable Dropdown Units)
@bot.tree.command(name="timeout", description="Timeouts a user with clickable units.")
@app_commands.choices(unit=[
    app_commands.Choice(name="Seconds", value="s"),
    app_commands.Choice(name="Minutes", value="m"),
    app_commands.Choice(name="Hours", value="h"),
    app_commands.Choice(name="Days", value="d"),
    app_commands.Choice(name="Weeks", value="w"),
    app_commands.Choice(name="Months", value="mo")
])
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, amount: int, unit: app_commands.Choice[str], reason: str = "No reason provided"):
    seconds_multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "mo": 2592000}
    total_seconds = amount * seconds_multiplier.get(unit.value, 1)
    
    delta = datetime.timedelta(seconds=total_seconds)
    until = discord.utils.utcnow() + delta
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(f"🔇 Timed out **{member}** for {amount} {unit.name}. Reason: {reason}")

# 6. Untimeout
@bot.tree.command(name="untimeout", description="Removes a timeout from a user early.")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.timeout(None, reason=reason)
    await interaction.response.send_message(f"🔊 Removed timeout for **{member}**.")

# 7. Warn
@bot.tree.command(name="warn", description="Issues a recorded warning to a user.")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    user_id = str(member.id)
    if user_id not in warning_database:
        warning_database[user_id] = []
    warning_database[user_id].append(reason)
    save_warnings(warning_database)
    await interaction.response.send_message(f"⚠️ Warned **{member}**. Total warnings: {len(warning_database[user_id])}. Reason: {reason}")

# 8. Warnings
@bot.tree.command(name="warnings", description="Views all recorded warnings for a user.")
@app_commands.checks.has_permissions(manage_messages=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    user_id = str(member.id)
    if user_id not in warning_database or not warning_database[user_id]:
        await interaction.response.send_message(f"ℹ️ **{member}** has no active warnings.")
        return
    
    reasons = "\n".join([f"**#{i+1}**: {r}" for i, r in enumerate(warning_database[user_id])])
    embed = discord.Embed(title=f"Warnings for {member}", description=reasons, color=discord.Color.orange())
    await interaction.response.send_message(embed=embed)

# 9. Delwarn
@bot.tree.command(name="delwarn", description="Deletes a specific warning number from a user's record.")
@app_commands.checks.has_permissions(manage_messages=True)
async def delwarn(interaction: discord.Interaction, member: discord.Member, warn_index: int):
    user_id = str(member.id)
    if user_id in warning_database and 0 < warn_index <= len(warning_database[user_id]):
        removed = warning_database[user_id].pop(warn_index - 1)
        save_warnings(warning_database)
        await interaction.response.send_message(f"🗑️ Removed warning #{warn_index} (`{removed}`) for **{member}**.")
    else:
        await interaction.response.send_message("❌ Invalid warning number or user has no warnings.")

# 10. Clearwarns
@bot.tree.command(name="clearwarns", description="Clears all warning records for a user.")
@app_commands.checks.has_permissions(manage_messages=True)
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    user_id = str(member.id)
    if user_id in warning_database:
        del warning_database[user_id]
        save_warnings(warning_database)
        await interaction.response.send_message(f"🧹 Cleared all warnings for **{member}**.")
    else:
        await interaction.response.send_message(f"ℹ️ **{member}** has no warnings to clear.")

# 11. Lock
@bot.tree.command(name="lock", description="Locks the current channel so members cannot send messages.")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message("🔒 Channel has been locked.")

# 12. Unlock
@bot.tree.command(name="unlock", description="Unlocks the current channel.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await interaction.response.send_message("🔓 Channel has been unlocked.")

# 13. Purge
@bot.tree.command(name="purge", description="Deletes an exact number of messages, optionally filtered by user.")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int, member: discord.Member = None):
    await interaction.response.defer()
    if member:
        deleted = []
        async for msg in interaction.channel.history(limit=200):
            if msg.author == member:
                deleted.append(msg)
                if len(deleted) == amount:
                    break
        if deleted:
            await interaction.channel.delete_messages(deleted)
        await interaction.followup.send(f"🗑️ Successfully deleted {len(deleted)} messages from **{member}**.")
    else:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Successfully deleted {len(deleted)} messages.")

# 14. Slowmode
@bot.tree.command(name="slowmode", description="Sets a slowmode delay for the channel in seconds (0 to disable).")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    await interaction.channel.edit(slowmode_delay=seconds)
    if seconds == 0:
        await interaction.response.send_message("⏱️ Slowmode has been disabled.")
    else:
        await interaction.response.send_message(f"⏱️ Slowmode set to {seconds} seconds.")

# 15. Nick
@bot.tree.command(name="nick", description="Changes a member's server nickname.")
@app_commands.checks.has_permissions(manage_nicknames=True)
async def nick(interaction: discord.Interaction, member: discord.Member, new_nickname: str = None):
    await member.edit(nick=new_nickname)
    if new_nickname:
        await interaction.response.send_message(f"✏️ Changed nickname for **{member}** to `{new_nickname}`.")
    else:
        await interaction.response.send_message(f"✏️ Cleared nickname for **{member}**.")

# 16. Userinfo
@bot.tree.command(name="userinfo", description="Displays detailed information about a member.")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    roles = [role.mention for role in target.roles if role != interaction.guild.default_role]
    
    embed = discord.Embed(title=f"User Info - {target}", color=target.color)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="User ID", value=target.id, inline=True)
    embed.add_field(name="Joined Server", value=target.joined_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Account Created", value=target.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles) if roles else "None", inline=False)
    
    await interaction.response.send_message(embed=embed)

# 17. Serverinfo (Formatted exactly like your reference image)[span_1](start_span)[span_1](end_span)
@bot.tree.command(name="serverinfo", description="Displays detailed server information.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    
    created_str = guild.created_at.strftime("%B %d, %Y %I:%M %p")
    
    embed = discord.Embed(title="📊 Server Information", color=discord.Color.from_rgb(40, 160, 200))
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
        
    embed.description = guild.description if guild.description else "No description set.[span_2](start_span)"[span_2](end_span)
    
    embed.add_field(
        name="📜 General Info",
        value=f"**Name:** {guild.name}\n**Server ID:** {guild.id}\n**Owner:** {guild.owner.mention}\n**Created:** {created_str}",
        inline=False
    )
    
    embed.add_field(
        name="👥 Members & Roles",
        value=f"**Members:** {guild.member_count}\n**Roles:** {len(guild.roles)}\n**Verification Level:** {str(guild.verification_level).capitalize()}",
        inline=False
    )
    
    embed.add_field(
        name="💎 Boost Status",
        value=f"**Level:** {guild.premium_tier}\n**Boosts:** {guild.premium_subscription_count}\n**AFK Timeout:** {guild.afk_timeout} sec",
        inline=False
    )
    
    embed.add_field(
        name="📁 Channels",
        value=f"**Text:** {text_channels}\n**Voice:** {voice_channels}\n**Categories:** {categories}",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

# 18. Ping
@bot.tree.command(name="ping", description="Checks the bot's latency.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! 🏓 Latency is `{latency}ms`.")

# Error handling
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You do not have the required permissions to use this command.")
    else:
        await interaction.response.send_message(f"❌ An error occurred: {error}")

# Run bot securely
bot.run(os.environ.get("DISCORD_TOKEN"))
