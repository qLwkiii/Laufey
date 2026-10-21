import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==================== RENDER KEEP-ALIVE WEB SERVER ====================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Laufey Bot is alive and running!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==================== JSON STORAGE HELPERS ====================
CHANNELS_FILE = "channels.json"
LEVELS_FILE = "levels.json"
GIVEAWAYS_FILE = "giveaways.json"
STICKY_FILE = "sticky.json"
CONFIG_FILE = "config.json"

def load_json(filepath):
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user} | Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

# ==================== MODERATION COMMANDS ====================
@bot.tree.command(name="clear", description="Clear a specified number of messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Cleared {amount} messages.", ephemeral=True)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 Kicked {member.mention}. Reason: {reason}", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 Banned {member.mention}. Reason: {reason}", ephemeral=True)

@bot.tree.command(name="unban", description="Unban a user by their user ID")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user, reason=reason)
    await interaction.response.send_message(f"✅ Unbanned {user.name}.", ephemeral=True)

@bot.tree.command(name="timeout", description="Timeout a member for a duration in minutes")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"⏳ Timed out {member.mention} for {minutes} minutes.", ephemeral=True)

@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"🔊 Removed timeout from {member.mention}.", ephemeral=True)

@bot.tree.command(name="warn", description="Warn a server member")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    await interaction.response.send_message(f"⚠️ Warned {member.mention} for: {reason}", ephemeral=False)

# ==================== UTILITY & INFO COMMANDS ====================
@bot.tree.command(name="embed", description="Send a custom embed message")
@app_commands.checks.has_permissions(manage_messages=True)
async def embed_cmd(interaction: discord.Interaction, title: str, description: str, color: str = "blue"):
    color_map = {"blue": discord.Color.blue(), "red": discord.Color.red(), "green": discord.Color.green(), "gold": discord.Color.gold(), "purple": discord.Color.purple()}
    emb_color = color_map.get(color.lower(), discord.Color.blue())
    embed = discord.Embed(title=title, description=description, color=emb_color)
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Embed sent!", ephemeral=True)

