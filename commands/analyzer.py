import discord
from discord import app_commands
from discord.ext import commands


class MessageAnalyzer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Slash command to analyze messages in a channel
    @app_commands.command(
        name="analyze",
        description="Counts the number of messages sent by each user in the channel",
    )
    async def analyze(self, interaction: discord.Interaction):
        # Slash command to count and analyze messages sent by users
        await interaction.response.defer(thinking=True)  # Defer the response

        user_message_count = {}

        # Notify the user that analysis has started
        progress_message = await interaction.followup.send(
            "Analyzing messages... This might take a while."
        )

        # Iterate through the channel history and count messages
        async for message in interaction.channel.history(limit=1000000):
            # Skip the bot's own progress message
            if message.id == progress_message.id:
                continue

            # Count messages for each user
            if message.author in user_message_count:
                user_message_count[message.author] += 1
            else:
                user_message_count[message.author] = 1

        # Sort users by message count
        sorted_user_message_count = sorted(
            user_message_count.items(), key=lambda x: x[1], reverse=True
        )

        # Create an output string for the top contributors
        output = "\n".join(
            [
                f"{user.name}: {count} messages"
                for user, count in sorted_user_message_count
            ]
        )

        # Create an embed to display the results
        embed = discord.Embed(
            title="Message Count",
            description="Number of messages per user",
            color=0x7289DA,
        )
        embed.add_field(
            name="Top Contributors", value=output or "No messages found", inline=False
        )

        # Edit the original message with the final result
        await progress_message.edit(content=None, embed=embed)


# Add cog to the bot
async def setup(bot):
    await bot.add_cog(MessageAnalyzer(bot))
