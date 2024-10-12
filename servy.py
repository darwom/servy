import discord
import config
from discord.ext import commands
import asyncio
import os
import importlib
import inspect

# Discord bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# Generic function to load classes based on directory and parameters in __init__
async def load_modules(directory):
    for filename in os.listdir(directory):
        if not filename.endswith(".py"):
            continue

        module_name = filename[:-3]
        module = importlib.import_module(f"{directory}.{module_name}")

        for obj_name in dir(module):
            obj = getattr(module, obj_name)

            if not is_valid_class(obj, module):
                continue

            if not has_valid_init(obj):
                print(f"Skipping {obj_name}: __init__ method has unexpected parameters.")
                continue

            if directory == "commands":
                await bot.load_extension(f"{directory}.{module_name}")
                print(f"Loaded command {module_name}.")
            elif directory == "services":
                obj(bot)
                print(f"Initialized service {obj_name}.")


def is_valid_class(obj, module):
    return isinstance(obj, type) and obj.__module__ == module.__name__


def has_valid_init(obj):
    try:
        init_signature = inspect.signature(obj.__init__)
        params = list(init_signature.parameters.values())
        return len(params) == 2 and params[0].name == "self" and params[1].name == "bot"
    except Exception as e:
        print(f"Error inspecting __init__ method of {obj}: {e}")
        return False


# Event: Bot is ready
@bot.event
async def on_ready():
    print(f"Bot is logged in as {bot.user}")

    # Sync global commands
    try:
        synced = await bot.tree.sync()  # Sync globally
        print(f"Synced {len(synced)} commands globally.")
    except Exception as e:
        print(f"Error syncing commands: {e}")


# Start the bot
async def main():
    async with bot:
        await load_modules("commands")
        await load_modules("services")
        await bot.start(config.DISCORD_TOKEN)


# Run the bot
asyncio.run(main())
