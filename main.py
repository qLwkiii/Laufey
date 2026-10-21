import discord
from discord import app_commands
from discord.ext import commands
import datetime, os, json, asyncio, random, threading
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
INVITES_CACHE = {}

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            try: return json.load(f)
            except: return {}
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
            INVITES_CACHE[guild.id] = {inv.code: inv.uses for inv in invites}
        except: pass
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Sync error: {e}")

@bot.event
async def on_invite_create(invite):
    if invite.guild.id not in INVITES_CACHE: INVITES_CACHE[invite.guild.id] = {}
    INVITES_CACHE[invite.guild.id][invite.code] = invite.uses

@bot.event
async def on_invite_delete(invite):
    if invite.guild.id in INVITES_CACHE and invite.code in INVITES_CACHE[invite.guild.id]:
        del INVITES_CACHE[invite.guild.id][invite.code]

# --- GIVEAWAY SYSTEM ---
@bot.tree.command(name="gstart", description="Start a flexible giveaway")
async def gstart(interaction: discord.Interaction, duration: int, unit: str, winners: int, prize: str, required_role: discord.Role = None, requirements: str = None):
    await interaction.response.defer()
    u = unit.lower().strip()
    seconds = duration * 86400 if u in ["d","day","days"] else (duration * 3600 if u in ["h","hr","hours"] else (duration * 60 if u in ["m","min","minutes"] else duration))
    
    end_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    timestamp = f"<t:{int(end_time.timestamp())}:R>"

    embed = discord.Embed(title="🎉 GIVEAWAY STARTED! 🎉", color=discord.Color.gold())
    embed.add_field(name="🎁 Prize", value=f"**{prize}**", inline=False)
    embed.add_field(name="👑 Winners", value=str(winners), inline=True)
    embed.add_field(name="⏳ Ends", value=timestamp, inline=True)
    embed.add_field(name="🎙️ Hosted By", value=interaction.user.mention, inline=True)
    if required_role: embed.add_field(name="🔒 Required Role", value=required_role.mention, inline=False)
    if requirements: embed.add_field(name="📜 Requirements", value=requirements, inline=False)
    embed.set_footer(text="React with 🎉 to enter!")

    message = await interaction.followup.send(embed=embed, wait=True)
    await message.add_reaction("🎉")

    giveaways = load_json(GIVEAWAYS_FILE)
    giveaways[str(message.id)] = {"guild_id": interaction.guild_id, "channel_id": interaction.channel_id, "prize": prize, "winners": winners, "required_role_id": required_role.id if required_role else None, "host_id": interaction.user.id}
    save_json(GIVEAWAYS_FILE, giveaways)

    await asyncio.sleep(seconds)

    try: updated_msg = await interaction.channel.fetch_message(message.id)
    except: return

    reaction = discord.utils.get(updated_msg.reactions, emoji="🎉")
    if not reaction:
        await interaction.channel.send(f"❌ Giveaway for **{prize}** ended with no entries.")
        return

    raw_users = [user async for user in reaction.users() if not user.bot]
    valid_users = [u for u in raw_users if not required_role or (interaction.guild.get_member(u.id) and required_role in interaction.guild.get_member(u.id).roles)]

    if not valid_users:
        await interaction.channel.send(f"❌ Giveaway for **{prize}** ended, but no entries met requirements.")
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

@bot.tree.command(name="greroll", description="Reroll giveaway winners")
@app_commands.checks.has_permissions(manage_events=True)
async def greroll(interaction: discord.Interaction, message_id: str):
    await interaction.response.defer()
    try: msg = await interaction.channel.fetch_message(int(message_id))
    except:
        await interaction.followup.send("❌ Message not found.", ephemeral=True)
        return

    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    if not reaction:
        await interaction.followup.send("❌ No entries found.", ephemeral=True)
        return

    raw_users = [user async for user in reaction.users() if not user.bot]
    if not raw_users:
        await interaction.followup.send("❌ No valid entries.", ephemeral=True)
        return

    new_winner = random.choice(raw_users)
    await interaction.followup.send(f"🎉 New Winner: {new_winner.mention}!")

@bot.tree.command(name="gstop", description="Stop giveaway")
@app_commands.checks.has_permissions(manage_events=True)
async def gstop(interaction: discord.Interaction, message_id: str):
    await interaction.response.defer()
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
        cancel_embed = discord.Embed(title="🛑 GIVEAWAY CANCELED 🛑", description="Canceled by admin.", color=discord.Color.red())
        await msg.edit(embed=cancel_embed)
        await interaction.followup.send("✅ Giveaway canceled.", ephemeral=True)
    except:
        await interaction.followup.send("❌ Message not found.", ephemeral=True)

