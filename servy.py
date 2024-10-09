import discord
import config
from discord.ext import commands
import asyncio


# Discord bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# Load extensions
async def load_extensions():
    for extension in ["cogs.minecraft", "cogs.music"]:
        await bot.load_extension(extension)


# Event: Bot is ready
@bot.event
async def on_ready():
    print(f"Bot is logged in as {bot.user}")

    # Sync commands with Discord
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands globally.")
    except Exception as e:
        print(f"Error syncing commands: {e}")


# Start the bot
async def main():
    async with bot:
        await load_extensions()
        await bot.start(config.DISCORD_TOKEN)


# Run the bot
asyncio.run(main())
