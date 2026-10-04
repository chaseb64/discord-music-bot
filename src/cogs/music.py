import asyncio
import os
import random
import re
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
from utils.lyrics import fetch_lyrics

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda *args, **kwargs: ''

downloads_dir = os.path.abspath('downloads')
uploads_dir = os.path.join(downloads_dir, 'uploads')
os.makedirs(downloads_dir, exist_ok=True)
os.makedirs(uploads_dir, exist_ok=True)

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
    'source_address': '0.0.0.0',  # bind to ipv4
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

AUDIO_FILTERS = {
    'none': None,
    'bassboost': 'bass=g=10:f=110:w=0.6',
    'nightcore': 'asetrate=48000*1.25,aresample=48000',
    'vaporwave': 'asetrate=48000*0.82,aresample=48000,aecho=0.8:0.88:60:0.4',
    '8d': 'apulsator=hz=0.125',
    'treble': 'treble=g=8:f=6000:w=0.6',
}

def probe_audio_duration(file_path: str) -> float:
    """Probes the total duration of an audio file in seconds using FFmpeg."""
    try:
        bin_path = get_ffmpeg_executable()
        if not bin_path or not os.path.exists(file_path):
            return 0.0
        cmd = [bin_path, '-i', file_path, '-f', 'null', '-']
        res = subprocess.run(cmd, capture_output=True, text=True)
        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.?\d*)', res.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0.0

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
        return getattr(self.original, '_current_error', None)

    @classmethod
    def create_player(cls, file_path: str, data: dict, volume: float = 0.5, seek: float = 0, filter_name: str = 'none'):
        ffmpeg_executable = get_ffmpeg_executable()
        if not ffmpeg_executable:
            raise RuntimeError("No working FFmpeg executable found on this system.")

        opts = '-vn -b:a 192k'
        filter_str = AUDIO_FILTERS.get(filter_name)
        if filter_str:
            opts += f' -af "{filter_str}"'

        before_opts_list = []
        if seek and seek > 0:
            before_opts_list.append(f'-ss {int(seek)}')

        # Only pass HTTP reconnect options when input is a remote URL stream (NOT local files)
        if file_path.startswith(('http://', 'https://')):
            before_opts_list.append('-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5')

        before_opts = " ".join(before_opts_list) if before_opts_list else None

        source = discord.FFmpegPCMAudio(
            file_path,
            executable=ffmpeg_executable,
            before_options=before_opts,
            options=opts
        )
        return cls(source, data=data, file_path=file_path, volume=volume)

    @classmethod
    async def from_url(cls, url: str, *, loop=None, volume: float = 0.5, seek: float = 0, filter_name: str = 'none'):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=True))

        if 'entries' in data:
            valid_entries = [e for e in data['entries'] if e]
            if not valid_entries:
                raise RuntimeError("No valid entries found for this track/playlist.")
            data = valid_entries[0]

        file_path = None
        if 'requested_downloads' in data and len(data['requested_downloads']) > 0:
            file_path = data['requested_downloads'][0].get('filepath')
        if not file_path or not os.path.exists(file_path):
            file_path = ytdl.prepare_filename(data)

        if not os.path.exists(file_path):
            track_id = str(data.get('id', ''))
            for f in os.listdir(downloads_dir):
                if track_id and track_id in f:
                    file_path = os.path.join(downloads_dir, f)
                    break

        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Downloaded audio file not found on disk at {file_path}")

        return cls.create_player(file_path, data, volume=volume, seek=seek, filter_name=filter_name)

