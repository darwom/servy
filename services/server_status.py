import discord
from mcrcon import MCRcon
import config
import asyncio


class ServerStatusService:
    def __init__(self, bot):
        self.bot = bot
        self.last_status = None  # Variable to store the last known server status
        self.lock = asyncio.Lock()  # Lock to prevent concurrent updates
        self.bot.loop.create_task(self.update_presence())  # Check status on startup

    # Function to retrieve the server status
    async def get_server_status(self):
        try:

            def rcon_command():
                with MCRcon(
                    config.RCON_IP, config.RCON_PASSWORD, port=config.RCON_PORT
                ) as mcr:
                    response = mcr.command("list")
                    return response

            response = await asyncio.get_event_loop().run_in_executor(
                None, rcon_command
            )

            if "There are 0" in response:
                return "Online, no players"
            elif "There are" in response:
                num_players = response.split()[2]  # Extract the number of players
                return f"Online, {num_players} players"
            else:
                return "Online"
        except Exception:
            return "Offline"

    # Method to update the bot's presence based on the server status
    async def update_presence(self):
        async with self.lock:
            status = await self.get_server_status()

            if status != self.last_status:
                self.last_status = status  # Update the last known status

                if "Offline" in status:
                    activity = discord.Activity(
                        type=discord.ActivityType.watching, name="Server offline"
                    )
                elif "no players" in status:
                    activity = discord.Activity(
                        type=discord.ActivityType.playing, name="Online"
                    )
                else:
                    activity = discord.Activity(
                        type=discord.ActivityType.playing, name=status
                    )

                await self.bot.change_presence(
                    status=discord.Status.online, activity=activity
                )

    # Method called when a log change is detected by the MinecraftLogWatcher
    async def on_log_change(self):
        await self.update_presence()
