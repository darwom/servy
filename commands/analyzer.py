import json
import os
from types import SimpleNamespace
import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands import Choice
import matplotlib.pyplot as plt
import io
import pytz
import config
from collections import defaultdict, Counter, deque
from datetime import datetime, timedelta
import numpy as np
from commands.backup import CancelButton


class MessageAnalyzer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.is_canceled = False

    @app_commands.command(
        name="analyze", description="Analyzes messages in the channel"
    )
    @app_commands.describe(
        analysis_type="Type of analysis to perform",
        limit="Maximum number of messages to analyze (default: all messages)",
        user="User to analyze (default: all users)",
        search_term="The term to search for (only required if Word Count is selected)",
        use_backup="Use fetched backup data for analysis if available (default: True for limit > 100)",
        ephemeral="Only I can see the response (default: False)",
    )
    @app_commands.choices(
        analysis_type=[
            Choice(name="Message Count", value="message_count"),
            Choice(name="Activity Time", value="time_activity"),
            Choice(name="Activity Chart", value="activity_chart"),
            Choice(name="Word Count", value="word_count"),
        ]
    )
    async def analyze(
        self,
        interaction: discord.Interaction,
        analysis_type: Choice[str],
        limit: int = None,
        user: discord.User = None,
        search_term: str = None,
        use_backup: bool = None,
        ephemeral: bool = False,
    ):
        if analysis_type.value == "word_count" and search_term is None:
            await interaction.response.send_message(
                "You must provide a search term for word count analysis.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=ephemeral)
        limit = limit or 1000000
        adjusted_limit = limit + 1 if not ephemeral else limit

        if use_backup is None:
            use_backup = True
            if adjusted_limit < 100:
                use_backup = False

        progress_message = await interaction.followup.send(
            content="Analyzing messages... This may take a while.",
            view=CancelButton(self, interaction),
        )

        start = datetime.now()

        channel_id = interaction.channel.id
        backup_folder = config.BACKUP_PATH
        channel_folder = f"{backup_folder}/{channel_id}"
        if not backup_folder:
            use_backup = False

        messages_deque = deque()
        new_messages_fetched = 0
        backup_timestamp = None

        if use_backup and os.path.exists(channel_folder):
            backup_files = [
                f for f in os.listdir(channel_folder) if f.endswith(".json")
            ]
            backup_files.sort(reverse=True)
            for backup_file in backup_files:
                with open(
                    f"{channel_folder}/{backup_file}", "r", encoding="utf-8"
                ) as f:
                    backup_data = json.load(f)
                    if backup_data.get("is_complete", False):
                        messages_deque = deque(
                            backup_data.get("channel", {}).get("messages", [])
                        )
                        backup_timestamp = backup_data.get("backup_date")
                        break
            else:
                use_backup = False

            if messages_deque:
                last_backup_date = datetime.fromisoformat(
                    messages_deque[0]["created_at"]
                )

                async for message in interaction.channel.history(limit=adjusted_limit):
                    # Check if the message is older than the last backup message eg "2024-10-25T23:34:25.602000+00:00"
                    if message.created_at > last_backup_date:
                        if message.id == progress_message.id:
                            continue
                        new_messages_fetched += 1
                        messages_deque.appendleft(
                            {
                                "id": message.id,
                                "author": {
                                    "id": message.author.id,
                                    "display_name": message.author.display_name,
                                },
                                "content": message.content,
                                "created_at": message.created_at.isoformat(),
                                "type": str(message.type),
                            }
                        )
                    else:
                        break

        user_message_count = defaultdict(int)
        user_word_count = defaultdict(int)
        user_time_activity = defaultdict(list)

        timezone = pytz.timezone(config.TIMEZONE)

        message_count = 0

        async def analyze_message(message):
            if message.id == progress_message.id:
                return

            nonlocal message_count
            message_count += 1
            if message_count % (10000 if messages_deque else 1000) == 0:
                await progress_message.edit(
                    content=f"Analyzing messages... {message_count} messages processed.",
                    view=CancelButton(self, interaction),
                )

            if user and int(message.author.id) != user.id:
                return

            if analysis_type.value == "message_count":
                user_message_count[(message.author.display_name)] += 1
            elif analysis_type.value in ["time_activity", "activity_chart"]:
                localized_time = datetime.fromisoformat(
                    str(message.created_at)
                ).astimezone(timezone)
                user_time_activity[message.author.id].append(localized_time)
            elif analysis_type.value == "word_count":
                if search_term.lower() in message.content.lower():
                    user_word_count[message.author.display_name] += 1

        if messages_deque:
            for message in messages_deque:
                if self.is_canceled:
                    self.is_canceled = False
                    return
                if message_count >= limit:
                    break

                message = SimpleNamespace(**message)
                message.author = SimpleNamespace(**message.author)

                await analyze_message(message)
        else:
            async for message in interaction.channel.history(limit=adjusted_limit):
                if self.is_canceled:
                    self.is_canceled = False
                    return

                await analyze_message(message)

        end = datetime.now()
        formatted_loop_time = f"{(end - start).seconds // 60}:{(end - start).seconds % 60:02}.{(end - start).microseconds // 1000:03}"
        fomatted_buckup_time = (
            datetime.strptime(backup_timestamp, "%Y%m%d-%H%M%S").strftime(
                "%d.%m.%Y at %H:%M"
            )
            if backup_timestamp
            else "N/A"
        )

        backup_info = (
            f"Backup data used from {fomatted_buckup_time} with {new_messages_fetched} new messages fetched.\n"
            if messages_deque
            else ""
        )
        total_analyzed_info = f"**{message_count} messages analyzed in {formatted_loop_time}.**\n{backup_info}"

        if analysis_type.value == "message_count":
            await self.handle_message_count(
                progress_message,
                user,
                user_message_count,
                message_count,
                total_analyzed_info,
            )
        elif analysis_type.value == "time_activity":
            await self.handle_time_activity(
                interaction,
                progress_message,
                user,
                user_time_activity,
                total_analyzed_info,
            )
        elif analysis_type.value == "activity_chart":
            await self.handle_activity_chart(
                interaction,
                progress_message,
                user,
                user_time_activity,
                total_analyzed_info,
            )
        elif analysis_type.value == "word_count":
            await self.handle_word_count(
                progress_message,
                user,
                user_word_count,
                total_analyzed_info,
                search_term,
            )
        else:
            await progress_message.edit(
                content="Unsupported analysis type.",
                view=None,
            )

    async def handle_word_count(
        self,
        progress_message,
        user,
        user_word_count,
        total_analyzed_info,
        search_term,
    ):
        total_word_uses = sum(user_word_count.values())

        sorted_user_word_count = sorted(
            user_word_count.items(), key=lambda x: x[1], reverse=True
        )
        output_lines = []
        display_name = user.display_name if user else ""
        for display_name, count in sorted_user_word_count:
            percentage = (count / total_word_uses * 100) if total_word_uses > 0 else 0
            output_lines.append(
                f"**{display_name}** used '{search_term}' {count} times ({percentage:.2f}%)"
            )
        output = "\n".join(output_lines) or f"No users found using '{search_term}'"
        user_name = f"by {display_name} " if user else ""
        heading = f"Word Count for '{search_term}' {user_name}({total_word_uses} uses):"

        embed = discord.Embed(
            title="Word Count",
            description=total_analyzed_info,
            color=0x7289DA,
        )
        embed.add_field(name=heading, value=output, inline=False)
        await progress_message.edit(
            content=None,
            embed=embed,
            view=None,
        )

    async def handle_activity_chart(
        self,
        interaction,
        progress_message,
        user,
        user_time_activity,
        total_analyzed_info,
    ):
        if user:
            member = interaction.guild.get_member(user.id)
            display_name = member.display_name if member else user.name
        else:
            display_name = "All Users"

        times = [t for times_list in user_time_activity.values() for t in times_list]
        if not times:
            await progress_message.edit(
                content="No messages found.",
                view=None,
            )
            return

        # Generate activity chart
        output, chart = self.generate_activity_chart(
            times, display_name, total_analyzed_info
        )
        embed = discord.Embed(
            title="Activity Chart Analysis",
            description=output,
            color=0x7289DA,
        )
        file = discord.File(chart, filename="activity_chart.png") if chart else None
        if chart:
            embed.set_image(url="attachment://activity_chart.png")
        await progress_message.edit(
            content=None,
            embed=embed,
            attachments=[file] if file else [],
            view=None,
        )

    def generate_activity_chart(self, timestamps, display_name, total_analyzed_info):
        try:
            # Sort timestamps by date
            timestamps.sort()
            dates = [t.date() for t in timestamps]
            date_counts = Counter(dates)

            # Ensure all days in the range are present, filling in gaps with 0
            start_date = min(dates)
            end_date = max(dates)
            all_dates = [
                start_date + timedelta(days=x)
                for x in range((end_date - start_date).days + 1)
            ]
            counts = [date_counts.get(date, 0) for date in all_dates]

            # Apply a simple moving average to smooth the curve
            window_size = 5
            if len(counts) >= window_size:
                smoothed_counts = np.convolve(
                    counts, np.ones(window_size) / window_size, mode="same"
                )
            else:
                smoothed_counts = counts

            # Plot the activity chart
            plt.figure(figsize=(12, 6))
            plt.plot(all_dates, smoothed_counts, linestyle="-", color="b")
            plt.xlabel("Date")
            plt.ylabel("Number of Messages")
            plt.title(
                f"Activity Chart for {display_name} (Smoothed with Moving Average)"
            )
            plt.xticks(rotation=45)
            plt.grid(True, linestyle="--", linewidth=0.5)
            plt.tight_layout()

            # Save to BytesIO object
            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            plt.close()
            buf.seek(0)
            return total_analyzed_info, buf
        except Exception as e:
            return "Error generating activity chart analysis.", str(e)

    async def handle_message_count(
        self,
        progress_message,
        user,
        user_message_count,
        message_count,
        total_analyzed_info,
    ):
        sorted_user_message_count = sorted(
            user_message_count.items(), key=lambda x: x[1], reverse=True
        )
        output_lines = []
        display_name = user.display_name if user else ""

        for display_name, count in sorted_user_message_count:
            percentage = (count / message_count * 100) if message_count > 0 else 0
            output_lines.append(
                f"**{display_name}**: {count} messages ({percentage:.2f}%)"
            )

        output = "\n".join(output_lines) or "No messages found"
        output = output[:1019] + "..." if len(output) > 1024 else output
        if user:
            heading = f"Message Count for {display_name}"
        else:
            heading = "Top Contributors"

        embed = discord.Embed(
            title="Message Count",
            description=total_analyzed_info,
            color=0x7289DA,
        )
        embed.add_field(name=heading, value=output, inline=False)
        await progress_message.edit(
            content=None,
            embed=embed,
            view=None,
        )

    async def handle_time_activity(
        self,
        interaction,
        progress_message,
        user,
        user_time_activity,
        total_analyzed_info,
    ):
        if user:
            member = interaction.guild.get_member(user.id)
            display_name = member.display_name if member else user.name
        else:
            display_name = "All Users"

        times = [t for times_list in user_time_activity.values() for t in times_list]
        if not times:
            await progress_message.edit(
                content="No messages found.",
                view=None,
            )
            return

        output, heatmap = self.generate_activity_output(
            times, display_name, total_analyzed_info
        )
        embed = discord.Embed(
            title="Activity Time Analysis",
            description=output,
            color=0x7289DA,
        )
        file = discord.File(heatmap, filename="heatmap.png") if heatmap else None
        if heatmap:
            embed.set_image(url="attachment://heatmap.png")
        await progress_message.edit(
            content=None,
            embed=embed,
            attachments=[file] if file else [],
            view=None,
        )

    def generate_activity_output(self, times, display_name, total_analyzed_info):
        try:
            hour_counts = Counter(t.hour for t in times)
            day_counts = Counter(t.strftime("%A") for t in times)
            month_counts = Counter(t.strftime("%B") for t in times)
            year_counts = Counter(t.year for t in times)
            total_messages = len(times)
            most_common_hour, hour_count = hour_counts.most_common(1)[0]
            most_common_day, day_count = day_counts.most_common(1)[0]
            most_common_month, month_count = month_counts.most_common(1)[0]
            most_common_year, year_count = year_counts.most_common(1)[0]
            hour_percentage = hour_count / total_messages * 100
            day_percentage = day_count / total_messages * 100
            month_percentage = month_count / total_messages * 100
            year_percentage = year_count / total_messages * 100

            possessive_name = (
                f"**{display_name}'s**"
                if display_name != "All Users"
                else "**All Users'**"
            )

            output = (
                f"{total_analyzed_info}"
                f"{possessive_name} most active hour: **{most_common_hour}:00** "
                f"with {hour_count} messages ({hour_percentage:.2f}%).\n"
                f"Most active day: **{most_common_day}** "
                f"with {day_count} messages ({day_percentage:.2f}%).\n"
                f"Most active month: **{most_common_month}** "
                f"with {month_count} messages ({month_percentage:.2f}%).\n"
                f"Most active year: **{most_common_year}** "
                f"with {year_count} messages ({year_percentage:.2f}%)."
            )

            heatmap = self.generate_heatmap(times, display_name)
            return output, heatmap
        except Exception as e:
            return "Error generating activity analysis.", str(e)

    def generate_heatmap(self, timestamps, title):
        try:
            import numpy as np

            heatmap_data = np.zeros((7, 24), dtype=int)  # 7 days, 24 hours

            for t in timestamps:
                day_of_week = t.weekday()  # Monday=0, Sunday=6
                hour = t.hour
                heatmap_data[day_of_week][hour] += 1

            plt.figure(figsize=(12, 6))
            plt.imshow(heatmap_data, aspect="auto", cmap="YlOrRd", origin="lower")
            plt.colorbar(label="Message Count")
            plt.title(f"Activity Heatmap for {title}")
            plt.ylabel("Day of Week")
            plt.xlabel("Hour of Day")
            plt.yticks(
                range(7),
                [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ],
            )
            plt.xticks(range(24), range(24))
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            plt.close()
            buf.seek(0)
            return buf
        except Exception as e:
            return "Error generating heatmap.", str(e)


# Add cog to the bot
async def setup(bot):
    await bot.add_cog(MessageAnalyzer(bot))
