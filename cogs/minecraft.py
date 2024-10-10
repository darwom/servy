from discord.ext import commands, tasks
from mcrcon import MCRcon
import config
import os
import asyncio


class Minecraft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if config.LOG_FILE_PATH == "":
            return
        self.watch_log.start()  # Start the log watching loop

    # Generator function to tail a file
    async def tail_logfile(self, file):
        file.seek(0, os.SEEK_END)
        while True:
            line = file.readline()
            if not line:
                await asyncio.sleep(1)
                continue
            yield line

    # Loop to watch the Minecraft server log file
    @tasks.loop(seconds=1)
    async def watch_log(self):
        try:
            with open(config.LOG_FILE_PATH, "r") as file:
                log_lines = self.tail_logfile(file)
                channel = self.bot.get_channel(config.CONSOLE_CHANNEL_ID)
                line = file.readline()
                async for line in log_lines:
                    await channel.send(line.strip())
        except Exception as e:
            print(f"Error watching log file: {e}")

    # Command to send a command to the Minecraft server
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # Check if the message is in the specified channel
        if message.channel.id == config.CONSOLE_CHANNEL_ID:
            try:
                # Send the message content as an RCON command to the Minecraft server
                with MCRcon(
                    config.RCON_IP, config.RCON_PASSWORD, port=config.RCON_PORT
                ) as mcr:
                    response = mcr.command(message.content)
                    await message.channel.send(f"Command Response: {response}")
            except Exception as e:
                print(f"Error sending command to RCON: {e}")
                await message.channel.send(f"Error: {e}")

    @watch_log.before_loop
    async def before_watch_log(self):
        await self.bot.wait_until_ready()  # Ensure the bot is ready before starting the task


async def setup(bot):
    await bot.add_cog(Minecraft(bot))
