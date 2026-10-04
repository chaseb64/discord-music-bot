import os
import re
import time
import asyncio
import json
import logging
from aiohttp import web, WSMsgType
import psutil

_log = logging.getLogger("web.dashboard")

class WebDashboard:
    def __init__(self, bot):
        self.bot = bot
        # Allow up to 100MB for direct MP3 audio file uploads
        self.app = web.Application(client_max_size=100 * 1024 * 1024)
        self.websockets = set()
        self.broadcast_task = None
        self.visualizer_task = None
        self.setup_routes()

    def setup_routes(self):
        # Core API routes
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/api/status', self.handle_api_status)
        self.app.router.add_get('/api/guild/{guild_id}', self.handle_api_guild)
        self.app.router.add_post('/api/play', self.handle_api_play)
        self.app.router.add_post('/api/skip', self.handle_api_skip)
        self.app.router.add_post('/api/pause', self.handle_api_pause)
        self.app.router.add_post('/api/stop', self.handle_api_stop)
        self.app.router.add_post('/api/volume', self.handle_api_volume)
        self.app.router.add_post('/api/queue/remove', self.handle_api_queue_remove)

        # Extended Feature routes: Audio FX, Seeking, Looping, Autoplay, Shuffle, Lyrics, MP3 Upload
        self.app.router.add_post('/api/filter', self.handle_api_filter)
        self.app.router.add_post('/api/seek', self.handle_api_seek)
        self.app.router.add_post('/api/loop', self.handle_api_loop)
        self.app.router.add_post('/api/autoplay', self.handle_api_autoplay)
        self.app.router.add_post('/api/shuffle', self.handle_api_shuffle)
        self.app.router.add_post('/api/queue/move', self.handle_api_queue_move)
        self.app.router.add_get('/api/lyrics', self.handle_api_lyrics)
        self.app.router.add_post('/api/upload', self.handle_api_upload)

        self.app.router.add_get('/ws', self.handle_websocket)

        # Static files
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
        if os.path.exists(static_dir):
            self.app.router.add_static('/static/', path=static_dir, name='static')

    def get_music_cog(self):
        return self.bot.get_cog("Music")

    def get_system_metrics(self):
        start_time = getattr(self.bot, 'start_time', time.time())
        uptime_seconds = int(round(time.time() - start_time))
        m, s = divmod(uptime_seconds, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        if d > 0:
            uptime_str = f"{d}d {h}h {m}m"
        elif h > 0:
            uptime_str = f"{h}h {m}m {s}s"
        else:
            uptime_str = f"{m}m {s}s"

        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        ping = int(round(self.bot.latency * 1000)) if (self.bot.latency and self.bot.latency != float('inf')) else 0
        streams = getattr(self.bot, 'total_streams_completed', 0)

        update_info = None
        try:
            from version import get_release_info, _cached_update_info
            rel = get_release_info()
            update_info = _cached_update_info
        except Exception:
            rel = {'version': '2.4.2', 'tag': 'v2.4.2', 'codename': 'Valkyrie', 'commit': 'main', 'date': ''}

        return {
            'uptime_str': uptime_str,
            'uptime_seconds': uptime_seconds,
            'uptime': uptime_seconds,
            'cpu_percent': cpu,
            'cpu': cpu,
            'ram_percent': ram.percent,
            'ram_used_mb': int(round(ram.used / (1024 * 1024))),
            'ram': int(round(ram.used / (1024 * 1024))),
            'ram_total_mb': int(round(ram.total / (1024 * 1024))),
            'total_streams': streams,
            'streams_completed': streams,
            'ping_ms': ping,
            'ping': ping,
            'guild_count': len(self.bot.guilds),
            'release': rel,
            'version': rel['tag'],
            'update_info': update_info,
        }

    async def handle_index(self, request):
        index_file = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static', 'index.html'))
        if os.path.exists(index_file):
            return web.FileResponse(index_file)
        return web.Response(text="Dashboard static index.html not found.", status=404)

    async def handle_api_status(self, request):
        music_cog = self.get_music_cog()
        guilds_state = music_cog.get_all_guilds_state() if music_cog else []

        bot_user = {
            'name': self.bot.user.name if self.bot.user else "Discord Music Bot",
            'id': str(self.bot.user.id) if self.bot.user else "",
            'avatar': str(self.bot.user.display_avatar.url) if (self.bot.user and self.bot.user.display_avatar) else "/static/images/logo.png",
        }

        update_info = None
        try:
            from version import get_release_info, check_github_update
            rel = get_release_info()
            update_info = await check_github_update()
        except Exception:
            rel = {'version': '2.4.2', 'tag': 'v2.4.2', 'codename': 'Valkyrie', 'commit': 'main', 'date': ''}

        data = {
            'online': True,
            'bot': bot_user,
            'release': rel,
            'version': rel['tag'],
            'update_info': update_info,
            'metrics': self.get_system_metrics(),
            'guilds': guilds_state,
        }
        return web.json_response(data)

    async def handle_api_guild(self, request):
        guild_id_str = request.match_info.get('guild_id')
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({'error': 'Invalid guild ID'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        state = music_cog.get_guild_state(guild_id)
        if not state:
            return web.json_response({'error': 'Guild not found'}, status=404)

        return web.json_response(state)

    async def handle_api_play(self, request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON body'}, status=400)

        guild_id = body.get('guild_id')
        query = body.get('query', '').strip()

        if not guild_id or not query:
            return web.json_response({'error': 'guild_id and query are required'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        try:
            track = await music_cog.play_from_web(int(guild_id), query)
            await self.broadcast_update()
            return web.json_response({'success': True, 'track': track})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def handle_api_upload(self, request):
        """Processes multipart form uploads of user MP3/audio files securely."""
        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        allowed_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.webm', '.opus'}
        reader = await request.multipart()
        guild_id = None
        saved_file_path = None
        orig_filename = "uploaded_track.mp3"

        uploads_dir = os.path.abspath(os.path.join('downloads', 'uploads'))
        os.makedirs(uploads_dir, exist_ok=True)

        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == 'guild_id':
                guild_id = (await part.text()).strip()
            elif part.name == 'file':
                raw_filename = os.path.basename(part.filename or "uploaded_track.mp3")
                ext = os.path.splitext(raw_filename)[1].lower()
                if ext not in allowed_extensions:
                    return web.json_response({'error': f'Unsupported file extension "{ext}". Allowed: {", ".join(sorted(allowed_extensions))}'}, status=400)

                orig_filename = raw_filename
                clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', raw_filename)
                dest = os.path.join(uploads_dir, f"{int(time.time())}_{clean_name}")
                dest_abs = os.path.abspath(dest)

                # Prevent Path Traversal
                if os.path.commonpath([dest_abs, uploads_dir]) != uploads_dir:
                    return web.json_response({'error': 'Invalid destination file path.'}, status=400)

                with open(dest_abs, 'wb') as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        await asyncio.to_thread(f.write, chunk)
                saved_file_path = dest_abs

        if not guild_id or not saved_file_path:
            return web.json_response({'error': 'guild_id and file are required.'}, status=400)

        try:
            guild_id_int = int(guild_id)
        except (ValueError, TypeError):
            return web.json_response({'error': 'Invalid guild_id'}, status=400)

        try:
            track = await music_cog.play_local_file(guild_id_int, saved_file_path, orig_filename)
            await self.broadcast_update()
            return web.json_response({'success': True, 'track': track})
        except Exception as e:
            _log.error(f"Error handling upload: {e}")
            return web.json_response({'error': str(e)}, status=400 if isinstance(e, ValueError) else 500)

    async def handle_api_skip(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
        except Exception:
            return web.json_response({'error': 'Invalid guild_id'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.skip_from_web(guild_id)
        if success:
            await self.broadcast_update()
            return web.json_response({'success': True, 'message': msg})
        return web.json_response({'error': msg}, status=400)

    async def handle_api_pause(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
        except Exception:
            return web.json_response({'error': 'Invalid guild_id'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.pause_from_web(guild_id)
        if success:
            await self.broadcast_update()
            return web.json_response({'success': True, 'status': msg.lower()})
        return web.json_response({'error': msg}, status=400)

    async def handle_api_stop(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
        except Exception:
            return web.json_response({'error': 'Invalid guild_id'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = await music_cog.stop_from_web(guild_id)
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg})

    async def handle_api_volume(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            vol = int(body.get('volume', 100))
        except Exception:
            return web.json_response({'error': 'Invalid parameters'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.set_volume_from_web(guild_id, vol)
        if success:
            await self.broadcast_update()
            return web.json_response({'success': True, 'volume': vol})
        return web.json_response({'error': msg}, status=400)

    async def handle_api_filter(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            filter_name = str(body.get('filter', 'none')).strip().lower()
        except Exception:
            return web.json_response({'error': 'Invalid request body'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = await music_cog.apply_filter(guild_id, filter_name)
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg, 'filter': filter_name})

    async def handle_api_seek(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            position = float(body.get('position', 0))
        except Exception:
            return web.json_response({'error': 'Invalid request body'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = await music_cog.seek(guild_id, position)
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg, 'position': position})

    async def handle_api_loop(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            mode = str(body.get('mode', 'off')).strip().lower()
        except Exception:
            return web.json_response({'error': 'Invalid request body'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.set_loop_mode(guild_id, mode)
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg, 'mode': mode})

    async def handle_api_autoplay(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            enabled = body.get('enabled')
        except Exception:
            return web.json_response({'error': 'Invalid request body'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.toggle_autoplay(guild_id, enabled)
        await self.broadcast_update()
        is_enabled = music_cog.guild_settings[guild_id].get('autoplay', False)
        return web.json_response({'success': success, 'message': msg, 'autoplay': is_enabled})

    async def handle_api_shuffle(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
        except Exception:
            return web.json_response({'error': 'Invalid request body'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.shuffle_queue(guild_id)
        if success:
            await self.broadcast_update()
            return web.json_response({'success': True, 'message': msg})
        return web.json_response({'error': msg}, status=400)

    async def handle_api_queue_move(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            from_idx = int(body.get('from_index'))
            to_idx = int(body.get('to_index'))
        except Exception:
            return web.json_response({'error': 'Invalid request body'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.reorder_queue(guild_id, from_idx, to_idx)
        if success:
            await self.broadcast_update()
            return web.json_response({'success': True, 'message': msg})
        return web.json_response({'error': msg}, status=400)

    async def handle_api_lyrics(self, request):
        title = request.query.get('title')
        artist = request.query.get('artist', '')
        guild_id_str = request.query.get('guild_id')

        music_cog = self.get_music_cog()
        if not title and guild_id_str and music_cog:
            try:
                guild_id = int(guild_id_str)
                curr = music_cog.current_tracks.get(guild_id)
                if curr:
                    title = curr.get('title')
                    artist = curr.get('artist') or curr.get('uploader') or ''
            except Exception:
                pass

        if not title:
            return web.json_response({'error': 'No track title specified'}, status=400)

        from utils.lyrics import fetch_lyrics
        res = await fetch_lyrics(title, artist)
        return web.json_response({'success': True, 'lyrics': res})

    async def handle_api_queue_remove(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            index = int(body.get('index'))
        except Exception:
            return web.json_response({'error': 'Invalid parameters'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.remove_track_from_web(guild_id, index)
        if success:
            await self.broadcast_update()
            return web.json_response({'success': True, 'message': msg})
        return web.json_response({'error': msg}, status=400)

    async def handle_websocket(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.websockets.add(ws)
        _log.info(f"WebSocket client connected. Total clients: {len(self.websockets)}")

        try:
            music_cog = self.get_music_cog()
            state = {
                'type': 'initial_state',
                'metrics': self.get_system_metrics(),
                'guilds': music_cog.get_all_guilds_state() if music_cog else [],
            }
            await ws.send_str(json.dumps(state))

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    if msg.data == 'ping':
                        await ws.send_str(json.dumps({'type': 'pong'}))
                elif msg.type == WSMsgType.ERROR:
                    _log.error(f"WS connection closed with exception {ws.exception()}")
        finally:
            self.websockets.discard(ws)
            _log.info(f"WebSocket client disconnected. Remaining: {len(self.websockets)}")

        return ws

    async def broadcast_update(self):
        """Pushes state update to all active WebSocket clients."""
        if not self.websockets:
            return
        music_cog = self.get_music_cog()
        payload = json.dumps({
            'type': 'state_update',
            'metrics': self.get_system_metrics(),
            'guilds': music_cog.get_all_guilds_state() if music_cog else [],
        })
        dead_ws = set()
        for ws in list(self.websockets):
            try:
                await ws.send_str(payload)
            except Exception:
                dead_ws.add(ws)
        for ws in dead_ws:
            self.websockets.discard(ws)

    async def start_broadcast_loop(self):
        """Broadcasts server metrics and status every 2.5 seconds."""
        while True:
            try:
                await asyncio.sleep(2.5)
                await self.broadcast_update()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.debug(f"Broadcast loop error: {e}")
                await asyncio.sleep(2)

    async def start_visualizer_loop(self):
        """Streams live 36-band audio spectrum levels to connected dashboards at 20 FPS (50ms)."""
        while True:
            try:
                await asyncio.sleep(0.05)
                if not self.websockets:
                    continue

                music_cog = self.get_music_cog()
                if not music_cog or not music_cog.current_tracks:
                    continue

                bands_by_guild = {}
                for gid, curr in list(music_cog.current_tracks.items()):
                    player = curr.get('player')
                    if player and hasattr(player, 'latest_bands'):
                        bands_by_guild[str(gid)] = player.latest_bands

                if bands_by_guild:
                    payload = json.dumps({
                        'type': 'visualizer_update',
                        'bands_by_guild': bands_by_guild,
                    })
                    dead_ws = set()
                    for ws in list(self.websockets):
                        try:
                            await ws.send_str(payload)
                        except Exception:
                            dead_ws.add(ws)
                    for ws in dead_ws:
                        self.websockets.discard(ws)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.debug(f"Visualizer loop error: {e}")
                await asyncio.sleep(0.1)

async def start_web_server(bot):
    dashboard = WebDashboard(bot)
    runner = web.AppRunner(dashboard.app)
    await runner.setup()

    port = int(os.getenv('PORT') or os.getenv('DASHBOARD_PORT') or 25567)
    host = '0.0.0.0'

    site = web.TCPSite(runner, host, port)
    await site.start()

    dashboard.broadcast_task = asyncio.create_task(dashboard.start_broadcast_loop())
    dashboard.visualizer_task = asyncio.create_task(dashboard.start_visualizer_loop())
    print(f"[Web Dashboard] Dashboard running at http://localhost:{port} (bound to {host}:{port})")

    bot.web_dashboard = dashboard
    bot.web_runner = runner
    return runner
