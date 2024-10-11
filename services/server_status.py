import discord
from discord.ext import tasks
from mcrcon import MCRcon
import config


class ServerStatusService:
    def __init__(self, bot):
        self.bot = bot
        self.update_server_status.start()  # Start the fallback task

    # Function to get the server status
    def get_server_status(self):
        try:
            with MCRcon(
                config.RCON_IP, config.RCON_PASSWORD, port=config.RCON_PORT
            ) as mcr:
                response = mcr.command("list")
                if "There are 0" in response:
                    return "Online, no players"
                elif "There are" in response:
                    num_players = response.split()[2]  # Extract player count
                    return f"Online, {num_players} players"
                else:
                    return "Online"
        except Exception:
            return "Offline"

    # Task to update the bot's presence based on the server status
    async def update_presence(self):
        status = self.get_server_status()
        print(f"Updating server status: {status}")

        if "Offline" in status:
            activity = discord.Activity(
                type=discord.ActivityType.watching, name="Server offline"
            )
        elif "no players" in status:
            activity = discord.Activity(
                type=discord.ActivityType.playing, name="Online"
            )
        else:
            activity = discord.Activity(type=discord.ActivityType.playing, name=status)

        await self.bot.change_presence(status=discord.Status.online, activity=activity)

    # Task to update the bot's presence periodically (fallback)
    @tasks.loop(minutes=5)
    async def update_server_status(self):
        await self.update_presence()

    @update_server_status.before_loop
    async def before_update_server_status(self):
        await self.bot.wait_until_ready()

    # Method to be called when a log change is detected by MinecraftLogWatcher
    async def on_log_change(self):
        print("Log change detected, updating server status.")
        await self.update_presence()
