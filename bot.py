import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncpg

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("No DISCORD_TOKEN found. Set it in Railway → Variables.")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("No DATABASE_URL found. Add Railway PostgreSQL and ensure the var is present.")

GLOBAL_KEY = "global"  # change to per-guild/channel later if you want
_pg_pool = None

async def get_pool():
    global _pg_pool
    if _pg_pool is None:
        # asyncpg understands sslmode=require in the URL from Railway
        _pg_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    return _pg_pool

# --- DB helpers ---
async def init_db():
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute("""
            CREATE TABLE IF NOT EXISTS counters(
              key   TEXT PRIMARY KEY,
              value INTEGER NOT NULL
            );
        """)
        await con.execute("""
            INSERT INTO counters(key, value) VALUES($1, 0)
            ON CONFLICT (key) DO NOTHING;
        """, GLOBAL_KEY)

async def get_count(key: str = GLOBAL_KEY) -> int:
    pool = await get_pool()
    async with pool.acquire() as con:
        row = await con.fetchrow("SELECT value FROM counters WHERE key=$1", key)
        return int(row["value"]) if row else 0

async def add_count(delta: int, key: str = GLOBAL_KEY) -> int:
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO counters(key, value) VALUES($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = counters.value + EXCLUDED.value;
        """, key, delta)
        row = await con.fetchrow("SELECT value FROM counters WHERE key=$1", key)
        return int(row["value"])

async def set_count(value: int, key: str = GLOBAL_KEY) -> int:
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO counters(key, value) VALUES($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
        """, key, value)
        row = await con.fetchrow("SELECT value FROM counters WHERE key=$1", key)
        return int(row["value"])

async def reset_count(key: str = GLOBAL_KEY) -> int:
    return await set_count(0, key)

# --- Bot setup & slash commands ---
intents = discord.Intents.none()
bot = commands.Bot(command_prefix="!", intents=intents)

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
