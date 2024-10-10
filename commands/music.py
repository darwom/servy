import discord
from discord import app_commands
from discord.ext import commands

# Placeholder for the Music Cog. Does not play music yet


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Slash Command: /play
    @app_commands.command(name="play", description="Plays a song from a URL")
    async def play_song(self, interaction: discord.Interaction, url: str):
        await interaction.response.send_message(f"Playing song from {url}")

    # Slash Command: /stop
    @app_commands.command(name="stop", description="Stops the current song")
    async def stop_song(self, interaction: discord.Interaction):
        await interaction.response.send_message("Stopping song...")


# Setup function to add the Cog to the bot
async def setup(bot):
    await bot.add_cog(Music(bot))