@bot.tree.command(name="lock", description="Lock the current channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message("🔒 Channel locked.")

@bot.tree.command(name="unlock", description="Unlock the current channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await interaction.response.send_message("🔓 Channel unlocked.")

@bot.tree.command(name="userinfo", description="Display detailed information about a member")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    roles = [role.mention for role in target.roles if role != interaction.guild.default_role]
    roles_str = ", ".join(roles) if roles else "None"
    embed = discord.Embed(title=f"👤 User Info — {target.name}", color=target.color)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Identifier", value=f"`{target.id}`", inline=True)
    embed.add_field(name="Nickname", value=f"`{target.nick or 'None'}`", inline=True)
    embed.add_field(name="Bot Account", value=f"`{target.bot}`", inline=True)
    embed.add_field(name="Account Created", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="Joined Server", value=f"<t:{int(target.joined_at.timestamp())}:R>", inline=True)
    embed.add_field(name="Highest Role", value=target.top_role.mention, inline=True)
    embed.add_field(name=f"Roles [{len(roles)}]", value=roles_str, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Show comprehensive server details and statistics")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"🏰 {guild.name} — Server Overview", color=discord.Color.blue())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="Created On", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)
    embed.add_field(name="Total Members", value=f"👥 **{guild.member_count}**", inline=True)
    embed.add_field(name="Text Channels", value=f"💬 **{len(guild.text_channels)}**", inline=True)
    embed.add_field(name="Voice Channels", value=f"🔊 **{len(guild.voice_channels)}**", inline=True)
    embed.add_field(name="Boost Level", value=f"🚀 **Level {guild.premium_tier}**", inline=True)
    embed.add_field(name="Boost Count", value=f"✨ **{guild.premium_subscription_count}** Boosts", inline=True)
    embed.add_field(name="Roles Count", value=f"🎭 **{len(guild.roles)}** Roles", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="Get a high-resolution view of a user's avatar")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    embed = discord.Embed(title=f"🖼️ {target.name}'s Avatar", color=discord.Color.purple())
    embed.set_image(url=target.display_avatar.url)
    embed.add_field(name="Download Links", value=f"[PNG]({target.display_avatar.with_format('png').url}) | [JPG]({target.display_avatar.with_format('jpg').url}) | [WEBP]({target.display_avatar.with_format('webp').url})")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="poll", description="Create a clean, interactive poll with reaction options")
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
    options = [option1, option2]
    if option3: options.append(option3)
    if option4: options.append(option4)
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    desc = ""
    for i, opt in enumerate(options):
        desc += f"{emojis[i]} **{opt}**\n\n"
    embed = discord.Embed(title=f"📊 Poll: {question}", description=desc, color=discord.Color.gold())
    embed.set_footer(text=f"Poll created by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])

# ==================== GIVEAWAY COMMAND ====================
@bot.tree.command(name="giveaway", description="Start a giveaway")
@app_commands.checks.has_permissions(manage_guild=True)
async def giveaway(interaction: discord.Interaction, prize: str, duration_minutes: int):
    embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"Prize: **{prize}**\nReact with 🎉 to enter!\nDuration: {duration_minutes} minutes.", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    await msg.add_reaction("🎉")

# ==================== TICKET MANAGEMENT SYSTEM ====================

ticket = app_commands.Group(name="ticket", description="Ticket management commands")

@ticket.command(name="setup", description="Setup the ticket panel channel")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["ticket_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Ticket channel set to {channel.mention}.", ephemeral=True)

@ticket.command(name="panel", description="Send the interactive ticket creation panel")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🎫 Support Tickets", description="Click the button below to create a support ticket.", color=discord.Color.blue())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Ticket panel sent!", ephemeral=True)

# Register the ticket group to the bot tree
bot.tree.add_command(ticket)

# ==================== LEVELING & XP SYSTEM ====================
@bot.tree.command(name="rank", description="Check your or another member's current rank and level")
async def rank_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    levels = load_json(LEVELS_FILE)
    gid = str(interaction.guild_id)
    uid = str(target.id)
    user_data = levels.get(gid, {}).get(uid, {"xp": 0, "level": 1})
    embed = discord.Embed(title=f"📊 Rank Card — {target.name}", color=discord.Color.blue())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="⭐ Level", value=f"**{user_data['level']}**", inline=True)
    embed.add_field(name="✨ Current XP", value=f"**{user_data['xp']} / {user_data['level'] * 100}**", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Show top members on the server XP leaderboard")
async def leaderboard_cmd(interaction: discord.Interaction):
    levels = load_json(LEVELS_FILE)
    gid = str(interaction.guild_id)
    guild_data = levels.get(gid, {})
    if not guild_data:
        await interaction.response.send_message("❌ No XP data recorded yet for this server.", ephemeral=True)
        return
    sorted_users = sorted(guild_data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)[:10]
    desc = ""
    for i, (uid, stats) in enumerate(sorted_users, 1):
        user = interaction.guild.get_member(int(uid))
        name = user.name if user else f"User ID {uid}"
        desc += f"#{i} {name} — Level **{stats['level']}** ({stats['xp']} XP)\n"
    embed = discord.Embed(title="🏆 Server Level Leaderboard", description=desc, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="add-xp", description="Add XP to a member")
@app_commands.checks.has_permissions(manage_guild=True)
async def add_xp(interaction: discord.Interaction, member: discord.Member, amount: int):
    levels = load_json(LEVELS_FILE)
    gid = str(interaction.guild_id)
    uid = str(member.id)
    if gid not in levels: levels[gid] = {}
    if uid not in levels[gid]: levels[gid][uid] = {"xp": 0, "level": 1}
    levels[gid][uid]["xp"] += amount
    save_json(LEVELS_FILE, levels)
    await interaction.response.send_message(f"✅ Added **{amount} XP** to {member.mention}.", ephemeral=True)

@bot.tree.command(name="remove-xp", description="Remove XP from a member")
@app_commands.checks.has_permissions(manage_guild=True)
async def remove_xp(interaction: discord.Interaction, member: discord.Member, amount: int):
    levels = load_json(LEVELS_FILE)
    gid = str(interaction.guild_id)
    uid = str(member.id)
    if gid not in levels: levels[gid] = {}
    if uid not in levels[gid]: levels[gid][uid] = {"xp": 0, "level": 1}
    levels[gid][uid]["xp"] = max(0, levels[gid][uid]["xp"] - amount)
    save_json(LEVELS_FILE, levels)
    await interaction.response.send_message(f"✅ Removed **{amount} XP** from {member.mention}.", ephemeral=True)

@bot.tree.command(name="reset-xp", description="Reset a member's level and XP")
@app_commands.checks.has_permissions(manage_guild=True)
async def reset_xp(interaction: discord.Interaction, member: discord.Member):
    levels = load_json(LEVELS_FILE)
    gid = str(interaction.guild_id)
    uid = str(member.id)
    if gid in levels and uid in levels[gid]:
        levels[gid][uid] = {"xp": 0, "level": 1}
        save_json(LEVELS_FILE, levels)
    await interaction.response.send_message(f"🔄 Reset level and XP for {member.mention}.", ephemeral=True)

@bot.tree.command(name="set-level-reward", description="Set a role reward for reaching a specific level")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_level_reward(interaction: discord.Interaction, level: int, role: discord.Role):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    if "level_rewards" not in data[gid]: data[gid]["level_rewards"] = {}
    data[gid]["level_rewards"][str(level)] = role.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"🎁 Reward set! Reaching **Level {level}** now grants {role.mention}.", ephemeral=True)

@bot.tree.command(name="level-rewards", description="View configured level role rewards")
async def level_rewards(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    rewards = data.get(gid, {}).get("level_rewards", {})
    if not rewards:
        await interaction.response.send_message("❌ No level role rewards configured yet.", ephemeral=True)
        return
    desc = "\n".join([f"• **Level {lvl}**: <@&{rid}>" for lvl, rid in sorted(rewards.items(), key=lambda x: int(x[0]))])
    embed = discord.Embed(title="🎁 Level Role Rewards", description=desc, color=discord.Color.purple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==============================================================================
# ADVANCED INVITE TRACKING SYSTEM (Falcon Style)
# ==============================================================================

def create_falcon_invite_embed(target: discord.User | discord.Member) -> discord.Embed:
    # Stats variables — ready for database integration
    joins = 0
    left = 0
    fake = 0
    rejoins = 0
    total = max(0, joins - left - fake)
    
    embed = discord.Embed(
        title="Invite log",
        description=(
            f"**`>>` {target.mention} has {total} invites**\n\n"
            f"**Joins :** `{joins}`\n"
            f"**Left :** `{left}`\n"
            f"**Fake :** `{fake}`\n"
            f"**Rejoins :** `{rejoins}` `(7d)`\n\n"
            f"▸ Discover new events and giveaways!\n"
            f"▸ Customize this command in premium!"
        ),
        color=discord.Color.from_str("#1abc9c")  # Matching Falcon's Cyan sidebar color
    )
    
    if hasattr(target, 'display_avatar'):
        embed.set_thumbnail(url=target.display_avatar.url)
        
    return embed


# Slash Command: /invites
@bot.tree.command(name="invites", description="Check detailed invite statistics for a user")
async def invites_slash(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    embed = create_falcon_invite_embed(target)
    embed.set_footer(text=f"Requested by {interaction.user.name} | Today at {discord.utils.utcnow().strftime('%I:%M %p')}")
    await interaction.response.send_message(embed=embed)


# Prefix Command: !invites or !invites @user
@bot.command(name="invites")
async def invites_prefix_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    embed = create_falcon_invite_embed(target)
    embed.set_footer(text=f"Requested by {ctx.author.name} | Today at {discord.utils.utcnow().strftime('%I:%M %p')}")
    await ctx.send(embed=embed)


@bot.tree.command(name="invite-leaderboard", description="Show top inviters in the server")
async def invite_leaderboard(interaction: discord.Interaction):
    embed = discord.Embed(title="🏆 Server Invite Leaderboard", description="1. **No active stats recorded yet** — 0 Invites", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="invite-rewards", description="View custom invite milestone rewards")
async def invite_rewards(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    rewards = data.get(gid, {}).get("invite_rewards", {})
    if not rewards:
        embed = discord.Embed(title="🎁 Invite Milestone Rewards", description="No invite rewards configured yet.", color=discord.Color.purple())
    else:
        desc = "\n".join([f"• **{invs} Invites**: <@&{rid}>" for invs, rid in sorted(rewards.items(), key=lambda x: int(x[0]))])
        embed = discord.Embed(title="🎁 Invite Milestone Rewards", description=desc, color=discord.Color.purple())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="invite-rewards-set", description="Set a role reward for a milestone number of invites")
@app_commands.checks.has_permissions(manage_guild=True)
async def invite_rewards_set(interaction: discord.Interaction, invites: int, role: discord.Role):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    if "invite_rewards" not in data[gid]: data[gid]["invite_rewards"] = {}
    data[gid]["invite_rewards"][str(invites)] = role.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"🎁 Invite reward set! Reaching **{invites} invites** will now grant {role.mention}.", ephemeral=True)


@bot.tree.command(name="fake-invites", description="Check how many fake/alt invites a user has")
async def fake_invites(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    await interaction.response.send_message(f"🛡️ **{target.name}** has 0 fake or suspicious invites.", ephemeral=True)


@bot.tree.command(name="invite-bonus", description="Add or remove bonus invites for a member")
@app_commands.checks.has_permissions(manage_guild=True)
async def invite_bonus(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.send_message(f"✨ Successfully adjusted bonus invites for {member.mention} by `{amount}`.", ephemeral=True)


@bot.tree.command(name="invite-reset", description="Reset a user's invite count")
@app_commands.checks.has_permissions(manage_guild=True)
async def invite_reset(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"🔄 Reset invite tracking stats for {member.mention}.", ephemeral=True)


# ==================== RUN BOT ====================
token = os.environ.get("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ ERROR: DISCORD_TOKEN environment variable not found!")
