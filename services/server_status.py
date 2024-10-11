import discord
from mcrcon import MCRcon
import config
import asyncio


class ServerStatusService:
    def __init__(self, bot):
        self.bot = bot
        self.last_status = None  # Variable zum Speichern des letzten Status
        self.lock = asyncio.Lock()  # Lock to prevent concurrent updates

    # Funktion zum Abrufen des Serverstatus
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
                num_players = response.split()[2]  # Spieleranzahl extrahieren
                return f"Online, {num_players} players"
            else:
                return "Online"
        except Exception:
            return "Offline"

    # Methode zum Aktualisieren der Bot-Präsenz basierend auf dem Serverstatus
    async def update_presence(self):
        async with self.lock:
            status = await self.get_server_status()

            if status != self.last_status:
                self.last_status = status  # Letzten bekannten Status aktualisieren

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

    # Methode, die aufgerufen wird, wenn eine Log-Änderung vom MinecraftLogWatcher erkannt wird
    async def on_log_change(self):
        await self.update_presence()
