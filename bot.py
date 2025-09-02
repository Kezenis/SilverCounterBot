import os
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("No DISCORD_TOKEN found. Did you set it in Railway Variables?")

DB_PATH = "counter.db"
GLOBAL_KEY = "global"

intents = discord.Intents.none()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- DB helpers ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS counters (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            )
        """)
        await db.execute("INSERT OR IGNORE INTO counters(key, value) VALUES (?, 0)", (GLOBAL_KEY,))
        await db.commit()

async def get_count(key: str = GLOBAL_KEY) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM counters WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def add_count(delta: int, key: str = GLOBAL_KEY) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO counters(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = counters.value + excluded.value
        """, (key, delta))
        await db.commit()
        return await get_count(key)

async def set_count(value: int, key: str = GLOBAL_KEY) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO counters(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()
        return await get_count(key)

async def reset_count(key: str = GLOBAL_KEY) -> int:
    return await set_count(0, key)

# --- Slash commands ---
@bot.event
async def on_ready():
    await init_db()
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.tree.sync()
    print("✅ Slash commands synced.")

@bot.tree.command(name="went", description="Increment the shared counter by N (default 1).")
@app_commands.describe(n="How much to add (negative to subtract). Default = 1")
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
async def setcount_cmd(interaction: discord.Interaction, value: int):
    new_val = await set_count(value, GLOBAL_KEY)
    await interaction.response.send_message(f"🛠️ Set count to **{new_val}**")

@bot.tree.command(name="resetcount", description="Reset the shared count to 0.")
async def resetcount_cmd(interaction: discord.Interaction):
    new_val = await reset_count(GLOBAL_KEY)
    await interaction.response.send_message(f"♻️ Counter reset. Count is now **{new_val}**")

if __name__ == "__main__":
    bot.run(TOKEN)
