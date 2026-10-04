import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, AsyncMock
import aiohttp
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from web.server import WebDashboard

class TestWebDashboardUpload(AioHTTPTestCase):
    async def get_application(self):
        bot = MagicMock()
        music_cog = MagicMock()
        music_cog.play_local_file = AsyncMock(return_value={'title': 'uploaded_track.mp3'})
        bot.get_cog.return_value = music_cog
        self.dashboard = WebDashboard(bot)
        return self.dashboard.app

    @unittest_run_loop
    async def test_upload_mp3_success(self):
        data = aiohttp.FormData()
        data.add_field('guild_id', '123456789')
        data.add_field(
            'file',
            b'A' * (1024 * 1024), # 1MB binary data
            filename='test_song.mp3',
            content_type='audio/mpeg'
        )

        resp = await self.client.post('/api/upload', data=data)
        self.assertEqual(resp.status, 200)
        json_resp = await resp.json()
        self.assertTrue(json_resp.get('success'))
        self.assertIn('track', json_resp)

if __name__ == '__main__':
    unittest.main()
