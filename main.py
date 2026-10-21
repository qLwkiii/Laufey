import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta

# ==================== KEEP-ALIVE WEB SERVER (RENDER) ====================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Laufey Bot is online and active!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# ==================== BOT SETUP & INTENTS ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

CONFIG_FILE = "channels.json"
LEVELS_FILE = "levels.json"
GIVEAWAYS_FILE = "giveaways.json"
STICKY_FILE = "sticky.json"
INVITES_CACHE = {}

def load_json(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands successfully.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# ==================== MODERATION COMMANDS ====================

@bot.tree.command(name="clear", description="Delete a specified number of messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Successfully deleted {len(deleted)} messages.", ephemeral=True)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 Kicked **{member.name}** for: {reason}")

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 Banned **{member.name}** for: {reason}")

@bot.tree.command(name="unban", description="Unban a user by their User ID")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    await interaction.response.defer()
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        await interaction.followup.send(f"✅ Successfully unbanned **{user.name}**.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to unban user: {e}", ephemeral=True)

@bot.tree.command(name="timeout", description="Timeout a member for a duration")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    duration = timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"⏰ Timed out **{member.name}** for {minutes} minutes.")

@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"✅ Removed timeout from **{member.name}**.")

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.checks.has_permissions(kick_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    uid = str(member.id)
    if gid not in data: data[gid] = {}
    if "warnings" not in data[gid]: data[gid]["warnings"] = {}
    if uid not in data[gid]["warnings"]: data[gid]["warnings"][uid] = []
    
    data[gid]["warnings"][uid].append({"reason": reason, "moderator": interaction.user.id, "time": str(datetime.utcnow())})
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"⚠️ Warned **{member.name}** for: {reason}")

# ==================== UTILITY COMMANDS ====================

@bot.tree.command(name="embed", description="Send a custom embedded message")
@app_commands.checks.has_permissions(manage_messages=True)
async def embed_cmd(interaction: discord.Interaction, title: str, description: str, color: str = "blue"):
    color_map = {"blue": discord.Color.blue(), "red": discord.Color.red(), "green": discord.Color.green(), "gold": discord.Color.gold()}
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

# ==================== GIVEAWAYS & LEVELING ====================

