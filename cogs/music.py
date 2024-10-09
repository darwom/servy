import os
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands


# Placeholder for the Music Cog. Does not play music yet

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.database_path = os.path.join(os.path.dirname(__file__), '_audio_Processor/history.db')

        # Ensure the audio processor directory exists
        if not os.path.exists(os.path.dirname(self.database_path)):
            os.makedirs(os.path.dirname(self.database_path))

        self.setup_database()

    def setup_database(self):
        """Set up the initial database and table."""
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                user_id INTEGER,
                url TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def add_song_to_history(self, user_id: int, url: str):
        """Add a played song to the user's history."""
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO history (user_id, url) VALUES (?, ?)', (user_id, url))
        conn.commit()
        conn.close()

    def get_user_history(self, user_id: int):
        """Retrieve play history for a user."""
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        cursor.execute('SELECT url, timestamp FROM history WHERE user_id = ?', (user_id,))
        history = cursor.fetchall()
        conn.close()
        return history

    # Slash Command: /play
    @app_commands.command(name="play", description="Plays a song from a URL")
    async def play_song(self, interaction: discord.Interaction, url: str):
        user_id = interaction.user.id  # Get the user's ID
        self.add_song_to_history(user_id, url)  # Add song to history
        await interaction.response.send_message(f"Playing song from {url}")

    # Slash Command: /stop
    @app_commands.command(name="stop", description="Stops the current song")
    async def stop_song(self, interaction: discord.Interaction):
        await interaction.response.send_message("Stopping song...")


# Setup function to add the Cog to the bot
async def setup(bot):
    await bot.add_cog(Music(bot))
