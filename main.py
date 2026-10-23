import os
import datetime
import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------
# BOT SETUP & INTENTS
# ---------------------------------------------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory database for warnings
warnings_db = {}

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print(f"Synced {len(synced)} slash commands successfully!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# ---------------------------------------------------------
# 18 FULL SLASH COMMANDS (ZERO TRIMMING & COMPLETE LOCKDOWN)
# ---------------------------------------------------------

# 1. SERVERINFO
@bot.tree.command(name="serverinfo", description="Displays detailed information about this server.")
async def serverinfo(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    if not guild:
        await interaction.followup.send("This command can only be used inside a server!", ephemeral=True)
        return

    total_members = guild.member_count or 0
    bot_count = sum(1 for member in guild.members if member.bot) if guild.members else 0
    human_count = total_members - bot_count if guild.members else "N/A"

    embed = discord.Embed(
        title=f"🏰 {guild.name}", 
        description=guild.description or "No description set.", 
        color=discord.Color.blue()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(name="Owner", value=f"{guild.owner.mention}" if guild.owner else "Unknown", inline=True)
    embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="Created On", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)
    embed.add_field(name="Total Members", value=f"👥 {total_members}", inline=True)
    embed.add_field(name="Humans", value=f"👤 {human_count}", inline=True)
    embed.add_field(name="Bots", value=f"🤖 {bot_count}", inline=True)
    embed.add_field(name="Roles Count", value=f"📜 {len(guild.roles)}", inline=True)
    embed.add_field(name="Text Channels", value=f"💬 {len(guild.text_channels)}", inline=True)
    embed.add_field(name="Voice Channels", value=f"🔊 {len(guild.voice_channels)}", inline=True)
    embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)


# 2. USERINFO (With Full Profile Picture Display)
@bot.tree.command(name="userinfo", description="Displays detailed information about a member.")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    member = member or interaction.user

    roles = [role.mention for role in member.roles[1:]] or ["None"]
    
    embed = discord.Embed(
        title=f"👤 User Info - {member.display_name}", 
        color=member.color
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=member.display_avatar.url)

    embed.add_field(name="Username", value=f"{member.name}", inline=True)
    embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
    
    if member.joined_at:
        embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:D>", inline=True)
    
    embed.add_field(name="Joined Discord", value=f"<t:{int(member.created_at.timestamp())}:D>", inline=True)
    embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles[:10]), inline=False)
    embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)


# 3. TIMEOUT
@bot.tree.command(name="timeout", description="Timeout a member for a specified duration in minutes.")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    await interaction.response.defer()
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.followup.send("❌ Cannot timeout user: Their role is equal to or higher than mine.")
        return

    duration = datetime.timedelta(minutes=minutes)
    try:
        await member.timeout(duration, reason=reason)
        await interaction.followup.send(f"⏳ **{member.mention}** has been timed out for {minutes} minutes. Reason: {reason}")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to timeout user: {e}")


# 4. UNTIMEOUT
@bot.tree.command(name="untimeout", description="Remove a timeout from a member.")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    try:
        await member.timeout(None)
        await interaction.followup.send(f"✅ Timeout removed for **{member.mention}**.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to remove timeout: {e}")


# 5. WARN
@bot.tree.command(name="warn", description="Issue a formal warning to a member.")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer()
    guild_id = interaction.guild_id
    user_id = member.id

    if guild_id not in warnings_db:
        warnings_db[guild_id] = {}
    if user_id not in warnings_db[guild_id]:
        warnings_db[guild_id][user_id] = []

    warnings_db[guild_id][user_id].append(reason)
    total_warns = len(warnings_db[guild_id][user_id])
    await interaction.followup.send(f"⚠️ **{member.mention}** was warned. Reason: {reason} (Total Warnings: {total_warns})")


