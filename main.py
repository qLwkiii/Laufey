import os
import json
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import datetime
import re

import discord
from discord import app_commands
from discord.ext import commands

# ==========================================
# 1. RENDER / HOSTING KEEP-ALIVE WEB SERVER
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
    print("Ready and synced slash commands!")

def parse_time_duration(time_str: str) -> datetime.timedelta:
    match = re.match(r"^(\d+)([smhd])$", time_str.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 's': return datetime.timedelta(seconds=value)
    if unit == 'm': return datetime.timedelta(minutes=value)
    if unit == 'h': return datetime.timedelta(hours=value)
    if unit == 'd': return datetime.timedelta(days=value)
    return None

# ==========================================
# MODERATION & UTILITY COMMANDS (18 TOTAL)
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
        await interaction.response.send_message(f"❌ Failed to unban. Check if the User ID is valid. Error: {e}", ephemeral=True)

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

# 5. Timeout
@bot.tree.command(name="timeout", description="Timeouts a user (e.g., 30s, 15m, 2h, 1d).")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
    delta = parse_time_duration(duration)
    if not delta:
        await interaction.response.send_message("❌ Invalid format! Use a number followed by s, m, h, or d (e.g., `10m`, `2h`).", ephemeral=True)
        return
    until = datetime.datetime.utcnow() + delta
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(f"🔇 Timed out **{member}** for **{duration}**. Reason: {reason}")

# 6. Untimeout
@bot.tree.command(name="untimeout", description="Removes a timeout from a user early.")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.timeout(None, reason=reason)
    await interaction.response.send_message(f"🔊 Removed timeout for **{member}**.")

# 7. Warn (Saved to JSON)
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
        await interaction.response.send_message(f"ℹ️ **{member}** has no active warnings.", ephemeral=True)
        return
    
    reasons = "\n".join([f"**#{i+1}**: {r}" for i, r in enumerate(warning_database[user_id])])
    embed = discord.Embed(title=f"Warnings for {member}", description=reasons, color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

# 9. Delwarn (New: Delete specific warning number)
@bot.tree.command(name="delwarn", description="Deletes a specific warning number from a user's record.")
@app_commands.checks.has_permissions(manage_messages=True)
async def delwarn(interaction: discord.Interaction, member: discord.Member, warn_index: int):
    user_id = str(member.id)
    if user_id in warning_database and 0 < warn_index <= len(warning_database[user_id]):
        removed = warning_database[user_id].pop(warn_index - 1)
        save_warnings(warning_database)
        await interaction.response.send_message(f"🗑️ Removed warning #{warn_index} (`{removed}`) for **{member}**.")
    else:
        await interaction.response.send_message("❌ Invalid warning number or user has no warnings.", ephemeral=True)

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
        await interaction.response.send_message(f"ℹ️ **{member}** has no warnings to clear.", ephemeral=True)

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
@bot.tree.command(name="purge", description="Deletes a specific number of messages, optionally filtered by user.")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int, member: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    if member:
        def check(m): return m.author == member
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(f"🗑️ Deleted {len(deleted)} messages from **{member}**.", ephemeral=True)
    else:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Successfully deleted {len(deleted)} messages.", ephemeral=True)

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

# 16. Userinfo (New)
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

# 17. Serverinfo
@bot.tree.command(name="serverinfo", description="Displays basic information about the server.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.blue())
    embed.add_field(name="Owner", value=guild.owner, inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Created On", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    await interaction.response.send_message(embed=embed)

# 18. Ping
@bot.tree.command(name="ping", description="Checks the bot's latency.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"pong! 🏓 Latency is `{latency}ms`.")

# Error handling
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You do not have the required permissions to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ An error occurred: {error}", ephemeral=True)

bot.run("YOUR_BOT_TOKEN_HERE")
