from typing import Union

import discord
from discord import app_commands
from discord.ext import commands


class Move(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="move", description="Move all Users to a voice channel")
    @app_commands.rename(from_channel='from')
    @app_commands.describe(to="The voice channel to move to", from_channel="The voice channel from which everyone will be moved")
    async def move(self, interaction: discord.Interaction, to: discord.VoiceChannel = None, from_channel: discord.VoiceChannel = None):
        if not interaction.user.voice:
            await interaction.response.send_message("You are not in a voice channel!")
            return

        if not to:
            to = interaction.user.voice.channel

        if from_channel and from_channel == to:
            await interaction.response.send_message("That is unnecessary!")

        if from_channel:
            await interaction.response.send_message(f"Moving everyone from {from_channel.name} to {to.name}")
            for member in from_channel.members:
                await  member.move_to(to)
            return

        await interaction.response.send_message(f"Moving everyone to {to.name}")

        for channel in interaction.guild.voice_channels:
            for member in channel.members:
                await member.move_to(to)


# Setup function to add the Cog to the bot
async def setup(bot):
    await bot.add_cog(Move(bot))
