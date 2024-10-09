import os
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Secrets from the .env file
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
RCON_IP = os.getenv("RCON_IP")
RCON_PASSWORD = os.getenv("RCON_PASSWORD")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH")

# Constants
RCON_PORT = 25575
CHANNEL_ID = 1292595944344256553
RCON_IP = "localhost"
