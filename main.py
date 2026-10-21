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
GIVEAWAYS_FILE = "giveaways.json"
INVITES_CACHE = {}

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
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            INVITES_CACHE[guild.id] = {invite.code: invite.uses for invite in invites}
        except discord.Forbidden:
            pass

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_invite_create(invite):
    if invite.guild.id not in INVITES_CACHE:
        INVITES_CACHE[invite.guild.id] = {}
    INVITES_CACHE[invite.guild.id][invite.code] = invite.uses

@bot.event
async def on_invite_delete(invite):
    if invite.guild.id in INVITES_CACHE and invite.code in INVITES_CACHE[invite.guild.id]:
        del INVITES_CACHE[invite.guild.id][invite.code]

# ==================== ADVANCED GIVEAWAY SYSTEM ====================

@bot.tree.command(name="gstart", description="Start a giveaway (Unit: seconds, minutes, hours, days)")
@app_commands.describe(
    duration="Number of units (e.g. 10)",
    unit="Type: seconds, minutes, hours, or days",
    winners="Number of winners",
    prize="Prize description",
    required_role="Optional role required to enter/win",
    requirements="Optional description of requirements"
)
async def gstart(
    interaction: discord.Interaction, 
    duration: int, 
    unit: str, 
    winners: int, 
    prize: str, 
    required_role: discord.Role = None, 
    requirements: str = None
):
    await interaction.response.defer()
    
    u = unit.lower().strip()
    if u in ["s", "sec", "seconds", "second"]:
        seconds = duration
    elif u in ["m", "min", "minutes", "minute"]:
        seconds = duration * 60
    elif u in ["h", "hr", "hours", "hour"]:
        seconds = duration * 3600
    elif u in ["d", "days", "day"]:
        seconds = duration * 86400
    else:
        seconds = duration * 60

    end_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    timestamp = f"<t:{int(end_time.timestamp())}:R>"

    embed = discord.Embed(title="🎉 GIVEAWAY STARTED! 🎉", color=discord.Color.gold())
    embed.add_field(name="🎁 Prize", value=f"**{prize}**", inline=False)
    embed.add_field(name="👑 Winners", value=str(winners), inline=True)
    embed.add_field(name="⏳ Ends", value=timestamp, inline=True)
    embed.add_field(name="🎙️ Hosted By", value=interaction.user.mention, inline=True)

    if required_role:
        embed.add_field(name="🔒 Required Role", value=required_role.mention, inline=False)
    
    if requirements:
        embed.add_field(name="📜 Requirements", value=requirements, inline=False)

    embed.set_footer(text="React with 🎉 to enter!")

    message = await interaction.followup.send(embed=embed, wait=True)
    await message.add_reaction("🎉")

    giveaways = load_json(GIVEAWAYS_FILE)
    giveaways[str(message.id)] = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "prize": prize,
        "winners": winners,
        "required_role_id": required_role.id if required_role else None,
        "host_id": interaction.user.id
    }
    save_json(GIVEAWAYS_FILE, giveaways)

    await asyncio.sleep(seconds)

    try:
        updated_msg = await interaction.channel.fetch_message(message.id)
    except discord.NotFound:
        return

    reaction = discord.utils.get(updated_msg.reactions, emoji="🎉")
    if not reaction:
        await interaction.channel.send(f"❌ Giveaway for **{prize}** ended, but no reactions were found.")
        return

    raw_users = [user async for user in reaction.users() if not user.bot]
    
    valid_users = []
    for user in raw_users:
        if required_role:
            member = interaction.guild.get_member(user.id)
            if member and required_role in member.roles:
                valid_users.append(user)
        else:
            valid_users.append(user)

    if not valid_users:
        await interaction.channel.send(f"❌ Giveaway for **{prize}** ended, but no entries met the requirement!")
        return

    num_winners = min(len(valid_users), winners)
    winning_users = random.sample(valid_users, num_winners)
    winner_mentions = ", ".join([u.mention for u in winning_users])

    win_embed = discord.Embed(title="🎉 GIVEAWAY ENDED! 🎉", color=discord.Color.green())
    win_embed.add_field(name="🎁 Prize", value=f"**{prize}**", inline=False)
    win_embed.add_field(name="🏆 Winner(s)", value=winner_mentions, inline=False)
    win_embed.add_field(name="🎙️ Hosted By", value=interaction.user.mention, inline=False)
    
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

    giveaways = load_json(GIVEAWAYS_FILE)
    g_data = giveaways.get(str(message_id), {})
    req_role_id = g_data.get("required_role_id")

    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    if not reaction:
        await interaction.followup.send("❌ No `🎉` reactions found on that message.", ephemeral=True)
        return

    raw_users = [user async for user in reaction.users() if not user.bot]
    valid_users = []
    for user in raw_users:
        if req_role_id:
            member = interaction.guild.get_member(user.id)
            if member and any(r.id == req_role_id for r in member.roles):
                valid_users.append(user)
        else:
            valid_users.append(user)

    if not valid_users:
        await interaction.followup.send("❌ No valid user entries found that meet requirements to reroll.", ephemeral=True)
        return

    new_winner = random.choice(valid_users)
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