# --- INVITES & CONFIG ---
@bot.tree.command(name="setinvitracker", description="Set channel for invite alerts")
@app_commands.checks.has_permissions(manage_channels=True)
async def setinvitracker(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["invite_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Invite channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="removeinvitracker", description="Disable invite tracking")
@app_commands.checks.has_permissions(manage_channels=True)
async def removeinvitracker(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid in data and "invite_channel" in data[gid]:
        del data[gid]["invite_channel"]
        save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Invite tracking disabled.", ephemeral=True)

@bot.tree.command(name="setwelcome", description="Set welcome channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["welcome_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="removewelcome", description="Disable welcome channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def removewelcome(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid in data and "welcome_channel" in data[gid]:
        del data[gid]["welcome_channel"]
        save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Welcome disabled.", ephemeral=True)

@bot.tree.command(name="setleave", description="Set leave channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def setleave(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["leave_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Leave channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="removeleave", description="Disable leave channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def removeleave(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid in data and "leave_channel" in data[gid]:
        del data[gid]["leave_channel"]
        save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Leave disabled.", ephemeral=True)

@bot.tree.command(name="setlevel", description="Set level channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def setlevel(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["level_channel"] = channel.id
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message(f"✅ Level channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="enablelevels", description="Enable levels")
@app_commands.checks.has_permissions(manage_channels=True)
async def enablelevels(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid not in data: data[gid] = {}
    data[gid]["levels_enabled"] = True
    save_json(CONFIG_FILE, data)
    await interaction.response.send_message("✅ Levels enabled!", ephemeral=True)

@bot.tree.command(name="disablelevels", description="Disable levels")
@app_commands.checks.has_permissions(manage_channels=True)
async def disablelevels(interaction: discord.Interaction):
    data = load_json(CONFIG_FILE)
    gid = str(interaction.guild_id)
    if gid in data:
        data[gid]["levels_enabled"] = False
        save_json(CONFIG_FILE, data)
    await interaction.response.send_message("❌ Levels disabled.", ephemeral=True)

# --- EVENTS ---
@bot.event
async def on_member_join(member: discord.Member):
    data = load_json(CONFIG_FILE)
    gid = str(member.guild.id)
    if gid in data and "welcome_channel" in data[gid]:
        ch = member.guild.get_channel(data[gid]["welcome_channel"])
        if ch: await ch.send(f"👋 Welcome {member.mention}!")

    if gid in data and "invite_channel" in data[gid]:
        ch = member.guild.get_channel(data[gid]["invite_channel"])
        if ch:
            cached = INVITES_CACHE.get(member.guild.id, {})
            try:
                new_invs = await member.guild.invites()
                used = next((i for i in new_invs if i.code in cached and i.uses > cached[i.code]), None)
                INVITES_CACHE[member.guild.id] = {i.code: i.uses for i in new_invs}
                if used and used.inviter: await ch.send(f"📩 {member.mention} invited by **{used.inviter.mention}** ({used.code}).")
                else: await ch.send(f"📩 {member.mention} joined.")
            except: pass

@bot.event
async def on_member_remove(member: discord.Member):
    data = load_json(CONFIG_FILE)
    gid = str(member.guild.id)
    if gid in data and "leave_channel" in data[gid]:
        ch = member.guild.get_channel(data[gid]["leave_channel"])
        if ch: await ch.send(f"👋 **{member.name}** left.")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild: return
    config = load_json(CONFIG_FILE)
    gid = str(message.guild.id)
    if gid in config and config[gid].get("levels_enabled", False):
        levels = load_json(LEVELS_FILE)
        uid = str(message.author.id)
        if gid not in levels: levels[gid] = {}
        if uid not in levels[gid]: levels[gid][uid] = {"xp": 0, "level": 1}
        
        levels[gid][uid]["xp"] += 10
        if levels[gid][uid]["xp"] >= levels[gid][uid]["level"] * 100:
            levels[gid][uid]["level"] += 1
            levels[gid][uid]["xp"] = 0
            ch = message.guild.get_channel(config[gid].get("level_channel", message.channel.id)) or message.channel
            await ch.send(f"🎉 Congrats {message.author.mention}, level **{levels[gid][uid]['level']}**!")
        save_json(LEVELS_FILE, levels)
    await bot.process_commands(message)

# --- MODERATION ---
@bot.command(name="clear")
async def clear(ctx, amount: int = 5):
    if not ctx.author.guild_permissions.manage_messages: return
    await ctx.message.delete()
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 Deleted {len(deleted)} messages.", delete_after=5)

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await interaction.response.defer()
    await member.kick(reason=reason)
    await interaction.followup.send(f"✅ Kicked {member.mention}.")

@bot.tree.command(name="ban", description="Ban a member")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await interaction.response.defer()
    await member.ban(reason=reason)
    await interaction.followup.send(f"⛔ Banned {member.mention}.")

@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int, unit: str, reason: str = "No reason"):
    await interaction.response.defer()
    u = unit.lower().strip()
    sec = duration * 86400 if u in ["d","days"] else (duration * 3600 if u in ["h","hours"] else (duration * 60 if u in ["m","minutes"] else duration))
    await member.timeout(datetime.timedelta(seconds=sec), reason=reason)
    await interaction.followup.send(f"🔇 Timed out {member.mention}.")

@bot.tree.command(name="untimeout", description="Remove timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    await member.timeout(None)
    await interaction.followup.send(f"🔊 Removed timeout for {member.mention}.")

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    await interaction.response.defer()
    try: await member.send(f"⚠️ Warned in **{interaction.guild.name}**: {reason}")
    except: pass
    await interaction.followup.send(f"⚠️ Warned {member.mention}.")

token = os.environ.get("DISCORD_TOKEN")
if token: bot.run(token)
else: print("❌ Missing DISCORD_TOKEN!")
