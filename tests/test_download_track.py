import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import asyncio

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from cogs.music import YTDLSource

class TestDownloadTrack(unittest.TestCase):

    def test_extract_first_entry(self):
        # When entries key exists
        data_playlist = {
            'entries': [
                None,
                {'id': '123', 'title': 'Track 1'},
                {'id': '456', 'title': 'Track 2'}
            ]
        }
        res = YTDLSource._extract_first_entry(data_playlist)
        self.assertEqual(res['id'], '123')

        # When entries key is empty
        with self.assertRaises(RuntimeError):
            YTDLSource._extract_first_entry({'entries': [None]})

        # Single track data without entries
        single_data = {'id': '789', 'title': 'Single Track'}
        self.assertEqual(YTDLSource._extract_first_entry(single_data), single_data)

    @patch('cogs.music.ytdl')
    def test_try_download_candidates_success(self, mock_ytdl):
        mock_ytdl.extract_info.side_effect = [{'id': '1', 'title': 'Test'}]
        res, err = YTDLSource._try_download_candidates(['https://example.com/1'])
        self.assertEqual(res, ('https://example.com/1', {'id': '1', 'title': 'Test'}))
        self.assertIsNone(err)

    @patch('cogs.music.ytdl')
    def test_try_download_candidates_failure(self, mock_ytdl):
        mock_ytdl.extract_info.side_effect = RuntimeError("Download error")
        res, err = YTDLSource._try_download_candidates(['https://example.com/1'])
        self.assertIsNone(res)
        self.assertIsInstance(err, RuntimeError)

    @patch('os.path.exists')
    @patch('cogs.music.ytdl')
    def test_resolve_file_path_from_requested_downloads(self, mock_ytdl, mock_exists):
        mock_exists.return_value = True
        data = {
            'requested_downloads': [{'filepath': '/tmp/test.mp3'}]
        }
        path = YTDLSource._resolve_file_path(data)
        self.assertEqual(path, '/tmp/test.mp3')

    @patch('os.path.exists')
    @patch('cogs.music.ytdl')
    def test_resolve_file_path_from_prepare_filename(self, mock_ytdl, mock_exists):
        # requested_downloads path missing, prepare_filename succeeds
        mock_exists.side_effect = lambda p: p == '/tmp/prepared.mp3'
        mock_ytdl.prepare_filename.return_value = '/tmp/prepared.mp3'
        data = {'id': '123'}
        path = YTDLSource._resolve_file_path(data)
        self.assertEqual(path, '/tmp/prepared.mp3')

    @patch('os.path.exists')
    @patch('cogs.music.ytdl')
    def test_resolve_file_path_not_found_raises(self, mock_ytdl, mock_exists):
        mock_exists.return_value = False
        mock_ytdl.prepare_filename.return_value = '/tmp/nonexistent.mp3'
        with patch('os.listdir', return_value=[]):
            with self.assertRaises(FileNotFoundError):
                YTDLSource._resolve_file_path({'id': '999'})

    @patch.object(YTDLSource, '_resolve_file_path', return_value='/tmp/song.mp3')
    @patch.object(YTDLSource, '_extract_first_entry', side_effect=lambda d: d)
    @patch.object(YTDLSource, '_try_download_candidates', return_value=(('https://example.com/track', {'id': 'abc'}), None))
    def test_download_track_async(self, mock_candidates, mock_extract, mock_resolve):
        file_path, data = asyncio.run(
            YTDLSource.download_track('https://example.com/track')
        )
        self.assertEqual(file_path, '/tmp/song.mp3')
        self.assertEqual(data, {'id': 'abc'})

if __name__ == '__main__':
    unittest.main()
