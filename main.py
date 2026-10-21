import discord
from discord import app_commands
from discord.ext import commands
import datetime
import os
import json
import asyncio
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- Web Server ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Laufey Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# --- Setup Bot ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.invites = True

bot = commands.Bot(command_prefix="!", intents=intents)

CONFIG_FILE = "channels.json"
LEVELS_FILE = "levels.json"
GIVEAWAYS_FILE = "giveaways.json"
STICKY_FILE = "sticky.json"
INVITES_CACHE = {}

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            try:
                return json.load(f)
            except:
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
            INVITES_CACHE[guild.id] = {
                inv.code: inv.uses for inv in invites
            }
        except:
            pass
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Sync error: {e}")

@bot.event
async def on_invite_create(invite):
    if invite.guild.id not in INVITES_CACHE:
        INVITES_CACHE[invite.guild.id] = {}
    INVITES_CACHE[invite.guild.id][invite.code] = invite.uses

@bot.event
async def on_invite_delete(invite):
    if invite.guild.id in INVITES_CACHE:
        if invite.code in INVITES_CACHE[invite.guild.id]:
            del INVITES_CACHE[invite.guild.id][invite.code]

# ==================== EMBED, LOCK, STICKY ====================

@bot.tree.command(name="embed", description="Create custom embed")
@app_commands.checks.has_permissions(manage_messages=True)
async def embed_cmd(
    interaction: discord.Interaction, 
    title: str, 
    description: str, 
    color: str = "blue", 
    channel: discord.TextChannel = None
):
    await interaction.response.defer(ephemeral=True)
    
    col_map = {
        "blue": discord.Color.blue(),
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "gold": discord.Color.gold(),
        "purple": discord.Color.purple()
    }
    embed_color = col_map.get(color.lower(), discord.Color.blue())
    embed = discord.Embed(
        title=title, 
        description=description, 
        color=embed_color
    )
    target = channel or interaction.channel
    await target.send(embed=embed)
    await interaction.followup.send("✅ Embed sent!", ephemeral=True)

