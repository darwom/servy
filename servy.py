import discord
import config
from discord.ext import commands
import asyncio
import os


# Discord bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# Automatically load all cogs from the 'cogs' directory
async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            # Remove the '.py' extension and load the cog
            await bot.load_extension(f"cogs.{filename[:-3]}")


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
