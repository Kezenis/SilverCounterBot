import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

DB_PATH = "counter.db"

# If you want one shared counter across all servers, keep KEY = "global".
# If you prefer per-server counters, set KEY to the guild id at runtime.
GLOBAL_KEY = "global"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Database helpers ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS counters (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            );
        """)
        # Ensure the global row exists
        await db.execute("""
            INSERT OR IGNORE INTO counters(key, value) VALUES (?, 0);
        """, (GLOBAL_KEY,))
        await db.commit()

async def get_count(key: str = GLOBAL_KEY) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM counters WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def add_count(delta: int, key: str = GLOBAL_KEY) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO counters(key, value) VALUES(?, 0)
            ON CONFLICT(key) DO UPDATE SET value = value + excluded.value + ? - 0;
        """, (key, delta))
        await db.commit()
        # Fetch updated value
        return await get_count(key)

async def set_count(value: int, key: str = GLOBAL_KEY) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO counters(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """, (key, value))
        await db.commit()
        return await get_count(key)

async def reset_count(key: str = GLOBAL_KEY) -> int:
    return await set_count(0, key)

# --- Slash commands ---
@bot.event
async def on_ready():
    await init_db()
    try:
        # Sync global application commands (may take up to ~1 hour the first time; per-guild is instant)
        # For instant dev testing, uncomment the guild line and put your server ID, then re-sync.
        # guild = discord.Object(id=YOUR_GUILD_ID)
        # bot.tree.copy_global_to(guild=guild)
        # await bot.tree.sync(guild=guild)
        await bot.tree.sync()
    except Exception as e:
        print("Command sync failed:", e)
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.tree.command(name="went", description="Increment the shared counter by N (default 1).")
@app_commands.describe(n="How much to add (can be negative to subtract). Default = 1")
async def went(interaction: discord.Interaction, n: int = 1):
    if n == 0:
        await interaction.response.send_message("Nothing changed (n = 0).", ephemeral=True)
        return
    new_val = await add_count(n, GLOBAL_KEY)
    sign = "➕" if n > 0 else "➖"
    await interaction.response.send_message(f"{sign} Added **{n}**. Count is now **{new_val}**.")

@bot.tree.command(name="count", description="Show the current shared count.")
async def count_cmd(interaction: discord.Interaction):
    val = await get_count(GLOBAL_KEY)
    await interaction.response.send_message(f"📊 Current count: **{val}**")

@bot.tree.command(name="setcount", description="Set the shared count to an exact value.")
@app_commands.describe(value="New exact value")
async def setcount(interaction: discord.Interaction, value: int):
    new_val = await set_count(value, GLOBAL_KEY)
    await interaction.response.send_message(f"🛠️ Set count to **{new_val}**")

@bot.tree.command(name="resetcount", description="Reset the shared count to 0.")
async def resetcount(interaction: discord.Interaction):
    new_val = await reset_count(GLOBAL_KEY)
    await interaction.response.send_message(f"♻️ Counter reset. Count is now **{new_val}**")

# Optional: simple message command for quick taps (prefix "!")
@bot.command()
async def wentmsg(ctx, n: int = 1):
    new_val = await add_count(n, GLOBAL_KEY)
    await ctx.send(f"✅ Added {n}. Count is now **{new_val}**")

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Please set DISCORD_TOKEN in a .env file or environment variable.")
    bot.run(TOKEN)
