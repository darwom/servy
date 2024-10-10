from discord.ext import commands
import config
from mcrcon import MCRcon


class Minecraft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Function to send an RCON command to the Minecraft server
    def send_rcon_command(self, command):
        try:
            with MCRcon(
                config.RCON_IP, config.RCON_PASSWORD, port=config.RCON_PORT
            ) as mcr:
                response = mcr.command(command)
                return response
        except Exception as e:
            print(f"Error sending RCON command: {e}")
            return None

    # Command to send a message to the Minecraft server
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:  # Ignore bot messages
            return

        if message.channel.id == config.CONSOLE_CHANNEL_ID:
            try:
                response = self.send_rcon_command(message.content)
                if response:
                    await message.channel.send(f"{response}")
            except Exception as e:
                print(f"Error sending command to RCON: {e}")
                await message.channel.send(f"Error: {e}")


async def setup(bot):
    await bot.add_cog(Minecraft(bot))
