import json
import os
import secrets
import sqlite3
import time
from urllib.parse import urlencode

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ----------------------------------------------------------------- settings
BOT_OWNER_ID = 1371881471765250213  

TOKEN = os.environ.get("DISCORD_TOKEN")
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
REDIRECT_URI = os.environ.get("REDIRECT_URI")
PORT = int(os.environ.get("PORT") or 10000)

API = "https://discord.com/api/v10"
STATE_TTL = 600
CONFIG_FILE = "config.json"
DB_FILE = "tokens.db"

intents = discord.Intents.default()
intents.members = True

# ----------------------------------------------------------------- Database Setup
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_user_tokens(user_id: int, access_token: str, refresh_token: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, access_token, refresh_token, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            access_token=excluded.access_token,
            refresh_token=excluded.refresh_token,
            updated_at=excluded.updated_at
    """, (str(user_id), access_token, refresh_token, time.time()))
    conn.commit()
    conn.close()

# ----------------------------------------------------------------- Config Setup
def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

config: dict = load_config()
pending_states: dict[str, dict] = {}


def page(text: str, ok: bool = True, status: int = 200) -> web.Response:
    color = "#3ba55d" if ok else "#ed4245"
    title_text = "Success!" if ok else "Verification Failed"
    
    if ok:
        text = "Your verification has been completed successfully. You may now safely close this browser tab and return to Discord."
    
    bg_image_url = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRtBl4SWAWsixnE06Rm52arUvHKMbF8ki7iloyn871CeN0oIHxK-7vhtrA&s=10"
    
    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verification Portal</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{
        background: url('{bg_image_url}') no-repeat center center fixed;
        background-size: cover;
        color: #f8fafc;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100vh;
        margin: 0;
        padding: 20px;
    }}
    .card {{
        background: rgba(10, 12, 16, 0.88);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 16px;
        padding: 40px 30px;
        max-width: 420px;
        width: 100%;
        text-align: center;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.8);
    }}
    h1 {{
        color: {color};
        font-size: 28px;
        margin-top: 0;
        margin-bottom: 16px;
        letter-spacing: -0.5px;
    }}
    p {{
        font-size: 15px;
        line-height: 1.6;
        color: #f1f5f9;
        margin: 0;
    }}
</style>
</head>
<body>
<div class="card">
    <h1>{title_text}</h1>
    <p>{text}</p>
</div>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html", status=status)

# ---------------------------------------------------------------- verify button
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, custom_id="verify:start")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = config.get(str(interaction.guild_id))
        if not cfg:
            return await interaction.response.send_message(
                "Verification isn't set up here yet.", ephemeral=True
            )
        role = interaction.guild.get_role(cfg["role_id"])
        if role in interaction.user.roles:
            return await interaction.response.send_message("You're already verified.", ephemeral=True)

        state = secrets.token_urlsafe(24)
        pending_states[state] = {
            "user_id": interaction.user.id,
            "guild_id": interaction.guild_id,
            "t": time.time(),
        }
        url = "https://discord.com/oauth2/authorize?" + urlencode(
            {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": "identify guilds.join",
                "state": state,
                "prompt": "consent",
            }
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Continue to verify", url=url))
        await interaction.response.send_message(
            f"To verify, approve the request on the next screen. Verifying gives you "
            f"{role.mention} role. Nothing happens unless you tap Authorize.",
            view=view,
            ephemeral=True,
        )

# ------------------------------------------------------------------------- bot
class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        self.add_view(VerifyView())
        await self.tree.sync()

        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text="Bot is running."))
        app.router.add_get("/callback", self.oauth_callback)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
        print(f"Web server listening on port {PORT}")
        print(f"Redirect URI in use: {REDIRECT_URI}")

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    async def refresh_user_token(self, refresh_token: str) -> tuple[str, str] | None:
        async with self.http_session.post(
            f"{API}/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        ) as r:
            if r.status == 200:
                data = await r.json()
                return data["access_token"], data["refresh_token"]
            return None

    async def add_member_to_guild(self, user_id: str, access_token: str, refresh_token: str, target_guild_id: int) -> bool:
        url = f"{API}/guilds/{target_guild_id}/members/{user_id}"
        headers = {"Authorization": f"Bot {TOKEN}"}
        
        async with self.http_session.put(url, headers=headers, json={"access_token": access_token}) as r:
            if r.status in (201, 204):
                return True
            if r.status == 401:
                refreshed = await self.refresh_user_token(refresh_token)
                if refreshed:
                    new_access, new_refresh = refreshed
                    save_user_tokens(int(user_id), new_access, new_refresh)
                    async with self.http_session.put(url, headers=headers, json={"access_token": new_access}) as r2:
                        return r2.status in (201, 204)
        return False

    async def oauth_callback(self, request: web.Request):
        code = request.query.get("code")
        state = request.query.get("state")
        entry = pending_states.pop(state, None) if state else None
        if request.query.get("error"):
            return page("You cancelled the authorization. Press Verify again to retry.", False, 400)
        if not code or not entry or time.time() - entry["t"] > STATE_TTL:
            return page("Invalid or expired link. Press Verify again in the server.", False, 400)

        user_id = entry["user_id"]
        cfg = config.get(str(entry["guild_id"]))
        if not cfg:
            return page("This server isn't set up.", False, 400)

        async with self.http_session.post(
            f"{API}/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
        ) as r:
            if r.status != 200:
                print("Token exchange failed:", r.status, await r.text())
                return page("Authorization failed. Check CLIENT_ID / CLIENT_SECRET.", False, 400)
            token_data = await r.json()
            access_token = token_data["access_token"]
            refresh_token = token_data["refresh_token"]

        async with self.http_session.get(
            f"{API}/users/@me", headers={"Authorization": f"Bearer {access_token}"}
        ) as r:
            if r.status != 200 or int((await r.json())["id"]) != user_id:
                return page("Account mismatch. Use the account you pressed Verify with.", False, 403)

        save_user_tokens(user_id, access_token, refresh_token)

        source = self.get_guild(entry["guild_id"])
        role = source.get_role(cfg["role_id"]) if source else None
        if source is None or role is None:
            return page("Setup problem: role not found. Tell an admin.", False, 500)
        try:
            member = source.get_member(user_id) or await source.fetch_member(user_id)
            await member.add_roles(role, reason="Passed verification")
        except discord.NotFound:
            return page("You're not in the server anymore.", False, 400)
        except discord.Forbidden:
            return page("I can't give the role. Tell an admin to move my role higher.", False, 500)

        success = await self.add_member_to_guild(str(user_id), access_token, refresh_token, cfg["target_guild_id"])
        if success:
            return page("You're verified and have been added to the other server. You can close this tab.", True)
        else:
            return page("You're verified, but I couldn't add you to the other server.", False)


bot = Bot()
# ---------------------------------------------------------------- Owner Checks
def is_bot_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id != BOT_OWNER_ID:
            await interaction.response.send_message("❌ Only the bot owner can execute pull commands.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ---------------------------------------------------------------- Pull Slash Commands
@bot.tree.command(name="lwkeypull_user", description="Pull a single authorized user into a target server.")
@is_bot_owner()
@app_commands.describe(user_id="The Discord User ID to pull", target_guild_id="The Target Guild ID")
async def lwkeypull_user(interaction: discord.Interaction, user_id: str, target_guild_id: str):
    await interaction.response.defer(ephemeral=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT access_token, refresh_token FROM users WHERE user_id = ?", (user_id.strip(),))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return await interaction.followup.send(f"❌ User `{user_id}` has not authorized or isn't in database.", ephemeral=True)

    access_token, refresh_token = row
    success = await bot.add_member_to_guild(user_id.strip(), access_token, refresh_token, int(target_guild_id.strip()))
    
    if success:
        await interaction.followup.send(f"✅ User `{user_id}` successfully pulled to server `{target_guild_id}`.", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ Failed to pull user `{user_id}` to server `{target_guild_id}`.", ephemeral=True)

@bot.tree.command(name="lwkeypull_all", description="Pull all stored authorized users into a target server.")
@is_bot_owner()
@app_commands.describe(target_guild_id="The Target Guild ID to pull all users into")
async def lwkeypull_all(interaction: discord.Interaction, target_guild_id: str):
    await interaction.response.defer(ephemeral=True)

    try:
        guild_id = int(target_guild_id.strip())
    except ValueError:
        return await interaction.followup.send("❌ Invalid Guild ID format.", ephemeral=True)

    target_guild = bot.get_guild(guild_id)
    if not target_guild:
        try:
            target_guild = await bot.fetch_guild(guild_id)
        except discord.NotFound:
            return await interaction.followup.send(f"❌ Server `{guild_id}` not found or bot isn't in it.", ephemeral=True)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, access_token, refresh_token FROM users")
    users = cursor.fetchall()
    conn.close()

    if not users:
        return await interaction.followup.send("❌ No authorized users found in database.", ephemeral=True)

    newly_added = 0
    already_in_server = 0
    failed = 0

    for uid, access_token, refresh_token in users:
        user_int_id = int(uid)
        
        member = target_guild.get_member(user_int_id)
        if member is not None:
            already_in_server += 1
            continue

        ok = await bot.add_member_to_guild(uid, access_token, refresh_token, guild_id)
        if ok:
            newly_added += 1
        else:
            failed += 1

    await interaction.followup.send(
        f"📊 **Pull Complete!**\n"
        f"- Successfully added: `{newly_added}`\n"
        f"- Already in server: `{already_in_server}`\n"
        f"- Failed: `{failed}`",
        ephemeral=True
    )

@bot.tree.command(name="lwkeypull_list", description="List all authorized users stored in the database.")
@is_bot_owner()
async def lwkeypull_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, updated_at FROM users")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return await interaction.followup.send("❌ No authorized users found in the database.", ephemeral=True)

    user_list_str = ""
    for uid, updated_at in rows:
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(updated_at))
        user_list_str += f"• <@{uid}> (`{uid}`) — Verified: {time_str}\n"

    if len(user_list_str) > 1900:
        user_list_str = user_list_str[:1900] + "\n... (list truncated)"

    embed = discord.Embed(
        title=f"Authorized Users ({len(rows)} total)",
        description=user_list_str,
        color=discord.Color.blue()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

# ---------------------------------------------------------------- Setup Verification Command
@bot.tree.command(description="Set up verification in this server and post the panel")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    role="Role members get after verifying",
    panel_channel="Where to post the verify button (default: this channel)",
)
async def setup_verify(
    interaction: discord.Interaction,
    role: discord.Role,
    panel_channel: discord.TextChannel | None = None,
):
    me = interaction.guild.me
    if role.is_default() or role.managed or role >= me.top_role:
        return await interaction.response.send_message(
            "I can't hand out that role. Pick another one, or move my role above it in Server Settings > Roles.",
            ephemeral=True,
        )

    target_guild = interaction.guild

    if not target_guild.me.guild_permissions.create_instant_invite:
        return await interaction.response.send_message(
            "I need the Create Invite permission in this server.",
            ephemeral=True,
        )

    panel = panel_channel or interaction.channel
    perms = panel.permissions_for(me)
    if not (perms.send_messages and perms.embed_links):
        return await interaction.response.send_message(
            f"I can't send messages or embeds in {panel.mention}.", ephemeral=True
        )

    config[str(interaction.guild_id)] = {"role_id": role.id, "target_guild_id": target_guild.id}
    save_config()

    embed = discord.Embed(
        title="Verification",
        description=(
            f"Complete the verification below to receive your {role.mention} role.\n"
            f"Get recognized as a verified member in **{target_guild.name}**."
        ),
        color=discord.Color.green(),
    )
    await panel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message(
        f"Done! Panel posted in {panel.mention}. Verified members get {role.mention} role "
        f"and are added to **{target_guild.name}**.",
        ephemeral=True,
    )

# ---------------------------------------------------------------- Kick Commands
@bot.tree.command(name="lwkey_kickuser", description="Kick a single authorized user from a target server.")
@is_bot_owner()
@app_commands.describe(user_id="The Discord User ID to kick", target_guild_id="The Target Guild ID to kick them from")
async def lwkey_kickuser(interaction: discord.Interaction, user_id: str, target_guild_id: str):
    await interaction.response.defer(ephemeral=True)
    
    uid = user_id.strip()
    try:
        guild_id = int(target_guild_id.strip())
    except ValueError:
        return await interaction.followup.send("❌ Invalid Guild ID format.", ephemeral=True)

    url = f"{API}/guilds/{guild_id}/members/{uid}"
    headers = {"Authorization": f"Bot {TOKEN}"}
    
    async with bot.http_session.delete(url, headers=headers) as r:
        if r.status in (204, 200):
            await interaction.followup.send(
                f"✅ Successfully kicked user `{uid}` from server `{target_guild_id}`.\n"
                f"🔒 *Their token remains safe in your database.*",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Failed to kick user `{uid}`. Status: `{r.status}`",
                ephemeral=True
            )

@bot.tree.command(name="lwkey_kickall", description="Kick all stored authorized users from a target server at once.")
@is_bot_owner()
@app_commands.describe(target_guild_id="The Target Guild ID to kick all users from")
async def lwkey_kickall(interaction: discord.Interaction, target_guild_id: str):
    await interaction.response.defer(ephemeral=True)

    try:
        guild_id = int(target_guild_id.strip())
    except ValueError:
        return await interaction.followup.send("❌ Invalid Guild ID format.", ephemeral=True)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    if not users:
        return await interaction.followup.send("❌ No authorized users found in database.", ephemeral=True)

    success_count = 0
    fail_count = 0
    headers = {"Authorization": f"Bot {TOKEN}"}

    for (uid,) in users:
        url = f"{API}/guilds/{guild_id}/members/{uid}"
        async with bot.http_session.delete(url, headers=headers) as r:
            if r.status in (204, 200):
                success_count += 1
            else:
                fail_count += 1

    await interaction.followup.send(
        f"📊 **Mass Kick Complete!**\n"
        f"- Successfully kicked: `{success_count}`\n"
        f"- Not in server / Failed: `{fail_count}`\n"
        f"🔒 *All tokens remain safe in your database.*",
        ephemeral=True
    )

bot.run(os.environ.get("DISCORD_TOKEN"))
