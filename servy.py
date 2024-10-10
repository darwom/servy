import discord
import config
from discord.ext import commands
import asyncio
import os
import importlib

# Discord bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# Automatically load all command modules from the 'commands' directory
async def load_extensions():
    for filename in os.listdir("./commands"):
        if filename.endswith(".py"):
            await bot.load_extension(f"commands.{filename[:-3]}")


# Automatically load and initialize all service modules from the 'services' directory
async def load_services():
    for filename in os.listdir("./services"):
        if filename.endswith(".py"):
            service_name = filename[:-3]
            module = importlib.import_module(f"services.{service_name}")

            # Initialize the service class, but ignore non-user-defined classes like MCRcon
            for obj_name in dir(module):
                obj = getattr(module, obj_name)
                # Only instantiate if it's a class and is defined in this module (not imported)
                if isinstance(obj, type) and obj.__module__ == module.__name__:
                    try:
                        instance = obj(bot)  # Initialize the class
                        print(f"Initialized service {obj_name}.")
                    except Exception as e:
                        print(f"Error initializing service {obj_name}: {e}")


# Event: Bot is ready
@bot.event
async def on_ready():
    print(f"Bot is logged in as {bot.user}")


# Start the bot
async def main():
    async with bot:
        await load_extensions()
        await load_services()  # Load and initialize services
        await bot.start(config.DISCORD_TOKEN)


# Run the bot
asyncio.run(main())
