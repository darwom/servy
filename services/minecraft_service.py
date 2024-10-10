import asyncio
import os
from mcrcon import MCRcon
import config


# Function to tail the log file
async def tail_logfile(file_path):
    with open(file_path, "r") as file:
        file.seek(0, os.SEEK_END)
        while True:
            line = file.readline()
            if not line:
                await asyncio.sleep(1)
                continue
            yield line


# Function to send a command to the Minecraft server via RCON
def send_rcon_command(command):
    try:
        with MCRcon(config.RCON_IP, config.RCON_PASSWORD, port=config.RCON_PORT) as mcr:
            response = mcr.command(command)
            return response
    except Exception as e:
        print(f"Error sending command to RCON: {e}")
        raise e
