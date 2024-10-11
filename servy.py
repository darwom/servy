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
async def load_modules(directory, bot):
    for filename in os.listdir(directory):
        if filename.endswith(".py"):
            module_name = filename[:-3]
            module = importlib.import_module(f"{directory}.{module_name}")

            # Iterate through the objects in the module to find classes
            for obj_name in dir(module):
                obj = getattr(module, obj_name)

                # Only check classes and ensure they are defined in this module
                if isinstance(obj, type) and obj.__module__ == module.__name__:
                    try:
                        # Inspect the signature of the __init__ method
                        init_signature = inspect.signature(obj.__init__)
                        params = list(init_signature.parameters.values())

                        # Check if the __init__ method has exactly two parameters: 'self' and 'bot'
                        if (
                            len(params) == 2
                            and params[0].name == "self"
                            and params[1].name == "bot"
                        ):
                            # For commands, use bot.load_extension
                            if directory == "commands":
                                await bot.load_extension(f"{directory}.{module_name}")
                                print(f"Loaded command extension {module_name}.")
                            # For services, instantiate the class
                            elif directory == "services":
                                instance = obj(bot)
                                print(f"Initialized service {obj_name}.")
                        else:
                            print(
                                f"Skipping {obj_name}: __init__ method has unexpected parameters."
                            )
                    except Exception as e:
                        print(f"Error loading {obj_name}: {e}")


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
        await load_modules("commands", bot)
        await load_modules("services", bot)
        await bot.start(config.DISCORD_TOKEN)


# Run the bot
asyncio.run(main())
