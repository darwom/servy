from discord.ext import commands, tasks
import config
from services.minecraft_service import tail_logfile, send_rcon_command


class Minecraft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if config.LOG_FILE_PATH == "":
            return
        self.watch_log.start()  # Start the log watching loop

    # Loop to watch the Minecraft server log file
    @tasks.loop(seconds=1)
    async def watch_log(self):
        try:
            channel = self.bot.get_channel(config.CONSOLE_CHANNEL_ID)
            async for line in tail_logfile(config.LOG_FILE_PATH):
                await channel.send(line.strip())
        except Exception as e:
            print(f"Error watching log file: {e}")

    # Command to send a message to the Minecraft server
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        if message.channel.id == config.CONSOLE_CHANNEL_ID:
            try:
                response = send_rcon_command(message.content)
                await message.channel.send(f"Command Response: {response}")
            except Exception as e:
                print(f"Error sending command to RCON: {e}")
                await message.channel.send(f"Error: {e}")

    @watch_log.before_loop
    async def before_watch_log(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Minecraft(bot))
