import asyncio

import discord
import yt_dlp as youtube_dl
from discord import app_commands
from discord.ext import commands


ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        #if player does not work it may need the path to the ffmpeg.exe
        #return cls(discord.FFmpegPCMAudio(executable="path/to/ffmpeg/bin/ffmpeg", source=filename, **ffmpeg_options), data=data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="play", description="Plays a song from a URL")
    async def play_song(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True)

        if not interaction.user.voice:
            await interaction.followup.send("You are not in a voice channel!")
            return

        #TODO change for continues usage
        voice_client = await interaction.user.voice.channel.connect()

        player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
        await interaction.followup.send(f"Playing {player.title}")

    @app_commands.command(name="stop", description="Stops the current song")
    async def stop_song(self, interaction: discord.Interaction):
        await interaction.response.send_message("Stopping song...")


# Setup function to add the Cog to the bot
async def setup(bot):
    await bot.add_cog(Music(bot))
