import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands import Choice
import matplotlib.pyplot as plt
import io
import pytz
import config
from collections import defaultdict, Counter
import datetime
import numpy as np


class MessageAnalyzer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="analyze", description="Analyzes messages in the channel"
    )
    @app_commands.describe(
        analysis_type="Type of analysis to perform",
        limit="Maximum number of messages to analyze",
        user="User to analyze (default: all users)",
        search_term="The term to search for (required if Word Count is selected)",
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
    ):
        if analysis_type.value == "word_count" and search_term is None:
            await interaction.response.send_message(
                "You must provide a search term for word count analysis.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        limit = limit or 1000000
        adjusted_limit = limit + 1  # Adjust for potential inclusion of progress message

        progress_message = await interaction.followup.send(
            "Analyzing messages... This may take a while."
        )

        user_message_count = defaultdict(int)
        user_word_count = defaultdict(int)
        user_time_activity = defaultdict(list)
        word_counter = Counter()
        users_to_analyze = [user.id] if user else None

        timezone = pytz.timezone(config.TIMEZONE)

        message_count = 0
        progress_interval = 100  # Update progress every 100 messages

        async for message in interaction.channel.history(limit=adjusted_limit):
            if message.id == progress_message.id:
                continue

            message_count += 1
            if message_count % progress_interval == 0:
                await progress_message.edit(
                    content=f"Analyzing messages... {message_count} messages processed."
                )

            if users_to_analyze and message.author.id not in users_to_analyze:
                continue

            if analysis_type.value == "message_count":
                user_message_count[message.author.id] += 1
            elif analysis_type.value in ["time_activity", "activity_chart"]:
                localized_time = message.created_at.astimezone(timezone)
                user_time_activity[message.author.id].append(localized_time)
            elif analysis_type.value == "word_count":
                if search_term.lower() in message.content.lower():
                    user_word_count[message.author.id] += 1

        total_analyzed_info = f"**{message_count} messages analyzed.**\n"

        if analysis_type.value == "message_count":
            await self.handle_message_count(
                interaction,
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
                interaction,
                progress_message,
                user,
                user_word_count,
                total_analyzed_info,
                search_term,
            )
        else:
            await progress_message.edit(content="Unsupported analysis type.")

    async def handle_word_count(
        self,
        interaction,
        progress_message,
        user,
        user_word_count,
        total_analyzed_info,
        search_term,
    ):
        total_word_uses = sum(user_word_count.values())

        if user:
            count = user_word_count.get(user.id, 0)
            percentage = (count / total_word_uses * 100) if total_word_uses > 0 else 0
            member = interaction.guild.get_member(user.id)
            display_name = member.display_name if member else user.name
            output = f"**{display_name}** used '{search_term}' {count} times ({percentage:.2f}%)"
            heading = f"Word Count for {display_name}"
        else:
            sorted_user_word_count = sorted(
                user_word_count.items(), key=lambda x: x[1], reverse=True
            )
            output_lines = []
            for user_id, count in sorted_user_word_count:
                member = interaction.guild.get_member(user_id)
                if member:
                    display_name = member.display_name
                else:
                    try:
                        user_obj = await self.bot.fetch_user(user_id)
                        display_name = user_obj.name
                    except:
                        display_name = f"User ID {user_id}"
                percentage = (
                    (count / total_word_uses * 100) if total_word_uses > 0 else 0
                )
                output_lines.append(
                    f"**{display_name}** used '{search_term}' {count} times ({percentage:.2f}%)"
                )
            output = "\n".join(output_lines) or f"No users found using '{search_term}'"
            heading = f"Word Count for '{search_term}' ({total_word_uses} uses):"

        embed = discord.Embed(
            title="Word Count",
            description=total_analyzed_info,
            color=0x7289DA,
        )
        embed.add_field(name=heading, value=output, inline=False)
        await progress_message.edit(content=None, embed=embed)

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
            times = user_time_activity.get(user.id, [])
            if not times:
                await progress_message.edit(
                    content=f"No messages from {display_name} found."
                )
                return
        else:
            times = [
                t for times_list in user_time_activity.values() for t in times_list
            ]
            display_name = "All Users"
            if not times:
                await progress_message.edit(content="No messages found.")
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
        if chart:
            file = discord.File(chart, filename="activity_chart.png")
            embed.set_image(url="attachment://activity_chart.png")
            await progress_message.edit(content=None, embed=embed, attachments=[file])
        else:
            await progress_message.edit(content=None, embed=embed)

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
                start_date + datetime.timedelta(days=x)
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
            print(f"Error generating activity chart: {e}")
            return "Error generating activity chart analysis.", None

    async def handle_message_count(
        self,
        interaction,
        progress_message,
        user,
        user_message_count,
        message_count,
        total_analyzed_info,
    ):
        if user:
            count = user_message_count.get(user.id, 0)
            percentage = (count / message_count * 100) if message_count > 0 else 0
            member = interaction.guild.get_member(user.id)
            display_name = member.display_name if member else user.name
            output = f"**{display_name}**: {count} messages ({percentage:.2f}%)"
            heading = f"Message Count for {display_name}"
        else:
            sorted_user_message_count = sorted(
                user_message_count.items(), key=lambda x: x[1], reverse=True
            )
            output_lines = []
            for user_id, count in sorted_user_message_count:
                member = interaction.guild.get_member(user_id)
                if member:
                    display_name = member.display_name
                else:
                    try:
                        user_obj = await self.bot.fetch_user(user_id)
                        display_name = user_obj.name
                    except:
                        display_name = f"User ID {user_id}"
                percentage = (count / message_count * 100) if message_count > 0 else 0
                output_lines.append(
                    f"**{display_name}**: {count} messages ({percentage:.2f}%)"
                )
            output = "\n".join(output_lines) or "No messages found"
            heading = "Top Contributors"

        embed = discord.Embed(
            title="Message Count",
            description=total_analyzed_info,
            color=0x7289DA,
        )
        embed.add_field(name=heading, value=output, inline=False)
        await progress_message.edit(content=None, embed=embed)

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
            times = user_time_activity.get(user.id, [])
            if not times:
                await progress_message.edit(
                    content=f"No messages from {display_name} found."
                )
                return
        else:
            times = [
                t for times_list in user_time_activity.values() for t in times_list
            ]
            display_name = "All Users"
            if not times:
                await progress_message.edit(content="No messages found.")
                return

        output, heatmap = self.generate_activity_output(
            times, display_name, total_analyzed_info
        )
        embed = discord.Embed(
            title="Activity Time Analysis",
            description=output,
            color=0x7289DA,
        )
        if heatmap:
            file = discord.File(heatmap, filename="heatmap.png")
            embed.set_image(url="attachment://heatmap.png")
            await progress_message.edit(content=None, embed=embed, attachments=[file])
        else:
            await progress_message.edit(content=None, embed=embed)

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
            print(f"Error generating activity output: {e}")
            return "Error generating activity analysis.", None

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
            print(f"Error generating heatmap: {e}")
            return None


# Add cog to the bot
async def setup(bot):
    await bot.add_cog(MessageAnalyzer(bot))
