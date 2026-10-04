import asyncio
import os
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp as youtube_dl
from collections import defaultdict

# Automatically register portable static ffmpeg binary paths if installed
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda *args, **kwargs: ''

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
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios'],
            'player_skip': ['webpage', 'configs'],
        }
    },
}

cookies_path = os.getenv('YTDL_COOKIES_FILE', 'cookies.txt')
if os.path.exists(cookies_path):
    ytdl_format_options['cookiefile'] = cookies_path

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k',
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
        ffmpeg_executable = os.getenv('FFMPEG_PATH', 'ffmpeg')
        return cls(discord.FFmpegPCMAudio(filename, executable=ffmpeg_executable, **ffmpeg_options), data=data)

class QueuePaginationView(discord.ui.View):
    def __init__(self, queue, page=1):
        super().__init__()
        self.queue = queue
        self.page = page
        self.per_page = 10
        self.total_pages = max(1, (len(queue) + self.per_page - 1) // self.per_page)

        # Disable buttons if needed
        if self.page == 1:
            self.children[0].disabled = True
        if self.page == self.total_pages:
            self.children[1].disabled = True

    def get_embed(self):
        start = (self.page - 1) * self.per_page
        end = start + self.per_page
        items = self.queue[start:end]

        description = ""
        for i, track in enumerate(items, start=start + 1):
            description += f"**{i}.** {track['title']}\n"

        embed = discord.Embed(
            title="Music Queue",
            description=description,
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Page {self.page} / {self.total_pages} | Total tracks: {len(self.queue)}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 1:
            self.page -= 1
            await self.update_view(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages:
            self.page += 1
            await self.update_view(interaction)

    async def update_view(self, interaction: discord.Interaction):
        # Update button states
        self.children[0].disabled = (self.page == 1)
        self.children[1].disabled = (self.page == self.total_pages)

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Dictionary mapping guild_id -> list of track dictionaries
        self.queues = defaultdict(list)
        # Prevent starting multiple playback loops per guild
        self.play_loops = {}

    def play_next(self, guild, voice_client):
        if len(self.queues[guild.id]) > 0:
            track = self.queues[guild.id].pop(0)

            # Recreate YTDLSource for the track
            # This avoids issues if the stream URL expires while waiting in queue
            asyncio.run_coroutine_threadsafe(self._play_track(guild, voice_client, track['url']), self.bot.loop)
        else:
            self.play_loops.pop(guild.id, None)

    async def _play_track(self, guild, voice_client, url):
        try:
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            voice_client.play(player, after=lambda e: self._on_playback_end(guild, voice_client, e))
        except Exception as e:
            print(f"Error playing track: {e}")
            self.play_next(guild, voice_client)

    def _on_playback_end(self, guild, voice_client, error):
        if error:
            print(f'Player error: {error}')

        # Increment total streams completed
        if hasattr(self.bot, 'total_streams_completed'):
            self.bot.total_streams_completed += 1

        self.play_next(guild, voice_client)

    @app_commands.command(name="play", description="Plays a song from YouTube.")
    @app_commands.describe(query="The song to play (URL or search query)")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            await interaction.response.send_message("You are not connected to a voice channel.", ephemeral=True)
            return

        channel = interaction.user.voice.channel

        await interaction.response.defer()

        # Connect to voice channel if not already connected
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        try:
            # We just extract info first to get title/url to add to queue
            # We don't build the player until it's time to play, to prevent URL expiry
            loop = self.bot.loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))

            if 'entries' in data:
                data = data['entries'][0]

            track_info = {
                'title': data.get('title'),
                'url': data.get('webpage_url') or query
            }

            self.queues[interaction.guild.id].append(track_info)
            await interaction.followup.send(f"Added to queue: **{track_info['title']}**")

            # Start playing if nothing is currently playing
            if not voice_client.is_playing() and interaction.guild.id not in self.play_loops:
                self.play_loops[interaction.guild.id] = True
                self.play_next(interaction.guild, voice_client)

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")

    @app_commands.command(name="queue", description="Shows the current music queue.")
    async def queue(self, interaction: discord.Interaction):
        q = self.queues[interaction.guild.id]
        if not q:
            await interaction.response.send_message("The queue is currently empty.")
            return

        if len(q) <= 10:
            description = ""
            for i, track in enumerate(q, start=1):
                description += f"**{i}.** {track['title']}\n"

            embed = discord.Embed(title="Music Queue", description=description, color=discord.Color.green())
            await interaction.response.send_message(embed=embed)
        else:
            view = QueuePaginationView(q)
            await interaction.response.send_message(embed=view.get_embed(), view=view)

    @app_commands.command(name="skip", description="Skips the currently playing song.")
    async def skip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop() # This triggers the 'after' callback, which calls play_next
            await interaction.response.send_message("Skipped the current song.")
        else:
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)

    @app_commands.command(name="stop", description="Stops the music and clears the queue.")
    async def stop(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client:
            self.queues[interaction.guild.id].clear()
            self.play_loops.pop(interaction.guild.id, None)
            voice_client.stop()
            await voice_client.disconnect()
            await interaction.response.send_message("Stopped the music, cleared the queue, and disconnected.")
        else:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Music(bot))