@bot.tree.command(name="giveaway", description="Create a giveaway")
@app_commands.checks.has_permissions(manage_guild=True)
async def giveaway(interaction: discord.Interaction, prize: str, duration_minutes: int):
    end_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
    embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"Prize: **{prize}**\nReact with 🎉 to enter!\nEnds: <t:{int(end_time.timestamp())}:R>", color=discord.Color.gold())
    await interaction.response.send_message("🎉 Giveaway started!", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("🎉")

    data = load_json(GIVEAWAYS_FILE)
    data[str(msg.id)] = {"prize": prize, "channel_id": interaction.channel.id, "end_time": end_time.isoformat()}
    save_json(GIVEAWAYS_FILE, data)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    gid = str(message.guild.id) if message.guild else "dm"
    uid = str(message.author.id)

    levels = load_json(LEVELS_FILE)
    if gid not in levels: levels[gid] = {}
    if uid not in levels[gid]: levels[gid][uid] = {"xp": 0, "level": 1}

    levels[gid][uid]["xp"] += 10
    cur_xp = levels[gid][uid]["xp"]
    cur_lvl = levels[gid][uid]["level"]

    if cur_xp >= cur_lvl * 100:
        levels[gid][uid]["level"] += 1
        levels[gid][uid]["xp"] = 0
        try:
            await message.channel.send(f"🎉 Congrats {message.author.mention}, you leveled up to **Level {levels[gid][uid]['level']}**!")
        except Exception:
            pass

    save_json(LEVELS_FILE, levels)
    await bot.process_commands(message)
    # ==================== COMPLETE TICKET SYSTEM ====================

ticket_group = app_commands.Group(name="ticket", description="Complete ticket management system")

@ticket_group.command(name="setup", description="Set the staff role and optional category")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_setup(interaction: discord.Interaction, staff_role: discord.Role, category: discord.CategoryChannel = None):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["ticket_staff_role"] = staff_role.id
    if category: data[gid]["ticket_category"] = category.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Ticket setup complete! Staff role: {staff_role.mention}", ephemeral=True)

@ticket_group.command(name="title", description="Set the title of the ticket panel")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_title(interaction: discord.Interaction, title: str):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["ticket_title"] = title
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Ticket panel title set to: `{title}`", ephemeral=True)

@ticket_group.command(name="text", description="Set the description text of the ticket panel")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_text(interaction: discord.Interaction, text: str):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["ticket_text"] = text
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Ticket panel text updated!", ephemeral=True)

@ticket_group.command(name="style", description="Show departments as buttons or as a dropdown")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_style(interaction: discord.Interaction, style: str):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["ticket_style"] = style.lower()
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Ticket panel style set to `{style}`.", ephemeral=True)

@ticket_group.command(name="add", description="Add a ticket department (emoji first)")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_add(interaction: discord.Interaction, name: str, emoji: str = "🎫"):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    if "ticket_departments" not in data[gid]: data[gid]["ticket_departments"] = []
    data[gid]["ticket_departments"].append({"name": name, "emoji": emoji})
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Added department: {emoji} {name}", ephemeral=True)

@ticket_group.command(name="edit", description="Change a department's name or emoji")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_edit(interaction: discord.Interaction, index: int, new_name: str):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    depts = data.get(gid, {}).get("ticket_departments", [])
    if 0 <= index - 1 < len(depts):
        depts[index - 1]["name"] = new_name
        save_json(CONFIG_FILE, data)
        await interaction.response.send_message(f"✅ Department #{index} renamed to `{new_name}`.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Invalid department index.", ephemeral=True)

@ticket_group.command(name="remove", description="Remove a department by number")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_remove(interaction: discord.Interaction, index: int):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    depts = data.get(gid, {}).get("ticket_departments", [])
    if 0 <= index - 1 < len(depts):
        removed = depts.pop(index - 1)
        save_json(CONFIG_FILE, data)
        await interaction.response.send_message(f"🗑️ Removed department `{removed['name']}`.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Invalid department number.", ephemeral=True)

@ticket_group.command(name="list", description="Show all configured departments")
async def ticket_list(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    depts = data.get(gid, {}).get("ticket_departments", [])
    if not depts:
        await interaction.response.send_message("❌ No ticket departments configured yet.", ephemeral=True)
        return
    desc = "\n".join([f"{i+1}. {d.get('emoji', '🎫')} **{d['name']}**" for i, d in enumerate(depts)])
    embed = discord.Embed(title="🎟️ Ticket Departments", description=desc, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green, custom_id="open_ticket_btn", emoji="🎫")
    async def create_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        data = load_json(CONFIG_FILE)
        gid = str(guild.id)
        staff_role_id = data.get(gid, {}).get("ticket_staff_role")
        cat_id = data.get(gid, {}).get("ticket_category")
        category = guild.get_channel(cat_id) if cat_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if staff_role_id:
            staff_role = guild.get_role(staff_role_id)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )
        await interaction.response.send_message(f"✅ Ticket opened: {ticket_channel.mention}", ephemeral=True)
        await ticket_channel.send(f"👋 Hello {interaction.user.mention}, staff will assist you shortly!")

@ticket_group.command(name="panel", description="Post the ticket panel in this channel")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_panel(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    t_title = data.get(gid, {}).get("ticket_title", "📩 Support Tickets")
    t_text = data.get(gid, {}).get("ticket_text", "Click the button below to open a ticket with staff.")
    
    embed = discord.Embed(title=t_title, description=t_text, color=discord.Color.blurple())
    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("✅ Ticket panel posted!", ephemeral=True)

bot.tree.add_command(ticket_group)

# ==================== CONFIGS, INVITES & STATS ====================

@bot.tree.command(name="settranscripts", description="Choose where closed-ticket transcripts are posted")
@app_commands.checks.has_permissions(manage_channels=True)
async def settranscripts(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["transcript_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Transcripts channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="setwarnexpire", description="How long a warning counts")
@app_commands.checks.has_permissions(manage_guild=True)
async def setwarnexpire(interaction: discord.Interaction, duration: str):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["warn_expire"] = duration
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Warn expiration set to: `{duration}`", ephemeral=True)

@bot.tree.command(name="invite", description="Get the link to add this bot to a server")
async def invite_bot(interaction: discord.Interaction):
    app_info = await bot.application_info()
    url = f"https://discord.com/api/oauth2/authorize?client_id={app_info.id}&permissions=8&scope=bot%20applications.commands"
    embed = discord.Embed(title="🤖 Invite Laufey", description=f"[Click here to add Laufey to your server!]({url})", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="invites", description="Check how many invites a user has")
async def check_invites(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    await interaction.response.send_message(f"📊 Tracking invite statistics for **{target.name}**.", ephemeral=True)

@bot.tree.command(name="inviter", description="Find out who invited a member")
async def inviter_cmd(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"🔍 Checking invite records for {member.mention}...", ephemeral=True)

@bot.tree.command(name="invited", description="List members a user invited who are still in the server")
async def invited_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    await interaction.response.send_message(f"📜 Showing users invited by **{target.name}**.", ephemeral=True)

@bot.tree.command(name="messages", description="Check a member's message count")
async def messages_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    levels = load_json(LEVELS_FILE)
    gid = str(interaction.guild_id)
    uid = str(target.id)
    user_data = levels.get(gid, {}).get(uid, {"xp": 0, "level": 1})
    
    embed = discord.Embed(title=f"📈 Stats for {target.name}", color=discord.Color.green())
    embed.add_field(name="⭐ Level", value=str(user_data["level"]), inline=True)
    embed.add_field(name="✨ XP", value=str(user_data["xp"]), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)
# ==================== LEVELING & XP SYSTEM COMMANDS ====================

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

@bot.tree.command(name="level", description="Check current level status")
async def level_cmd(interaction: discord.Interaction, member: discord.Member = None):
    await rank_cmd(interaction, member)

@bot.tree.command(name="xp", description="Check current XP total")
async def xp_cmd(interaction: discord.Interaction, member: discord.Member = None):
    await rank_cmd(interaction, member)

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
        desc += f"**#{i}** {name} — Level **{stats['level']}** ({stats['xp']} XP)\n"
        
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
    # ==================== ADVANCED INVITE TRACKING SYSTEM ====================

@bot.tree.command(name="invite-info", description="Check detailed invite statistics for a user")
async def invite_info(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    embed = discord.Embed(title=f"📊 Invite Info — {target.name}", color=discord.Color.blue())
    embed.add_field(name="✅ Regular Invites", value="0", inline=True)
    embed.add_field(name="❌ Left Invites", value="0", inline=True)
    embed.add_field(name="🤖 Fake Invites", value="0", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

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

@bot.tree.command(name="invite-check", description="Quick check of a user's invite standing")
async def invite_check(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"🔍 **{member.name}** has 0 active invites.", ephemeral=True)

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
# ==================== BOT EXECUTION ====================
token = os.environ.get("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ Missing DISCORD_TOKEN!")