@bot.tree.command(name="setinvitracker", description="Choose channel for invite tracking alerts")
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

@bot.tree.command(name="setwelcome", description="Choose channel for welcome messages")
@app_commands.checks.has_permissions(manage_channels=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["welcome_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="removewelcome", description="Disable and remove welcome channel")
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

@bot.tree.command(name="setleave", description="Choose channel for leave messages")
@app_commands.checks.has_permissions(manage_channels=True)
async def setleave(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["leave_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Leave channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="removeleave", description="Disable and remove leave channel")
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

@bot.tree.command(name="setlevel", description="Choose channel for level-up announcements")
@app_commands.checks.has_permissions(manage_channels=True)
async def setlevel(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["level_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Level-up channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="enablelevels", description="Turn on server leveling system")
@app_commands.checks.has_permissions(manage_channels=True)
async def enablelevels(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id not in data:
        data[str_guild_id] = {}
    data[str_guild_id]["levels_enabled"] = True
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Leveling system has been **enabled**!", ephemeral=True)

@bot.tree.command(name="disablelevels", description="Turn off server leveling system")
@app_commands.checks.has_permissions(manage_channels=True)
async def disablelevels(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(interaction.guild_id)
    if str_guild_id in data:
        data[str_guild_id]["levels_enabled"] = False
        save_json(CONFIG_FILE, data)
    await interaction.response.send_message("❌ Leveling system has been **disabled**.", ephemeral=True)

# ==================== EVENTS ====================

@bot.event
async def on_member_join(member: discord.Member):
    data = load_json(CONFIG_FILE)
    str_guild_id = str(member.guild.id)
    
    if str_guild_id in data and "welcome_channel" in data[str_guild_id]:
        channel_id = data[str_guild_id]["welcome_channel"]
        channel = member.guild.get_channel(channel_id)
        if channel:
            await channel.send(f"👋 Welcome to the server, {member.mention}! We're glad to have you here.")

    if str_guild_id in data and "invite_channel" in data[str_guild_id]:
        inv_channel = member.guild.get_channel(data[str_guild_id]["invite_channel"])
        if inv_channel:
            cached_invites = INVITES_CACHE.get(member.guild.id, {})
            try:
                new_invites = await member.guild.invites()
                used_invite = None
                for inv in new_invites:
                    if inv.code in cached_invites and inv.uses > cached_invites[inv.code]:
                        used_invite = inv
                        break
                
                INVITES_CACHE[member.guild.id] = {inv.code: inv.uses for inv in new_invites}
                
                if used_invite and used_invite.inviter:
                    await inv_channel.send(f"📩 {member.mention} joined using invite code **{used_invite.code}** from **{used_invite.inviter.mention}** (Total uses: {used_invite.uses})")
                else:
                    await inv_channel.send(f"📩 {member.mention} joined (Invite source unknown/vanity).")
            except discord.Forbidden:
                pass

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

# ==================== PREFIX COMMANDS ====================

@bot.command(name="clear")
async def clear(ctx, amount: int = 5):
    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send("❌ You do not have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 Successfully deleted {len(deleted)} messages.", delete_after=5)

# ==================== MODERATION SLASH COMMANDS ====================
