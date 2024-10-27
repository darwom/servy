from datetime import timezone
import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands import Choice
import pytz
import config


class DeleteMessages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Command to delete messages based on count or search
    @app_commands.command(
        name="delete", description="Delete messages based on count or search term"
    )
    @app_commands.choices(
        delete_type=[
            Choice(name="Delete by Count", value="count"),
            Choice(name="Delete by Search", value="search"),
        ]
    )
    @app_commands.describe(
        delete_type="Select whether to delete by message count or search term",
        value="The value for the selected option: number of messages for count, term for search",
    )
    async def delete_messages(
        self,
        interaction: discord.Interaction,
        delete_type: Choice[str],
        value: str,
    ):
        # Logic based on choice selection
        if delete_type.value == "count":
            try:
                count = int(value)
                await self.prompt_delete_by_count(interaction, count)
            except ValueError:
                await interaction.response.send_message(
                    "Please provide a valid number for count.", ephemeral=True
                )
        elif delete_type.value == "search":
            search_term = value
            await self.search_and_prompt_delete(interaction, search_term)

    async def search_and_prompt_delete(self, interaction, search):
        # Search for the message containing the search term and count messages
        messages = []
        async for message in interaction.channel.history(limit=1000):
            if search.lower() in message.content.lower():
                found_message = message
                break
            messages.append(message)
        else:
            await interaction.response.send_message(
                "No message found with the search term.", ephemeral=True
            )
            return

        count_to_delete = len(messages)
        await self.prompt_delete(interaction, found_message, count_to_delete)

    async def prompt_delete_by_count(self, interaction, count):
        # Fetch messages based on the count
        messages = []
        async for message in interaction.channel.history(limit=count + 1):
            if message.id == interaction.id:  # Ignore the command message itself
                continue
            messages.append(message)

        if not messages:
            await interaction.response.send_message(
                "No messages found to delete.", ephemeral=True
            )
            return

        found_message = messages[-1]  # Get the last message in the list (count)
        await self.prompt_delete(interaction, found_message, count)

    async def prompt_delete(self, interaction, found_message, count=None):
        local_tz = pytz.timezone(config.TIMEZONE)

        # Convert the message creation time from UTC to the local timezone
        utc_time = found_message.created_at.replace(tzinfo=timezone.utc)
        local_time = utc_time.astimezone(local_tz)

        message_time = local_time.strftime("%d.%m.%Y at %H:%M")
        message_author = found_message.author.display_name

        # Split the message content into lines and prefix each line with '> '
        formatted_content = "\n".join(
            [f"> {line}" for line in found_message.content.splitlines()]
        )

        formatted_message = (
            f"**{message_author}** on {message_time}:\n{formatted_content}"
        )

        # Ask for confirmation with formatted message
        view = ConfirmDeleteView(interaction, count)
        await interaction.response.send_message(
            f"{formatted_message}\n\nDo you want to **delete {count} messages** up to this one?\n\n︕ *Feature is being tested. Don't use on important channels. Cannot be undone.*\n",
            view=view,
            ephemeral=True,
        )


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, interaction, count=None, timeout=60):
        super().__init__(timeout=timeout)
        self.interaction = interaction
        self.count = count

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Disable the buttons after the first click
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="Deleting messages...", view=self
        )

        # Delete messages based on the count
        await interaction.channel.purge(limit=self.count)

        # Edit the original response to show the deletion message
        await self.interaction.edit_original_response(
            content=f"{self.count} Messages deleted.", view=None
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable the buttons after the first click
        for child in self.children:
            child.disabled = True

        # Edit the original response to show the cancellation message
        await self.interaction.edit_original_response(
            content="Deletion cancelled.", view=None
        )


# Add cog to the bot
async def setup(bot):
    await bot.add_cog(DeleteMessages(bot))
