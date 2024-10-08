import discord
import os
import asyncio
from discord.ext import tasks
from mcrcon import MCRcon
from dotenv import load_dotenv

# Lade den Inhalt der .env-Datei
load_dotenv()

# Zugriff auf die Umgebungsvariablen
TOKEN = os.getenv("DISCORD_TOKEN")
RCON_IP = os.getenv("RCON_IP")
RCON_PASSWORD = os.getenv("RCON_PASSWORD")
RCON_PORT = int(os.getenv("RCON_PORT"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH")

# Discord bot setup mit Intents
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# Funktion um die Logdatei zu überwachen und neue Einträge zu versenden
async def tail_logfile(file):
    file.seek(0, os.SEEK_END)
    while True:
        line = file.readline()
        if not line:
            await asyncio.sleep(1)
            continue
        yield line


# Überwache die Minecraft-Konsole und leite alle neuen Einträge an Discord weiter
@tasks.loop(seconds=1)
async def watch_log():
    try:
        with open(LOG_FILE_PATH, "r") as file:
            log_lines = tail_logfile(file)
            channel = client.get_channel(CHANNEL_ID)

            async for line in log_lines:
                await channel.send(line.strip())
    except Exception as e:
        print(f"Error watching log file: {e}")


# Fange Discord-Nachrichten ab und sende sie als RCON-Befehle
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.channel.id == CHANNEL_ID:
        try:
            with MCRcon(RCON_IP, RCON_PASSWORD, port=RCON_PORT) as mcr:
                command = message.content
                response = mcr.command(command)
                await message.channel.send(f"Command Response: {response}")
        except Exception as e:
            print(f"Error sending command to RCON: {e}")
            await message.channel.send(f"Error: {e}")


@client.event
async def on_ready():
    print(f"Bot ist eingeloggt als {client.user}")
    watch_log.start()


client.run(TOKEN)
