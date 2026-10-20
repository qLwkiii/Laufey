import discord
from discord import app_commands
from discord.ext import commands
import datetime

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# 1. Kick Command
@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer()
    await member.kick(reason=reason)
    await interaction.followup.send(f"✅ {member.mention} was kicked. Reason: {reason}")

# 2. Ban Command
@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer()
    await member.ban(reason=reason)
    await interaction.followup.send(f"⛔ {member.mention} was banned. Reason: {reason}")

# 3. Timeout Command
@bot.tree.command(name="timeout", description="Timeout (mute) a member for a set duration in minutes")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, duration_minutes: int, reason: str = "No reason provided"):
    await interaction.response.defer()
    duration = datetime.timedelta(minutes=duration_minutes)
    await member.timeout(duration, reason=reason)
    await interaction.followup.send(f"🔇 {member.mention} has been timed out for {duration_minutes} minute(s). Reason: {reason}")

# 4. Remove Timeout Command
@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    await member.timeout(None)
    await interaction.followup.send(f"🔊 Timeout removed for {member.mention}.")

# Error Handler
@kick.error
@ban.error
@timeout.error
@untimeout.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        else:
            await interaction.followup.send("❌ You do not have permission to use this command.", ephemeral=True)


bot.run(os.environ.get("DISCORD_TOKEN"))