# 6. WARNS
@bot.tree.command(name="warns", description="View warnings for a member.")
async def warns(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    member = member or interaction.user
    guild_id = interaction.guild_id
    user_id = member.id

    user_warnings = warnings_db.get(guild_id, {}).get(user_id, [])
    if not user_warnings:
        await interaction.followup.send(f"✅ **{member.mention}** has no warnings.")
        return

    warn_list = "\n".join([f"• {reason}" for reason in user_warnings])
    embed = discord.Embed(title=f"⚠️ Warnings for {member.name}", description=warn_list, color=discord.Color.yellow())
    await interaction.followup.send(embed=embed)


# 7. CLEARWARNS
@bot.tree.command(name="clearwarns", description="Clear all warnings for a member.")
@app_commands.checks.has_permissions(manage_messages=True)
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    guild_id = interaction.guild_id
    user_id = member.id

    if guild_id in warnings_db and user_id in warnings_db[guild_id]:
        warnings_db[guild_id][user_id] = []
        await interaction.followup.send(f"🧹 Cleared all warnings for **{member.mention}**.")
    else:
        await interaction.followup.send(f"**{member.mention}** has no warnings to clear.")


# 8. KICK
@bot.tree.command(name="kick", description="Kick a member from the server.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer()
    try:
        await member.kick(reason=reason)
        await interaction.followup.send(f"👢 Kicked **{member.mention}**. Reason: {reason}")
    except Exception as e:
        await interaction.followup.send(f"❌ Could not kick member: {e}")


# 9. BAN
@bot.tree.command(name="ban", description="Ban a member from the server.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer()
    try:
        await member.ban(reason=reason)
        await interaction.followup.send(f"🔨 Banned **{member.mention}**. Reason: {reason}")
    except Exception as e:
        await interaction.followup.send(f"❌ Could not ban member: {e}")


# 10. UNBAN
@bot.tree.command(name="unban", description="Unban a user by their User ID.")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer()
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.followup.send(f"🔓 Unbanned **{user.name}**.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to unban ID `{user_id}`: {e}")


# 11. PURGE
@bot.tree.command(name="purge", description="Purge a specified number of messages.")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    if amount < 1 or amount > 100:
        await interaction.followup.send("Please choose an amount between 1 and 100.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Deleted `{len(deleted)}` messages.", ephemeral=True)


# 12. SLOWMODE
@bot.tree.command(name="slowmode", description="Set channel slowmode delay in seconds.")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    await interaction.response.defer()
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.followup.send(f"⏱️ Channel slowmode set to `{seconds}` seconds.")


# 13. LOCK (Full Lockdown: Chatting, Threads, and Thread Messages Disabled)
@bot.tree.command(name="lock", description="Lock the current channel to disable chat and thread creation.")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    await interaction.response.defer()
    
    await interaction.channel.set_permissions(
        interaction.guild.default_role, 
        send_messages=False,
        send_messages_in_threads=False,
        create_public_threads=False,
        create_private_threads=False
    )
    await interaction.followup.send("🔒 Channel completely locked. Chatting, thread creation, and thread messaging disabled for `@everyone`.")


# 14. UNLOCK
@bot.tree.command(name="unlock", description="Unlock the current channel for @everyone.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    await interaction.response.defer()
    
    await interaction.channel.set_permissions(
        interaction.guild.default_role, 
        send_messages=True,
        send_messages_in_threads=True,
        create_public_threads=True,
        create_private_threads=True
    )
    await interaction.followup.send("🔓 Channel has been unlocked for `@everyone`.")


# 15. NICK
@bot.tree.command(name="nick", description="Change a member's nickname.")
@app_commands.checks.has_permissions(manage_nicknames=True)
async def nick(interaction: discord.Interaction, member: discord.Member, new_nickname: str = None):
    await interaction.response.defer()
    try:
        await member.edit(nick=new_nickname)
        name = new_nickname or member.name
        await interaction.followup.send(f"🏷️ Nickname for **{member.mention}** updated to `{name}`.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to change nickname: {e}")


# 16. BOTINFO
@bot.tree.command(name="botinfo", description="Display statistics and info about Laufey.")
async def botinfo(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(title="🤖 Bot Status & Information", color=discord.Color.purple())
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="Bot Name", value=bot.user.name, inline=True)
    embed.add_field(name="Bot ID", value=f"`{bot.user.id}`", inline=True)
    embed.add_field(name="Servers Connected", value=f"`{len(bot.guilds)}`", inline=True)
    embed.add_field(name="Library", value="`discord.py`", inline=True)
    embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)


# 17. AVATAR
@bot.tree.command(name="avatar", description="Get a user's avatar image.")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    member = member or interaction.user
    embed = discord.Embed(title=f"🖼️ {member.name}'s Avatar", color=discord.Color.dark_theme())
    embed.set_image(url=member.display_avatar.url)
    await interaction.followup.send(embed=embed)


# 18. PING
@bot.tree.command(name="ping", description="Check bot response latency.")
async def ping(interaction: discord.Interaction):
    await interaction.response.defer()
    latency = round(bot.latency * 1000)
    await interaction.followup.send(f"🏓 Pong! Latency: `{latency}ms`")

# ---------------------------------------------------------
# START BOT
# ---------------------------------------------------------
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        raise ValueError("DISCORD_TOKEN environment variable is missing!")
    bot.run(TOKEN)
