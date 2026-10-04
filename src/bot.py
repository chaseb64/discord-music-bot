import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.opus import ensure_opus

# Load environment variables
load_dotenv()

# Setup bot intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read commands/messages if needed
intents.voice_states = True

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        # Global variable for stats tracking
        self.total_streams_completed = 0

    async def setup_hook(self):
        # Load cogs
        for filename in os.listdir('./src/cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')

        # Sync slash commands globally
        await self.tree.sync()
        print("Slash commands synced globally.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token or token == "your_discord_bot_token_here":
        print("Please set your DISCORD_TOKEN in the .env file.")
        return

    # Ensure libopus is loaded for Discord voice support
    if not ensure_opus():
        print("[Opus] Warning: Opus shared library could not be loaded. Voice playback may fail.")

    bot = MusicBot()
    bot.run(token)

if __name__ == '__main__':
    main()