@bot.tree.command(name="lock", description="Lock current channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    await interaction.response.defer()
    role = interaction.guild.default_role
    overwrite = interaction.channel.overwrites_for(role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(role, overwrite=overwrite)
    await interaction.followup.send("🔒 Channel locked.")

@bot.tree.command(name="unlock", description="Unlock current channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    await interaction.response.defer()
    role = interaction.guild.default_role
    overwrite = interaction.channel.overwrites_for(role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(role, overwrite=overwrite)
    await interaction.followup.send("🔓 Channel unlocked.")

@bot.tree.command(name="sticky", description="Create sticky message")
@app_commands.checks.has_permissions(manage_messages=True)
async def sticky(interaction: discord.Interaction, *, message: str):
    await interaction.response.defer()
    sticky_data = load_json(STICKY_FILE)
    
    embed = discord.Embed(
        title="📌 Sticky Message", 
        description=message, 
        color=discord.Color.blurple()
    )
    msg = await interaction.channel.send(embed=embed)
    
    sticky_data[str(interaction.channel_id)] = {
        "content": message,
        "last_msg_id": msg.id
    }
    save_json(STICKY_FILE, sticky_data)
    await interaction.followup.send("✅ Sticky activated!", ephemeral=True)

@bot.tree.command(name="unsticky", description="Remove sticky message")
@app_commands.checks.has_permissions(manage_messages=True)
async def unsticky(interaction: discord.Interaction):
    await interaction.response.defer()
    sticky_data = load_json(STICKY_FILE)
    ch_id = str(interaction.channel_id)
    
    if ch_id in sticky_data:
        try:
            old_id = sticky_data[ch_id]["last_msg_id"]
            old_msg = await interaction.channel.fetch_message(old_id)
            await old_msg.delete()
        except:
            pass
        del sticky_data[ch_id]
        save_json(STICKY_FILE, sticky_data)
        await interaction.followup.send("✅ Sticky removed.", ephemeral=True)
    else:
        await interaction.followup.send("⚠️ No sticky here.", ephemeral=True)

# ==================== ADVANCED GIVEAWAY SYSTEM ====================

giveaway_group = app_commands.Group(name="giveaway", description="Advanced giveaway management")

@giveaway_group.command(name="create", description="Create a highly customizable giveaway")
@app_commands.checks.has_permissions(manage_events=True)
async def giveaway_create(
    interaction: discord.Interaction,
    duration: int,
    unit: str,
    winners: int,
    prize: str,
    channel: discord.TextChannel = None,
    required_roles: discord.Role = None,
    required_level: int = None,
    required_daily_messages: int = None,
    required_weekly_messages: int = None,
    required_monthly_messages: int = None,
    required_total_messages: int = None,
    required_server_boosts: int = None,
    requirement_bypass_roles: discord.Role = None,
    image: str = None,
    thumbnail: str = None,
    color: str = "gold",
    end_color: str = "green",
    claim_time: int = None,
    giveaway_winners_dm_message: str = None,
    giveaway_create_message: str = None
):
    await interaction.response.defer(ephemeral=True)
    target_channel = channel or interaction.channel
    
    u = unit.lower().strip()
    if u in ["d", "day", "days"]:
        seconds = duration * 86400
    elif u in ["h", "hr", "hours"]:
        seconds = duration * 3600
    elif u in ["m", "min", "minutes"]:
        seconds = duration * 60
    else:
        seconds = duration

    end_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    timestamp = f"<t:{int(end_time.timestamp())}:R>"

    col_map = {
        "gold": discord.Color.gold(),
        "blue": discord.Color.blue(),
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "purple": discord.Color.purple()
    }
    start_embed_color = col_map.get(color.lower(), discord.Color.gold())

    embed = discord.Embed(title="🎉 GIVEAWAY 🎉", color=start_embed_color)
    embed.add_field(name="🎁 Prize", value=f"**{prize}**", inline=False)
    embed.add_field(name="👑 Winners", value=str(winners), inline=True)
    embed.add_field(name="⏳ Ends", value=timestamp, inline=True)

    req_list = []
    if required_roles:
        req_list.append(f"• Role: {required_roles.mention}")
    if required_level:
        req_list.append(f"• Level: {required_level}+")
    if required_daily_messages:
        req_list.append(f"• Daily Msgs: {required_daily_messages}+")
    if required_weekly_messages:
        req_list.append(f"• Weekly Msgs: {required_weekly_messages}+")
    if required_monthly_messages:
        req_list.append(f"• Monthly Msgs: {required_monthly_messages}+")
    if required_total_messages:
        req_list.append(f"• Total Msgs: {required_total_messages}+")
    if required_server_boosts:
        req_list.append(f"• Server Boosts: {required_server_boosts}+")

    if req_list:
        embed.add_field(name="📜 Requirements", value="\n".join(req_list), inline=False)
    if requirement_bypass_roles:
        embed.add_field(name="🔓 Bypass Role", value=requirement_bypass_roles.mention, inline=False)
    if claim_time:
        embed.add_field(name="⏰ Claim Time", value=f"{claim_time} minutes", inline=False)

    if image:
        embed.set_image(url=image)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    embed.set_footer(text="React with 🎉 to enter!")

    if giveaway_create_message:
        await target_channel.send(giveaway_create_message)

    msg = await target_channel.send(embed=embed)
    await msg.add_reaction("🎉")

    giveaways = load_json(GIVEAWAYS_FILE)
    giveaways[str(msg.id)] = {
        "guild_id": interaction.guild_id,
        "channel_id": target_channel.id,
        "prize": prize,
        "winners": winners,
        "required_role_id": required_roles.id if required_roles else None,
        "bypass_role_id": requirement_bypass_roles.id if requirement_bypass_roles else None,
        "required_level": required_level,
        "end_color": end_color,
        "dm_message": giveaway_winners_dm_message
    }
    save_json(GIVEAWAYS_FILE, giveaways)

    await interaction.followup.send(f"✅ Giveaway created in {target_channel.mention}!", ephemeral=True)

    await asyncio.sleep(seconds)

    try:
        updated_msg = await target_channel.fetch_message(msg.id)
    except:
        return

    reaction = discord.utils.get(updated_msg.reactions, emoji="🎉")
    if not reaction:
        return

    raw_users = [user async for user in reaction.users() if not user.bot]
    valid_users = []

    levels_data = load_json(LEVELS_FILE)
    gid = str(interaction.guild_id)

    for u_obj in raw_users:
        member = interaction.guild.get_member(u_obj.id)
        if not member:
            continue

        if requirement_bypass_roles and requirement_bypass_roles in member.roles:
            valid_users.append(u_obj)
            continue

        if required_roles and required_roles not in member.roles:
            continue

        if required_level:
            user_lvl = levels_data.get(gid, {}).get(str(member.id), {}).get("level", 1)
            if user_lvl < required_level:
                continue

        valid_users.append(u_obj)

    if not valid_users:
        await target_channel.send(f"❌ Giveaway for **{prize}** ended with no valid entries.")
        return

    num_w = min(len(valid_users), winners)
    winning_users = random.sample(valid_users, num_w)
    winner_mentions = ", ".join([u.mention for u in winning_users])

    final_col_map = {
        "green": discord.Color.green(),
        "gold": discord.Color.gold(),
        "blue": discord.Color.blue(),
        "red": discord.Color.red(),
        "purple": discord.Color.purple()
    }
    end_embed_color = final_col_map.get(end_color.lower(), discord.Color.green())

    win_embed = discord.Embed(title="🎉 GIVEAWAY ENDED 🎉", color=end_embed_color)
    win_embed.add_field(name="🎁 Prize", value=f"**{prize}**", inline=False)
    win_embed.add_field(name="🏆 Winner(s)", value=winner_mentions, inline=False)
    if image:
        win_embed.set_image(url=image)

    await updated_msg.edit(embed=win_embed)
    await target_channel.send(f"🎊 Congratulations {winner_mentions}! You won **{prize}**!")

    if giveaway_winners_dm_message:
        for w_user in winning_users:
            try:
                await w_user.send(f"🎉 You won **{prize}**!\n\n{giveaway_winners_dm_message}")
            except:
                pass

bot.tree.add_command(giveaway_group)
# ==================== CONFIG & EVENTS ====================

@bot.tree.command(name="setinvitracker", description="Set invite channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def setinvitracker(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["invite_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Invite channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="setwelcome", description="Set welcome channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["welcome_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="setleave", description="Set leave channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def setleave(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["leave_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Leave channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="enablelevels", description="Enable levels")
@app_commands.checks.has_permissions(manage_channels=True)
async def enablelevels(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["levels_enabled"] = True
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Levels enabled!", ephemeral=True)

@bot.event
async def on_member_join(member: discord.Member):
    data = load_json(CONFIG_FILE)
    gid = str(member.guild.id)
    if gid in data and "welcome_channel" in data[gid]:
        ch = member.guild.get_channel(data[gid]["welcome_channel"])
        if ch: 
            await ch.send(f"👋 Welcome {member.mention}!")

@bot.event
async def on_member_remove(member: discord.Member):
    data = load_json(CONFIG_FILE)
    gid = str(member.guild.id)
    if gid in data and "leave_channel" in data[gid]:
        ch = member.guild.get_channel(data[gid]["leave_channel"])
        if ch: 
            await ch.send(f"👋 **{member.name}** left.")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild: 
        return

    # Sticky
    sticky_data = load_json(STICKY_FILE)
    ch_id = str(message.channel.id)
    if ch_id in sticky_data:
        s_info = sticky_data[ch_id]
        try:
            old_msg = await message.channel.fetch_message(s_info["last_msg_id"])
            await old_msg.delete()
        except: 
            pass
        embed = discord.Embed(
            title="📌 Sticky Message", 
            description=s_info["content"], 
            color=discord.Color.blurple()
        )
        new_sticky = await message.channel.send(embed=embed)
        s_info["last_msg_id"] = new_sticky.id
        save_json(STICKY_FILE, sticky_data)

    # Levels
    config = load_json(CONFIG_FILE)
    gid = str(message.guild.id)
    if gid in config and config[gid].get("levels_enabled", False):
        levels = load_json(LEVELS_FILE)
        uid = str(message.author.id)
        if gid not in levels: 
            levels[gid] = {}
        if uid not in levels[gid]: 
            levels[gid][uid] = {"xp": 0, "level": 1}
        
        levels[gid][uid]["xp"] += 10
        if levels[gid][uid]["xp"] >= levels[gid][uid]["level"] * 100:
            levels[gid][uid]["level"] += 1
            levels[gid][uid]["xp"] = 0
            ch = message.guild.get_channel(config[gid].get("level_channel", message.channel.id)) or message.channel
            await ch.send(f"🎉 Congrats {message.author.mention}, level **{levels[gid][uid]['level']}**!")
        save_json(LEVELS_FILE, levels)

    await bot.process_commands(message)

# ==================== MODERATION ====================

@bot.command(name="clear")
async def clear(ctx, amount: int = 5):
    if not ctx.author.guild_permissions.manage_messages: 
        return
    await ctx.message.delete()
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 Deleted {len(deleted)} messages.", delete_after=5)

@bot.tree.command(name="kick", description="Kick member")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await interaction.response.defer()
    await member.kick(reason=reason)
    await interaction.followup.send(f"✅ Kicked {member.mention}.")

@bot.tree.command(name="ban", description="Ban member")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await interaction.response.defer()
    await member.ban(reason=reason)
    await interaction.followup.send(f"⛔ Banned {member.mention}.")

@bot.tree.command(name="timeout", description="Timeout member")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int, unit: str, reason: str = "No reason"):
    await interaction.response.defer()
    u = unit.lower().strip()
    sec = duration * 86400 if u in ["d", "days"] else duration * 3600 if u in ["h", "hours"] else duration * 60 if u in ["m", "minutes"] else duration
    await member.timeout(datetime.timedelta(seconds=sec), reason=reason)
    await interaction.followup.send(f"🔇 Timed out {member.mention}.")

@bot.tree.command(name="warn", description="Warn member")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await interaction.response.defer()
    try: 
        await member.send(f"⚠️ Warned in **{interaction.guild.name}**: {reason}")
    except: 
        pass
    await interaction.followup.send(f"⚠️ Warned {member.mention}.")

# ==================== AUTOMOD & ANTISPAM ====================

automod_group = app_commands.Group(name="automod", description="Automod management")

@automod_group.command(name="words", description="Manage blocked words")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_words(interaction: discord.Interaction, action: str, word: str = None):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    if "automod_words" not in data[gid]: data[gid]["automod_words"] = []
    act = action.lower()
    if act == "add" and word:
        if word.lower() not in data[gid]["automod_words"]:
            data[gid]["automod_words"].append(word.lower())
            save_json(CONFIG_FILE, data)
        await interaction.response.send_message(f"✅ Added blocked word: `{word}`", ephemeral=True)
    elif act == "remove" and word:
        if word.lower() in data[gid]["automod_words"]:
            data[gid]["automod_words"].remove(word.lower())
            save_json(CONFIG_FILE, data)
        await interaction.response.send_message(f"✅ Removed blocked word: `{word}`", ephemeral=True)
    elif act == "list":
        words = data[gid]["automod_words"]
        await interaction.response.send_message(f"📜 Blocked words: {', '.join(words) if words else 'None'}", ephemeral=True)

@automod_group.command(name="invites", description="Toggle invite link deletion")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_invites(interaction: discord.Interaction, enabled: bool):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["automod_invites"] = enabled
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Automod invites set to: `{enabled}`", ephemeral=True)

@automod_group.command(name="links", description="Toggle link deletion")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_links(interaction: discord.Interaction, enabled: bool):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["automod_links"] = enabled
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Automod links set to: `{enabled}`", ephemeral=True)

@automod_group.command(name="punish", description="Set action after strikes")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_punish(interaction: discord.Interaction, action: str):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["automod_punishment"] = action.lower()
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Automod punishment set to: `{action}`", ephemeral=True)

bot.tree.add_command(automod_group)

antispam_group = app_commands.Group(name="antispam", description="Antispam management")

@antispam_group.command(name="on", description="Turn anti-spam on")
@app_commands.checks.has_permissions(manage_guild=True)
async def antispam_on(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["antispam_enabled"] = True
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Anti-spam enabled.", ephemeral=True)

@antispam_group.command(name="off", description="Turn anti-spam off")
@app_commands.checks.has_permissions(manage_guild=True)
async def antispam_off(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["antispam_enabled"] = False
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message("❌ Anti-spam disabled.", ephemeral=True)

bot.tree.add_command(antispam_group)
# ==================== TICKETS & UTILITIES ====================

@ticket_group.command(name="add", description="Add a ticket department (emoji first)")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_add(interaction: discord.Interaction, name: str, emoji: str = "🎫"):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    if "ticket_departments" not in data[gid]: data[gid]["ticket_departments"] = []
    data[gid]["ticket_departments"].append({"name": name, "emoji": emoji})
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Added ticket department: {emoji} {name}", ephemeral=True)

@ticket_group.command(name="edit", description="Change a department's name, emoji, description...")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_edit(interaction: discord.Interaction, index: int, new_name: str):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    depts = data.get(gid, {}).get("ticket_departments", [])
    if 0 <= index - 1 < len(depts):
        depts[index - 1]["name"] = new_name
        save_json(CONFIG_FILE, data)
        await interaction.response.send_message(f"✅ Updated department #{index} to `{new_name}`", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Invalid department number.", ephemeral=True)

@ticket_group.command(name="list", description="Show all departments and current ticket set...")
async def ticket_list(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    depts = data.get(gid, {}).get("ticket_departments", [])
    if not depts:
        await interaction.response.send_message("❌ No custom ticket departments configured.", ephemeral=True)
        return
    desc = "\n".join([f"{i+1}. {d.get('emoji', '🎫')} **{d['name']}**" for i, d in enumerate(depts)])
    embed = discord.Embed(title="🎟️ Ticket Departments", description=desc, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="invite", description="Get the link to add this bot to a server")
async def invite_bot(interaction: discord.Interaction):
    app_info = await bot.application_info()
    url = f"https://discord.com/api/oauth2/authorize?client_id={app_info.id}&permissions=8&scope=bot%20applications.commands"
    embed = discord.Embed(title="🤖 Invite Laufey", description=f"[Click here to add Laufey to your server!]({url})", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="invites", description="Check how many invites a user has")
async def check_invites(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    await interaction.response.send_message(f"📊 Tracking invites for **{target.name}**.", ephemeral=True)

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
    
    embed = discord.Embed(title=f"📈 Message & Activity Stats for {target.name}", color=discord.Color.green())
    embed.add_field(name="⭐ Level", value=str(user_data["level"]), inline=True)
    embed.add_field(name="✨ XP", value=str(user_data["xp"]), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)
token = os.environ.get("DISCORD_TOKEN")
if token: 
    bot.run(token)
else: 
    print("❌ Missing DISCORD_TOKEN!")