class QueuePaginationView(discord.ui.View):
    def __init__(self, queue, page=1):
        super().__init__()
        self.queue = queue
        self.page = page
        self.per_page = 10
        self.total_pages = max(1, (len(queue) + self.per_page - 1) // self.per_page)

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
        self.children[0].disabled = (self.page == 1)
        self.children[1].disabled = (self.page == self.total_pages)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = defaultdict(list)
        self.play_loops = {}
        self.current_tracks = {}
        # Guild-specific persistent playback settings
        self.guild_settings = defaultdict(lambda: {
            'filter': 'none',
            'loop': 'off',       # 'off', 'track', 'queue'
            'autoplay': False,   # auto-continue playback with related music
        })
        # Internal flag to prevent play_next triggering during mid-stream seek/filter restarts
        self.is_switching = {}

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
            'is_local': False,
        }

    def play_next(self, guild, voice_client):
        if len(self.queues[guild.id]) > 0:
            track = self.queues[guild.id].pop(0)
            asyncio.run_coroutine_threadsafe(self._play_track(guild, voice_client, track), self.bot.loop)
        else:
            self.play_loops.pop(guild.id, None)

    async def _play_track(self, guild, voice_client, track, seek: float = 0):
        try:
            ensure_opus()
            settings = self.guild_settings[guild.id]
            curr_filter = settings.get('filter', 'none')
            curr_vol = track.get('volume', 0.5)

            if track.get('is_local') and track.get('file_path') and os.path.exists(track['file_path']):
                player = YTDLSource.create_player(
                    track['file_path'],
                    track.get('data', {}),
                    volume=curr_vol,
                    seek=seek,
                    filter_name=curr_filter
                )
            else:
                player = await YTDLSource.from_url(
                    track['url'],
                    loop=self.bot.loop,
                    volume=curr_vol,
                    seek=seek,
                    filter_name=curr_filter
                )

            self.current_tracks[guild.id] = {
                'title': track.get('title') or player.title or 'Unknown Track',
                'url': track.get('url', ''),
                'webpage_url': track.get('webpage_url') or track.get('url', ''),
                'thumbnail': track.get('thumbnail') or '/static/images/vinyl.png',
                'duration': track.get('duration', 0) or player.data.get('duration', 0),
                'artist': track.get('artist', 'SoundCloud'),
                'uploader': track.get('uploader', 'SoundCloud'),
                'requester': track.get('requester', 'Discord User'),
                'is_local': track.get('is_local', False),
                'file_path': player.file_path,
                'data': player.data,
                'start_time': time.time() - seek,
                'player': player,
            }

            track_record = dict(self.current_tracks[guild.id])
            voice_client.play(player, after=lambda e: self._on_playback_end(guild, voice_client, e, player.file_path, track_record))
        except Exception as e:
            self.current_tracks.pop(guild.id, None)
            print(f"Error playing track ({type(e).__name__}): {e}")
            traceback.print_exc()
            self.play_next(guild, voice_client)

    def _on_playback_end(self, guild, voice_client, error, file_path=None, track=None):
        if self.is_switching.pop(guild.id, False):
            # Mid-track seek or filter change: keep file and do not advance queue
            return

        self.current_tracks.pop(guild.id, None)
        if error:
            print(f'Player error ({type(error).__name__}): {error}')

        settings = self.guild_settings[guild.id]
        loop_mode = settings.get('loop', 'off')

        # Increment total streams completed
        if hasattr(self.bot, 'total_streams_completed'):
            self.bot.total_streams_completed += 1

        # Looping logic:
        if loop_mode == 'track' and track:
            # Replay same track immediately
            self.queues[guild.id].insert(0, track)
            self.play_next(guild, voice_client)
            return
        elif loop_mode == 'queue' and track:
            # Re-enqueue track to end of queue
            self.queues[guild.id].append(track)

        # Clean up downloaded file if not local upload and loop mode is off
        if file_path and os.path.exists(file_path):
            if loop_mode != 'track' and not (track and track.get('is_local')):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

        # Advance queue or trigger Autoplay
        if len(self.queues[guild.id]) > 0:
            self.play_next(guild, voice_client)
        elif settings.get('autoplay', False) and track:
            asyncio.run_coroutine_threadsafe(self._autoplay_next(guild, voice_client, track), self.bot.loop)
        else:
            self.play_loops.pop(guild.id, None)

    async def _autoplay_next(self, guild, voice_client, previous_track: dict):
        """Autoplay recommendation engine: queries similar tracks by artist/genre when queue ends."""
        try:
            artist = previous_track.get('artist') or ''
            title = previous_track.get('title') or ''
            query = f"scsearch5:{artist} music" if artist and artist != 'SoundCloud' else f"scsearch5:{title} related"

            track_info = await self.extract_track_info(query)
            if track_info:
                track_info['requester'] = '⚡ Autoplay'
                self.queues[guild.id].append(track_info)
                self.play_next(guild, voice_client)
            else:
                self.play_loops.pop(guild.id, None)
        except Exception as e:
            print(f"[Autoplay] Failed to find related track: {e}")
            self.play_loops.pop(guild.id, None)

    def get_guild_state(self, guild_id: int):
        """Returns the complete playback, DSP filter, and queue state for a guild."""
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
        settings = self.guild_settings[guild_id]

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
                'uploader': curr.get('uploader', 'SoundCloud'),
                'requester': curr.get('requester', 'Discord User'),
                'is_local': curr.get('is_local', False),
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
                'uploader': t.get('uploader', 'SoundCloud'),
                'requester': t.get('requester', 'Discord User'),
                'is_local': t.get('is_local', False),
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
            'active_filter': settings.get('filter', 'none'),
            'loop_mode': settings.get('loop', 'off'),
            'autoplay': settings.get('autoplay', False),
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

    async def play_local_file(self, guild_id: int, file_path: str, original_filename: str):
        """Handles custom MP3/audio file uploads from the Web Command Center."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise ValueError(f"Guild {guild_id} not found.")

        duration = probe_audio_duration(file_path)
        clean_name = os.path.splitext(original_filename)[0]

        track_info = {
            'title': clean_name,
            'url': file_path,
            'webpage_url': '',
            'thumbnail': '/static/images/vinyl.png',
            'duration': int(round(duration)),
            'artist': 'Custom Upload',
            'uploader': 'Web User Upload',
            'requester': 'Web User',
            'is_local': True,
            'file_path': file_path,
            'data': {'title': clean_name, 'duration': int(round(duration))}
        }

        voice_client = guild.voice_client
        if not voice_client:
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

    async def seek(self, guild_id: int, position: float):
        """Seamlessly jumps to a specific timestamp in the current track."""
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return False, "Not connected to voice."
        vc = guild.voice_client
        curr = self.current_tracks.get(guild_id)
        if not curr or not curr.get('file_path'):
            return False, "No active track to seek."

        duration = curr.get('duration', 0)
        pos = max(0.0, min(float(position), float(duration - 1) if duration > 1 else 3600.0))

        settings = self.guild_settings[guild_id]
        curr_filter = settings.get('filter', 'none')
        curr_vol = curr['player'].volume if curr.get('player') else 0.5

        new_player = YTDLSource.create_player(
            curr['file_path'],
            curr.get('data', {}),
            volume=curr_vol,
            seek=pos,
            filter_name=curr_filter
        )

        self.is_switching[guild_id] = True
        vc.stop()
        curr['player'] = new_player
        curr['start_time'] = time.time() - pos

        track_dict = dict(curr)
        vc.play(new_player, after=lambda e: self._on_playback_end(guild, vc, e, curr['file_path'], track_dict))
        return True, f"Seeked to {int(pos)}s"

    async def apply_filter(self, guild_id: int, filter_name: str):
        """Applies a real-time DSP audio filter preset (Bass Boost, Nightcore, 8D, etc.)."""
        if filter_name not in AUDIO_FILTERS:
            return False, f"Unknown filter: {filter_name}"

        self.guild_settings[guild_id]['filter'] = filter_name

        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return True, f"Filter set to {filter_name} (will apply to next song)"

        vc = guild.voice_client
        curr = self.current_tracks.get(guild_id)
        if not curr or not curr.get('file_path') or not (vc.is_playing() or vc.is_paused()):
            return True, f"Filter set to {filter_name}"

        now = time.time()
        elapsed = max(0.0, now - curr.get('start_time', now))
        curr_vol = curr['player'].volume if curr.get('player') else 0.5

        new_player = YTDLSource.create_player(
            curr['file_path'],
            curr.get('data', {}),
            volume=curr_vol,
            seek=elapsed,
            filter_name=filter_name
        )

        self.is_switching[guild_id] = True
        vc.stop()
        curr['player'] = new_player
        curr['start_time'] = time.time() - elapsed

        track_dict = dict(curr)
        vc.play(new_player, after=lambda e: self._on_playback_end(guild, vc, e, curr['file_path'], track_dict))
        return True, f"Filter applied: {filter_name}"

    def set_loop_mode(self, guild_id: int, mode: str):
        """Configures repeat loop mode ('off', 'track', 'queue')."""
        if mode not in ('off', 'track', 'queue'):
            return False, "Invalid loop mode. Must be 'off', 'track', or 'queue'."
        self.guild_settings[guild_id]['loop'] = mode
        return True, f"Loop mode set to {mode}."

    def toggle_autoplay(self, guild_id: int, enabled: bool = None):
        """Toggles automatic recommended playback when the queue finishes."""
        if enabled is None:
            self.guild_settings[guild_id]['autoplay'] = not self.guild_settings[guild_id].get('autoplay', False)
        else:
            self.guild_settings[guild_id]['autoplay'] = bool(enabled)
        state = "enabled" if self.guild_settings[guild_id]['autoplay'] else "disabled"
        return True, f"Autoplay {state}."

    def shuffle_queue(self, guild_id: int):
        """Randomizes the order of all tracks in the current queue."""
        q = self.queues.get(guild_id, [])
        if len(q) < 2:
            return False, "Queue needs at least 2 tracks to shuffle."
        random.shuffle(q)
        return True, f"Shuffled {len(q)} tracks."

    def reorder_queue(self, guild_id: int, from_index: int, to_index: int):
        """Moves a track from one index to another in the queue."""
        q = self.queues.get(guild_id, [])
        if 0 <= from_index < len(q) and 0 <= to_index < len(q):
            item = q.pop(from_index)
            q.insert(to_index, item)
            return True, f"Moved '{item['title']}' to position #{to_index + 1}."
        return False, "Invalid queue indices."

    # --- Slash Commands ---
    @app_commands.command(name="play", description="Plays a song from SoundCloud or a direct URL.")
    @app_commands.describe(query="The song to play (URL or SoundCloud search keywords)")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            await interaction.response.send_message("You are not connected to a voice channel.", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        await interaction.response.defer()

        voice_client = interaction.guild.voice_client
        if voice_client is None:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        try:
            track_info = await self.extract_track_info(query)
            if not track_info:
                await interaction.followup.send("No playable tracks found for that search.")
                return

            track_info['requester'] = interaction.user.display_name
            self.queues[interaction.guild.id].append(track_info)
            await interaction.followup.send(f"Added to queue: **{track_info['title']}**")

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
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message("Skipped the current song.")
        else:
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)

    @app_commands.command(name="stop", description="Stops the music, clears the queue, and disconnects.")
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

    @app_commands.command(name="filter", description="Applies a DSP audio filter (Bass Boost, Nightcore, 8D, etc.)")
    @app_commands.describe(preset="The audio filter preset to apply")
    @app_commands.choices(preset=[
        app_commands.Choice(name="Normal / Off", value="none"),
        app_commands.Choice(name="Bass Boost (Deep 808)", value="bassboost"),
        app_commands.Choice(name="Nightcore (Speed & Pitch Up)", value="nightcore"),
        app_commands.Choice(name="Vaporwave (Slowed + Reverb)", value="vaporwave"),
        app_commands.Choice(name="8D Audio (Binaural Panning)", value="8d"),
        app_commands.Choice(name="Treble Boost (Crisp Highs)", value="treble"),
    ])
    async def filter_command(self, interaction: discord.Interaction, preset: app_commands.Choice[str]):
        await interaction.response.defer()
        success, msg = await self.apply_filter(interaction.guild.id, preset.value)
        color = discord.Color.green() if success else discord.Color.red()
        embed = discord.Embed(title="Audio Filter", description=msg, color=color)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="lyrics", description="Shows synchronized lyrics for the current song or searched title.")
    @app_commands.describe(search="Optional track name to search lyrics for")
    async def lyrics_command(self, interaction: discord.Interaction, search: str = None):
        await interaction.response.defer()
        title = search
        artist = ""
        if not title:
            curr = self.current_tracks.get(interaction.guild.id)
            if curr:
                title = curr.get('title')
                artist = curr.get('artist') or curr.get('uploader') or ""
            else:
                await interaction.followup.send("No track is currently playing. Specify a song title: `/lyrics <title>`")
                return

        res = await fetch_lyrics(title, artist)
        embed = discord.Embed(
            title=f"Lyrics: {res.get('track', title)}",
            description=f"**Artist:** {res.get('artist', 'Unknown')}\n\n",
            color=discord.Color.purple()
        )

        if res.get('has_synced'):
            text = "\n".join([f"`{int(l['time']//60):02d}:{int(l['time']%60):02d}` {l['text']}" for l in res['synced_lines'][:35]])
            if len(res['synced_lines']) > 35:
                text += "\n*... view live real-time karaoke sync on the Web Dashboard!*"
            embed.description += text
        else:
            plain = res.get('plain_text', 'No lyrics available.')
            if len(plain) > 2000:
                plain = plain[:1990] + "..."
            embed.description += plain

        embed.set_footer(text="Powered by LRCLIB • Live karaoke mode available on Web Command Center")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="seek", description="Jumps to a specific timestamp in the current song (e.g. 1:30 or 90).")
    @app_commands.describe(timestamp="Timestamp to jump to (e.g. 1:30 or 90)")
    async def seek_command(self, interaction: discord.Interaction, timestamp: str):
        await interaction.response.defer()
        seconds = 0
        if ":" in timestamp:
            parts = timestamp.split(":")
            if len(parts) == 2:
                seconds = int(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        else:
            try:
                seconds = float(timestamp)
            except ValueError:
                await interaction.followup.send("Invalid timestamp format. Use `mm:ss` or seconds (e.g. `1:30` or `90`).")
                return

        success, msg = await self.seek(interaction.guild.id, seconds)
        color = discord.Color.green() if success else discord.Color.red()
        embed = discord.Embed(title="Track Seek", description=msg, color=color)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="loop", description="Sets the repeat mode (off, track, queue).")
    @app_commands.describe(mode="Repeat mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off (No repeat)", value="off"),
        app_commands.Choice(name="Track (Repeat current song)", value="track"),
        app_commands.Choice(name="Queue (Repeat entire playlist)", value="queue"),
    ])
    async def loop_command(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        success, msg = self.set_loop_mode(interaction.guild.id, mode.value)
        embed = discord.Embed(title="Loop Mode", description=msg, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shuffle", description="Shuffles all songs in the current queue.")
    async def shuffle_command(self, interaction: discord.Interaction):
        success, msg = self.shuffle_queue(interaction.guild.id)
        color = discord.Color.green() if success else discord.Color.orange()
        embed = discord.Embed(title="Queue Shuffle", description=msg, color=color)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="autoplay", description="Toggles automatic playback of recommended songs when queue ends.")
    @app_commands.describe(enabled="Explicitly enable or disable autoplay")
    async def autoplay_command(self, interaction: discord.Interaction, enabled: bool = None):
        success, msg = self.toggle_autoplay(interaction.guild.id, enabled)
        embed = discord.Embed(title="Autoplay Radio", description=msg, color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot))
