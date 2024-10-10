import os
import asyncio
from discord.ext import tasks
import config


# Class to handle log file monitoring
class MinecraftLogWatcher:
    def __init__(self, bot):
        self.bot = bot
        self.log_file_path = config.LOG_FILE_PATH
        self.channel_id = config.CONSOLE_CHANNEL_ID

        if self.log_file_path == "":
            return

        self.watch_log.start()

        # Function to tail the logfile asynchronously

    async def tail_logfile(self, log_file_path):
        with open(log_file_path, "r") as file:
            file.seek(0, os.SEEK_END)  # Start at the end of the file
            while True:
                line = file.readline()
                if "RCON" in line:  # Skip lines that contain "RCON"
                    continue
                if not line:
                    await asyncio.sleep(1)  # Sleep briefly and then retry
                    continue
                yield line

    # Task to monitor the log file
    @tasks.loop(seconds=1)
    async def watch_log(self):
        try:
            async for line in self.tail_logfile(self.log_file_path):
                channel = self.bot.get_channel(self.channel_id)
                await channel.send(line.strip())
        except Exception as e:
            print(f"Error watching log file: {e}")

    @watch_log.before_loop
    async def before_watch_log(self):
        await self.bot.wait_until_ready()
