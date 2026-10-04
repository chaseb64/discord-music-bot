import os
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
        self.app = web.Application()
        self.websockets = set()
        self.broadcast_task = None
        self.setup_routes()

    def setup_routes(self):
        # API Routes
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/api/status', self.handle_api_status)
        self.app.router.add_get('/api/guild/{guild_id}', self.handle_api_guild)
        self.app.router.add_post('/api/play', self.handle_api_play)
        self.app.router.add_post('/api/skip', self.handle_api_skip)
        self.app.router.add_post('/api/pause', self.handle_api_pause)
        self.app.router.add_post('/api/stop', self.handle_api_stop)
        self.app.router.add_post('/api/volume', self.handle_api_volume)
        self.app.router.add_post('/api/queue/remove', self.handle_api_queue_remove)
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
        uptime_str = f"{d}d {h}h {m}m {s}s" if d > 0 else f"{h}h {m}s"

        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        ping = int(round(self.bot.latency * 1000)) if (self.bot.latency and self.bot.latency != float('inf')) else 0
        streams = getattr(self.bot, 'total_streams_completed', 0)

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

        data = {
            'online': True,
            'bot': bot_user,
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
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg})

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
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg})

    async def handle_api_stop(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
        except Exception:
            return web.json_response({'error': 'Invalid guild_id'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.stop_from_web(guild_id)
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg})

    async def handle_api_volume(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            volume = int(body.get('volume', 50))
        except Exception:
            return web.json_response({'error': 'Invalid request parameters'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.set_volume_from_web(guild_id, volume)
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg})

    async def handle_api_queue_remove(self, request):
        try:
            body = await request.json()
            guild_id = int(body.get('guild_id'))
            index = int(body.get('index'))
        except Exception:
            return web.json_response({'error': 'Invalid request parameters'}, status=400)

        music_cog = self.get_music_cog()
        if not music_cog:
            return web.json_response({'error': 'Music system not ready'}, status=503)

        success, msg = music_cog.remove_track_from_web(guild_id, index)
        await self.broadcast_update()
        return web.json_response({'success': success, 'message': msg})

    async def handle_websocket(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.websockets.add(ws)
        _log.info(f"WebSocket client connected. Active: {len(self.websockets)}")

        # Send initial status immediately
        try:
            music_cog = self.get_music_cog()
            metrics = self.get_system_metrics()
            initial_data = {
                'type': 'status_update',
                'metrics': metrics,
                'stats': metrics,
                'guilds': music_cog.get_all_guilds_state() if music_cog else [],
            }
            await ws.send_str(json.dumps(initial_data))
        except Exception:
            pass

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                        action = payload.get('action')
                        if action == 'ping':
                            await ws.send_str(json.dumps({'type': 'pong'}))
                        elif action == 'refresh':
                            await self.broadcast_update()
                    except Exception:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    _log.error(f"WebSocket connection closed with exception {ws.exception()}")
        finally:
            self.websockets.discard(ws)
            _log.info(f"WebSocket client disconnected. Active: {len(self.websockets)}")

        return ws

    async def broadcast_update(self):
        if not self.websockets:
            return

        music_cog = self.get_music_cog()
        metrics = self.get_system_metrics()
        payload = json.dumps({
            'type': 'status_update',
            'metrics': metrics,
            'stats': metrics,
            'guilds': music_cog.get_all_guilds_state() if music_cog else [],
        })

        dead_ws = set()
        for ws in self.websockets:
            try:
                await ws.send_str(payload)
            except Exception:
                dead_ws.add(ws)

        for ws in dead_ws:
            self.websockets.discard(ws)

    async def start_broadcast_loop(self):
        while True:
            try:
                await asyncio.sleep(1.5)
                await self.broadcast_update()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.debug(f"Broadcast loop error: {e}")
                await asyncio.sleep(2)

async def start_web_server(bot):
    dashboard = WebDashboard(bot)
    runner = web.AppRunner(dashboard.app)
    await runner.setup()

    port = int(os.getenv('PORT') or os.getenv('DASHBOARD_PORT') or 25567)
    host = '0.0.0.0'

    site = web.TCPSite(runner, host, port)
    await site.start()

    dashboard.broadcast_task = asyncio.create_task(dashboard.start_broadcast_loop())
    print(f"[Web Dashboard] Dashboard running at http://localhost:{port} (bound to {host}:{port})")

    bot.web_dashboard = dashboard
    bot.web_runner = runner
    return runner
