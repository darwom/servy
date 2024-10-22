import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from datetime import datetime
import re


class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.is_canceled = False

    @app_commands.command(name="backup", description="Backup messages from the channel")
    @app_commands.describe(
        user="User to backup messages for (default: all users)",
        limit="Maximum number of messages to backup (default: all messages)",
        download_attachments="Download message attachments and other media (default: False)",
        minimal="Backup only the essential information (default: False)",
        upload="Upload the backup file to the channel if possible (default: False)",
    )
    async def backup(
        self,
        interaction: discord.Interaction,
        user: discord.User = None,
        limit: int = None,
        download_attachments: bool = False,
        minimal: bool = False,
        upload: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        channel_id = channel.id
        default_limit = 1000000
        limit = limit or default_limit
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_folder = f"./output/backups"
        channel_folder = f"{backup_folder}/{channel_id}"
        attachments_folder = f"{channel_folder}/attachments"

        # os.makedirs(backup_folder, exist_ok=True)
        os.makedirs(attachments_folder, exist_ok=True)
        os.makedirs(channel_folder, exist_ok=True)

        backup_file = f"{channel_folder}/{timestamp}_backup.json"

        def get_basic_data(channel, timestamp):
            return {
                "backup_date": timestamp,
                "is_complete": not (limit < default_limit or user),
                "download_attachments": download_attachments,
                "minimal": minimal,
                "channel": {
                    "id": channel.id,
                    "type": str(channel.type),
                    "jump_url": (
                        channel.jump_url if hasattr(channel, "jump_url") else None
                    ),
                    "created_at": channel.created_at.isoformat(),
                },
            }

        def get_guild_channel_data(channel):
            return {
                "guild_id": channel.guild.id if channel.guild else None,
                "name": channel.name,
                "topic": channel.topic if hasattr(channel, "topic") else None,
                "nsfw": channel.nsfw if hasattr(channel, "nsfw") else None,
                "category_id": (
                    channel.category_id if hasattr(channel, "category_id") else None
                ),
                "category": (
                    channel.category.name if hasattr(channel, "category") else None
                ),
                "parent_id": (
                    channel.parent_id if hasattr(channel, "parent_id") else None
                ),
                "mention": channel.mention if hasattr(channel, "mention") else None,
            }

        def get_dm_data(channel):
            return {
                "recipients": [
                    {
                        "id": recipient.id,
                        "display_name": (
                            recipient.display_name
                            if recipient.display_name
                            else recipient.name
                        ),
                    }
                    for recipient in channel.recipients
                ],
            }

        def get_thread_data(channel):
            return {
                "owner_id": channel.owner_id,
                "message_count": channel.message_count,
                "member_count": channel.member_count,
                "thread_metadata": {
                    "archived": channel.archived,
                    "auto_archive_duration": channel.auto_archive_duration,
                    "archive_timestamp": channel.archive_timestamp.isoformat(),
                    "locked": channel.locked,
                },
            }

        users_set = set()
        backup_data = get_basic_data(channel, timestamp)
        filesize_limit = 10 * 1024 * 1024

        if isinstance(channel, discord.DMChannel):
            backup_data["channel"].update(get_dm_data(channel))
            users_set = set(channel.recipients)
        elif isinstance(channel, discord.GroupChannel):
            backup_data["channel"].update(get_dm_data(channel))
            backup_data["channel"]["name"] = (
                channel.name if channel.name else "Unnamed Group"
            )
            backup_data["channel"]["owner_id"] = channel.owner.id
            users_set = set(channel.recipients)
        else:
            backup_data["channel"].update(get_guild_channel_data(channel))
            users_set = {member for member in channel.guild.members if channel.guild}
            # filesize_limit = channel.guild.filesize_limit # gives 25mb even though its 10mb
        if isinstance(channel, discord.Thread):
            backup_data["channel"].update(get_thread_data(channel))
        elif isinstance(channel, discord.VoiceChannel):
            backup_data["channel"]["bitrate"] = channel.bitrate
            backup_data["channel"]["user_limit"] = channel.user_limit
            backup_data["channel"]["rtc_region"] = channel.rtc_region

        backup_data["channel"]["messages"] = []

        processed_messages = 0
        global downloaded_files
        downloaded_files = 0
        global skipped_files
        skipped_files = 0

        async for message in channel.history(limit=limit):
            # Process only if no user filter is applied or if the message is from the specified user
            if user and message.author.id != user.id:
                continue

            if self.is_canceled:
                print("Backup process was canceled.")
                return

            # Add user to the set of users if not already present
            if message.author not in users_set:
                users_set.add(message.author)

            # Build message data with mandatory fields
            msg_data = {
                "id": message.id,
                "author": {
                    "id": str(message.author.id),
                    "display_name": message.author.display_name,
                },
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
                "type": str(message.type),
            }

            # Add only if they exist
            if not minimal:
                if message.edited_at:
                    msg_data["edited_timestamp"] = message.edited_at.isoformat()
                if message.reference and message.reference.message_id:
                    msg_data["reply_to"] = message.reference.message_id
                if message.pinned:
                    msg_data["pinned"] = True
                if message.flags:
                    msg_data["flags"] = [str(flag) for flag in message.flags]
                if message.mentions:
                    msg_data["mentions"] = [
                        {"id": mention.id, "name": mention.display_name}
                        for mention in message.mentions
                    ]
                if message.reference:
                    msg_data["reference"] = {
                        "message_id": message.reference.message_id,
                        "channel_id": message.reference.channel_id,
                        "guild_id": message.reference.guild_id,
                        "fail_if_not_exists": message.reference.fail_if_not_exists,
                    }
                if message.poll:
                    msg_data["poll"] = message.poll._to_dict()
                if message.activity:
                    msg_data["activity"] = message.activity
                if message.application:
                    msg_data["application"] = {
                        "id": message.application.id,
                        "name": message.application.name,
                    }
                if message.webhook_id:
                    msg_data["webhook_id"] = message.webhook_id
                if message.components:
                    msg_data["components"] = [
                        component.to_dict() for component in message.components
                    ]
                if message.mention_everyone:
                    msg_data["mention_everyone"] = True
                if message.channel_mentions:
                    msg_data["channel_mentions"] = [
                        {"id": mention.id, "name": mention.name}
                        for mention in message.channel_mentions
                    ]
                if message.role_mentions:
                    msg_data["role_mentions"] = [
                        {"id": mention.id, "name": mention.name}
                        for mention in message.role_mentions
                    ]
                if message.thread:
                    msg_data["thread"] = {
                        "id": message.thread.id,
                        "name": message.thread.name,
                        "parent_id": message.thread.parent_id,
                        "owner_id": message.thread.owner_id,
                    }
                if message.interaction_metadata:
                    msg_data["interaction_metadata"] = {
                        "id": message.interaction_metadata.id,
                        "type": message.interaction_metadata.type,
                        "created_at": message.interaction_metadata.created_at.isoformat(),
                        "user": {
                            "id": message.interaction_metadata.user.id,
                            "name": message.interaction_metadata.user.name,
                        },
                    }
                if message.is_system():
                    msg_data["system_content"] = message.system_content
                if (
                    message.mentions
                    or message.channel_mentions
                    or message.role_mentions
                    or message.mention_everyone
                ):
                    msg_data["clean_content"] = message.clean_content

            async def download_file(url, file_path):
                if os.path.exists(file_path):
                    global skipped_files
                    skipped_files += 1
                    return False

                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            with open(file_path, "wb") as f:
                                f.write(await resp.read())
                                global downloaded_files
                                downloaded_files += 1
                            return True
                        skipped_files += 1
                return False

            # Handle stickers
            if message.stickers and not minimal:
                msg_data["stickers"] = []
                for sticker in message.stickers:
                    msg_data["stickers"].append(
                        {"id": sticker.id, "name": sticker.name, "url": sticker.url}
                    )

                    if not download_attachments:
                        continue
                    sticker_path = os.path.join(backup_folder, "stickers")
                    os.makedirs(sticker_path, exist_ok=True)
                    sticker_name = sticker.url.split("/")[-1]
                    sticker_file = os.path.join(sticker_path, sticker_name)

                    await download_file(sticker.url, sticker_file)

            # Handle reactions
            if message.reactions and not minimal:
                msg_data["reactions"] = []
                for reaction in message.reactions:
                    users = [str(user.id) async for user in reaction.users()]
                    reaction_data = {"emoji": str(reaction.emoji), "users": users}
                    msg_data["reactions"].append(reaction_data)

            # Handle attachments
            if message.attachments and not minimal:
                msg_data["attachments"] = []
                for attachment in message.attachments:
                    msg_data["attachments"].append(
                        {
                            "id": attachment.id,
                            "filename": attachment.filename,
                            "local_url": f"/attachments/{channel_id}/{attachment.id}/{attachment.filename}",
                            "url": attachment.url,
                            "spoiler": attachment.is_spoiler(),
                        }
                    )

                    if download_attachments:
                        attachment_path = os.path.join(
                            attachments_folder,
                            str(channel_id),
                            str(attachment.id),
                        )
                        os.makedirs(attachment_path, exist_ok=True)
                        file_path = os.path.join(attachment_path, attachment.filename)

                        if not os.path.exists(file_path):
                            await attachment.save(file_path)
                            downloaded_files += 1
                        else:
                            skipped_files += 1

            # Handle embeds
            if message.embeds and not minimal:
                msg_data["embeds"] = []
                attachment_pattern = re.compile(
                    r"https://cdn\.discordapp\.com/attachments/(?P<channel_id>\d+)/(?P<attachment_id>\d+)/(?P<filename>[^?]+)"
                )
                for embed in message.embeds:
                    msg_data["embeds"].append(embed.to_dict())

                    # Download embed files if the URL matches the expected Discord attachment pattern
                    if download_attachments and embed.url:
                        match = attachment_pattern.match(embed.url)
                        if not match:
                            continue
                        combined_ids = f"{match.group('channel_id')}/{match.group('attachment_id')}"
                        attachment_path = os.path.join(attachments_folder, combined_ids)
                        file = os.path.join(attachment_path, match.group("filename"))
                        os.makedirs(attachment_path, exist_ok=True)

                        await download_file(embed.url, file)

            # Download emojis in the message based on emoji IDs
            if download_attachments:
                emojis = re.compile(r"<:(\w+):(\d+)>").findall(message.content)
                for emoji_name, emoji_id in emojis:
                    base_emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}"
                    emoji_path = os.path.join(backup_folder, "emojis")

                    os.makedirs(emoji_path, exist_ok=True)

                    # Try to download .gif version first
                    emoji_url_gif = f"{base_emoji_url}.gif"
                    emoji_gif = os.path.join(emoji_path, f"{emoji_id}.gif")
                    emoji_url_webp = f"{base_emoji_url}.webp"
                    emoji_webp = os.path.join(emoji_path, f"{emoji_id}.webp")

                    if not await download_file(emoji_url_gif, emoji_gif):
                        await download_file(emoji_url_webp, emoji_webp)

            # Add message data to backup
            backup_data["channel"]["messages"].append(msg_data)
            processed_messages += 1

            # Update the progress message every 100 messages
            if processed_messages % 100 == 0:
                await interaction.edit_original_response(
                    content=f"Backing up messages... {processed_messages} processed.",
                    view=CancelButton(self, interaction),
                )

        if processed_messages > 1000:
            await interaction.edit_original_response(
                content=f"Processing complete! Saving backup...",
                view=None,
            )

        # Add user data to the backup
        if user:
            users_set = {user}
        if not minimal:
            backup_data["users"] = []
        for user in users_set:
            if minimal:
                continue
            user_data = {
                "id": str(user.id),
                "username": user.name,
                "global_name": user.global_name if user.global_name else None,
                "display_name": user.display_name if user.display_name else None,
                "discriminator": user.discriminator,
                "avatar": user.avatar.url if user.avatar else None,
                "bot": user.bot,
                "system": user.system,
                "mention": user.mention,
            }
            if user.display_avatar:
                if (
                    user.avatar
                    and user.display_avatar.url != user.avatar.url
                    or not user.avatar
                ):
                    user_data["display_avatar"] = user.display_avatar.url

            # Add only if available
            if user.public_flags:
                user_data["public_flags"] = user.public_flags.value
            if user.banner:
                user_data["banner"] = user.banner.url
            if user.accent_color:
                user_data["accent_color"] = user.accent_color.value
            if user.color:
                user_data["color"] = user.color.value
            if user.created_at:
                user_data["created_at"] = user.created_at.isoformat()
            if user.avatar_decoration:
                user_data["avatar_decoration"] = user.avatar_decoration.url
            if user.avatar_decoration_sku_id:
                user_data["avatar_decoration_sku_id"] = user.avatar_decoration_sku_id
            if isinstance(user, discord.Member):
                if user.roles:
                    user_data["roles"] = [
                        {"id": role.id, "name": role.name} for role in user.roles
                    ]
                if user.premium_since:
                    user_data["premium_since"] = user.premium_since.isoformat()
                if user.nick:
                    user_data["nick"] = user.nick

            backup_data["users"].append(user_data)

            # Download profile pictures of users
            if download_attachments:
                avatar_path = os.path.join(backup_folder, "avatars")
                os.makedirs(avatar_path, exist_ok=True)

                for user in users_set:
                    avatar_url = user.avatar.url if user.avatar else None
                    display_avatar_url = (
                        user.display_avatar.url if user.display_avatar else None
                    )
                    if avatar_url:
                        image_name = avatar_url.split("/")[-1].split("?")[0]
                        avatar_file = os.path.join(avatar_path, image_name)
                        await download_file(avatar_url, avatar_file)

                    if display_avatar_url and display_avatar_url != avatar_url:
                        image_name = display_avatar_url.split("/")[-1].split("?")[0]
                        display_avatar_file = os.path.join(avatar_path, image_name)
                        await download_file(display_avatar_url, display_avatar_file)

        # Save the backup to a JSON file
        try:
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=4)
            print(f"Backup saved to {backup_file}")

            # Downloaded files info
            downloaded_files_message = (
                f"Downloaded {downloaded_files} files. Skipped {skipped_files} files."
                if download_attachments
                else ""
            )

            upload_message = ""
            file = None

            if upload:
                if os.path.getsize(backup_file) < filesize_limit:
                    file = discord.File(backup_file)
                else:
                    upload_message = f"\nBackup file exceeds the upload limit of {filesize_limit / 1024 / 1024} MB."

            # Final message after completion
            await interaction.edit_original_response(
                content=f"Backup complete! {processed_messages} messages saved. {downloaded_files_message}{upload_message}",
                attachments=[file] if file else [],
                view=None,
            )
        except Exception as e:
            print(e)
            await interaction.edit_original_response(
                content=f"Error saving backup: {e}", view=None
            )


class CancelButton(discord.ui.View):
    def __init__(self, parent, interaction, timeout=60):
        super().__init__(timeout=timeout)
        self.parent = parent
        self.interaction = interaction

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.parent.is_canceled = True
        for child in self.children:
            child.disabled = True

        await self.interaction.edit_original_response(
            content="Process was canceled.", view=None
        )

        self.parent.is_canceled = False


# Add the cog to the bot
async def setup(bot):
    await bot.add_cog(BackupCog(bot))
