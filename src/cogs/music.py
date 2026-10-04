import asyncio
import os
import shutil
import subprocess
import time
import traceback
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp as youtube_dl
from collections import defaultdict

from utils.ffmpeg import get_ffmpeg_executable
from utils.opus import ensure_opus
from utils.audio_analyzer import AudioSpectrumAnalyzer

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda *args, **kwargs: ''

downloads_dir = os.path.abspath('downloads')
os.makedirs(downloads_dir, exist_ok=True)

ffmpeg_bin = get_ffmpeg_executable()

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': os.path.join(downloads_dir, '%(extractor)s-%(id)s.%(ext)s'),
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch',  # Search SoundCloud by default when no URL given
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios'],
            'player_skip': ['webpage', 'configs'],
        }
    },
}

if ffmpeg_bin:
    ytdl_format_options['ffmpeg_location'] = ffmpeg_bin

cookies_path = os.getenv('YTDL_COOKIES_FILE', 'cookies.txt')
if os.path.exists(cookies_path):
    ytdl_format_options['cookiefile'] = cookies_path

ffmpeg_options = {
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, file_path, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.file_path = file_path
        self.title = data.get('title')
        self.url = data.get('url')
        self.analyzer = AudioSpectrumAnalyzer(num_bands=36, fft_size=512)
        self.latest_bands = [0.0] * 36

    def read(self) -> bytes:
        data = super().read()
        if data:
            try:
                self.latest_bands = self.analyzer.analyze(data)
            except Exception:
                pass
        else:
            self.latest_bands = [0.0] * 36
        return data

    @property
    def _current_error(self):
        """Forward underlying FFmpeg error so AudioPlayer can report it to after callback."""
        return getattr(self.original, '_current_error', None)

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        # Always download via Python's native network stack to avoid DNS issues in static FFmpeg
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=True))

        if 'entries' in data:
            valid_entries = [e for e in data['entries'] if e]
            if not valid_entries:
                raise RuntimeError("No valid entries found for this track/playlist.")
            data = valid_entries[0]

        # Locate actual downloaded file
        file_path = None
        if 'requested_downloads' in data and len(data['requested_downloads']) > 0:
            file_path = data['requested_downloads'][0].get('filepath')
        if not file_path or not os.path.exists(file_path):
            file_path = ytdl.prepare_filename(data)

        # Fallback check inside downloads directory by ID
        if not os.path.exists(file_path):
            track_id = str(data.get('id', ''))
            for f in os.listdir(downloads_dir):
                if track_id and track_id in f:
                    file_path = os.path.join(downloads_dir, f)
                    break

        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Downloaded audio file not found on disk at {file_path}")

        ffmpeg_executable = get_ffmpeg_executable()
        if not ffmpeg_executable:
            raise RuntimeError("No working FFmpeg executable found on this system.")

        # Pre-flight check: verify that FFmpeg can decode this audio file
        test_cmd = [ffmpeg_executable, '-i', file_path, '-t', '0.5', '-f', 'null', '-']
        test_proc = subprocess.run(test_cmd, capture_output=True, text=True)
        if test_proc.returncode != 0:
            print(f"[FFmpeg Decode Error] returncode={test_proc.returncode}")
            print(f"[FFmpeg Stderr]: {test_proc.stderr}")
            raise RuntimeError(f"FFmpeg failed to decode audio (code {test_proc.returncode}): {test_proc.stderr.strip()[:200]}")

        return cls(discord.FFmpegPCMAudio(file_path, executable=ffmpeg_executable, **ffmpeg_options), data=data, file_path=file_path)

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
        # Currently active track details per guild
        self.current_tracks = {}

    async def extract_track_info(self, query: str):
        """Extracts metadata and direct streamable info for a track or query."""
        if query.startswith(('http://', 'https://', 'scsearch:', 'ytsearch:')):
            target = query
        else:
            target = f"scsearch5:{query}"

        search_opts = dict(ytdl_format_options)
        search_opts['ignoreerrors'] = True
        search_ytdl = youtube_dl.YoutubeDL(search_opts)

        loop = self.bot.loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: search_ytdl.extract_info(target, download=False))

        if not data:
            return None

        if 'entries' in data:
            valid_entries = [e for e in data['entries'] if e]
            if not valid_entries:
                return None
            data = valid_entries[0]

        thumbnail = data.get('thumbnail')
        if not thumbnail and data.get('thumbnails'):
            thumbnail = data['thumbnails'][-1].get('url')

        return {
            'title': data.get('title') or query,
            'url': data.get('webpage_url') or data.get('url') or target,
            'webpage_url': data.get('webpage_url') or data.get('url') or target,
            'thumbnail': thumbnail or '/static/images/vinyl.png',
            'duration': data.get('duration') or 0,
            'artist': data.get('uploader') or data.get('channel') or data.get('creator') or 'SoundCloud',
        }

    def play_next(self, guild, voice_client):
        if len(self.queues[guild.id]) > 0:
            track = self.queues[guild.id].pop(0)
            asyncio.run_coroutine_threadsafe(self._play_track(guild, voice_client, track), self.bot.loop)
        else:
            self.play_loops.pop(guild.id, None)

    async def _play_track(self, guild, voice_client, track):
        try:
            ensure_opus()
            player = await YTDLSource.from_url(track['url'], loop=self.bot.loop)
            self.current_tracks[guild.id] = {
                'title': track.get('title') or player.title or 'Unknown Track',
                'url': track.get('url', ''),
                'webpage_url': track.get('webpage_url') or track.get('url', ''),
                'thumbnail': track.get('thumbnail') or '/static/images/vinyl.png',
                'duration': track.get('duration', 0),
                'artist': track.get('artist', 'SoundCloud'),
                'start_time': time.time(),
                'player': player,
            }
            voice_client.play(player, after=lambda e: self._on_playback_end(guild, voice_client, e, player.file_path))
        except Exception as e:
            self.current_tracks.pop(guild.id, None)
            print(f"Error playing track ({type(e).__name__}): {e}")
            traceback.print_exc()
            self.play_next(guild, voice_client)

    def _on_playback_end(self, guild, voice_client, error, file_path=None):
        self.current_tracks.pop(guild.id, None)
        if error:
            print(f'Player error ({type(error).__name__}): {error}')

        # Clean up downloaded local file to save container disk space
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        # Increment total streams completed
        if hasattr(self.bot, 'total_streams_completed'):
            self.bot.total_streams_completed += 1

        self.play_next(guild, voice_client)

    def get_guild_state(self, guild_id: int):
        """Returns the complete playback and queue state for a guild."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None

        voice_client = guild.voice_client
        connected = voice_client is not None and voice_client.is_connected()
        channel_name = voice_client.channel.name if (connected and voice_client.channel) else None
        listeners = [m.display_name for m in (voice_client.channel.members if (connected and voice_client.channel) else []) if not m.bot]

        curr = self.current_tracks.get(guild_id)
        curr_dict = None
        is_playing = voice_client.is_playing() if connected else False
        is_paused = voice_client.is_paused() if connected else False
        curr_volume = 100

        if curr and connected:
            player = curr.get('player')
            curr_volume = int(round((player.volume if player else 0.5) * 100))
            elapsed = int(round(time.time() - curr.get('start_time', time.time()))) if (is_playing and not is_paused) else 0
            bands = player.latest_bands if (player and hasattr(player, 'latest_bands')) else ([0.0] * 36)

            curr_dict = {
                'title': curr['title'],
                'url': curr['url'],
                'webpage_url': curr.get('webpage_url', ''),
                'thumbnail': curr.get('thumbnail') or '/static/images/vinyl.png',
                'duration': curr.get('duration', 0),
                'artist': curr.get('artist', 'SoundCloud'),
                'uploader': curr.get('artist', 'SoundCloud'),
                'requester': curr.get('requester', 'Discord User'),
                'is_url': curr.get('is_url', False),
                'elapsed': elapsed,
                'is_playing': is_playing,
                'is_paused': is_paused,
                'volume': curr_volume,
                'visualizer_bands': bands,
            }
        else:
            bands = [0.0] * 36

        queue_list = []
        for i, t in enumerate(self.queues.get(guild_id, [])):
            queue_list.append({
                'index': i,
                'title': t.get('title', 'Unknown Track'),
                'url': t.get('url', ''),
                'webpage_url': t.get('webpage_url', ''),
                'thumbnail': t.get('thumbnail') or '/static/images/vinyl.png',
                'duration': t.get('duration', 0),
                'artist': t.get('artist', 'SoundCloud'),
                'uploader': t.get('artist', 'SoundCloud'),
                'requester': t.get('requester', 'Discord User'),
            })

        return {
            'guild_id': str(guild.id),
            'id': str(guild.id),
            'guild_name': guild.name,
            'name': guild.name,
            'guild_icon': str(guild.icon.url) if guild.icon else None,
            'connected': connected,
            'is_playing': is_playing,
            'is_paused': is_paused,
            'voice_channel': {'name': channel_name} if channel_name else None,
            'volume': curr_volume,
            'listeners': listeners,
            'current_track': curr_dict,
            'queue': queue_list,
            'visualizer_bands': bands,
        }

    def get_all_guilds_state(self):
        """Returns summarized status for all guilds."""
        results = []
        for guild in self.bot.guilds:
            state = self.get_guild_state(guild.id)
            if state:
                results.append(state)
        return results

    async def play_from_web(self, guild_id: int, query: str):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise ValueError(f"Guild {guild_id} not found.")

        track_info = await self.extract_track_info(query)
        if not track_info:
            raise ValueError("No playable tracks found.")

        voice_client = guild.voice_client
        if not voice_client:
            # Look for an active voice channel in this guild
            for ch in guild.voice_channels:
                if len(ch.members) > 0:
                    voice_client = await ch.connect()
                    break
            if not voice_client and guild.voice_channels:
                voice_client = await guild.voice_channels[0].connect()

        if not voice_client:
            raise ValueError("Bot is not connected to a voice channel in this server.")

        self.queues[guild.id].append(track_info)

        if not voice_client.is_playing() and guild.id not in self.play_loops:
            self.play_loops[guild.id] = True
            self.play_next(guild, voice_client)

        return track_info

    def pause_from_web(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return False, "Not connected to voice."
        vc = guild.voice_client
        if vc.is_playing():
            vc.pause()
            return True, "Paused"
        elif vc.is_paused():
            vc.resume()
            return True, "Resumed"
        return False, "Not playing or paused."

    def skip_from_web(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return False, "Not connected to voice."
        vc = guild.voice_client
        if vc.is_playing() or vc.is_paused():
            vc.stop()
            return True, "Skipped current track."
        return False, "No track is playing."

    async def stop_from_web(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False, "Guild not found."
        self.queues[guild.id].clear()
        self.play_loops.pop(guild.id, None)
        self.current_tracks.pop(guild.id, None)
        vc = guild.voice_client
        if vc:
            if vc.is_playing() or vc.is_paused():
                vc.stop()
            try:
                await vc.disconnect(force=True)
            except Exception as e:
                print(f"[Music] Error disconnecting from voice: {e}")
            return True, "Stopped playback and disconnected from voice channel."
        return True, "Stopped playback and cleared queue."

    def set_volume_from_web(self, guild_id: int, volume_pct: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False, "Guild not found."
        curr = self.current_tracks.get(guild.id)
        if curr and curr.get('player'):
            vol = max(0.0, min(1.0, volume_pct / 100.0))
            curr['player'].volume = vol
            return True, f"Volume set to {int(round(vol * 100))}%"
        return False, "No active track to adjust volume."

    def remove_track_from_web(self, guild_id: int, index: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False, "Guild not found."
        q = self.queues.get(guild.id, [])
        if 0 <= index < len(q):
            removed = q.pop(index)
            return True, f"Removed {removed['title']}"
        return False, "Invalid track index."


    @app_commands.command(name="play", description="Plays a song from SoundCloud or a direct URL.")
    @app_commands.describe(query="The song to play (URL or SoundCloud search keywords)")
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
            # If not a direct URL, search SoundCloud with top 5 results to skip DRM/preview tracks
            if query.startswith(('http://', 'https://', 'scsearch:', 'ytsearch:')):
                target = query
            else:
                target = f"scsearch5:{query}"

            # Extract metadata with ignoreerrors=True so DRM preview tracks don't crash search
            search_opts = dict(ytdl_format_options)
            search_opts['ignoreerrors'] = True
            search_ytdl = youtube_dl.YoutubeDL(search_opts)

            loop = self.bot.loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: search_ytdl.extract_info(target, download=False))

            if not data:
                await interaction.followup.send("No results found for that search.")
                return

            if 'entries' in data:
                valid_entries = [e for e in data['entries'] if e]
                if not valid_entries:
                    await interaction.followup.send("No playable tracks found for this search.")
                    return
                data = valid_entries[0]

            track_info = {
                'title': data.get('title') or query,
                'url': data.get('webpage_url') or data.get('url') or target
            }

            self.queues[interaction.guild.id].append(track_info)
            await interaction.followup.send(f"Added to queue: **{track_info['title']}**")

            # Start playing if nothing is currently playing
            if not voice_client.is_playing() and interaction.guild.id not in self.play_loops:
                self.play_loops[interaction.guild.id] = True
                self.play_next(interaction.guild, voice_client)

        except Exception as e:
            traceback.print_exc()
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

            # Clean up downloads directory
            if os.path.exists(downloads_dir):
                for f in os.listdir(downloads_dir):
                    p = os.path.join(downloads_dir, f)
                    try:
                        if os.path.isfile(p):
                            os.remove(p)
                    except Exception:
                        pass

            await interaction.response.send_message("Stopped the music, cleared the queue, and disconnected.")
        else:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Music(bot))

