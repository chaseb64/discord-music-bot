import io
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from utils.lyrics import clean_title, parse_lrc, _fetch_sync, fetch_lyrics, _lyrics_cache


class TestCleanTitleEdgeCases(unittest.TestCase):

    def test_empty_and_falsy_inputs(self):
        self.assertEqual(clean_title(""), ("", ""))
        self.assertEqual(clean_title(None), ("", ""))
        self.assertEqual(clean_title("   "), ("", ""))

    def test_multiple_hyphens(self):
        title, artist = clean_title("Artist Name - Song Title - Live Version")
        self.assertEqual(artist, "Artist Name")
        self.assertEqual(title, "Song Title - Live Version")

    def test_case_insensitive_bracket_stripping(self):
        title, artist = clean_title("Artist - Song Title (OFFICIAL MUSIC VIDEO)")
        self.assertEqual(artist, "Artist")
        self.assertEqual(title, "Song Title")

        title2, artist2 = clean_title("Artist - Song Title [Official Audio]")
        self.assertEqual(artist2, "Artist")
        self.assertEqual(title2, "Song Title")

        title3, artist3 = clean_title("Artist - Song Title (LYRICS)")
        self.assertEqual(artist3, "Artist")
        self.assertEqual(title3, "Song Title")

    def test_featuring_and_producer_variations(self):
        title1, artist1 = clean_title("Artist - Song Title feat. Featured Artist")
        self.assertEqual(artist1, "Artist")
        self.assertEqual(title1, "Song Title")

        title2, artist2 = clean_title("Artist - Song Title ft. Featured Artist")
        self.assertEqual(artist2, "Artist")
        self.assertEqual(title2, "Song Title")

        title3, artist3 = clean_title("Artist - Song Title FEAT. Featured Artist")
        self.assertEqual(artist3, "Artist")
        self.assertEqual(title3, "Song Title")

        title4, artist4 = clean_title("Artist - Song Title (prod. Producer Name)")
        self.assertEqual(artist4, "Artist")
        self.assertEqual(title4, "Song Title")

    def test_multiple_brackets_and_whitespace_normalization(self):
        title, artist = clean_title("  Artist Name  -  Song   Title  [4K]  (Official Audio)  [Remastered]  ")
        self.assertEqual(artist, "Artist Name")
        self.assertEqual(title, "Song Title")

    def test_title_without_artist(self):
        title, artist = clean_title("Standalone Song Title (Official Video)")
        self.assertEqual(artist, "")
        self.assertEqual(title, "Standalone Song Title")


class TestParseLrc(unittest.TestCase):

    def test_parse_valid_lrc(self):
        lrc_text = "[00:12.34] Hello world\n[01:05.50] Second line\n[02:00.00] "
        parsed = parse_lrc(lrc_text)
        expected = [
            {'time': 12.34, 'text': 'Hello world'},
            {'time': 65.5, 'text': 'Second line'}
        ]
        self.assertEqual(parsed, expected)

    def test_parse_empty_or_invalid_lrc(self):
        self.assertEqual(parse_lrc(""), [])
        self.assertEqual(parse_lrc("Not LRC format at all"), [])


class TestFetchSync(unittest.TestCase):

    @patch('urllib.request.urlopen')
    def test_fetch_sync_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({'trackName': 'Test'}).encode('utf-8')
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.return_value = mock_response

        data = _fetch_sync("https://example.com")
        self.assertEqual(data, {'trackName': 'Test'})

    @patch('urllib.request.urlopen')
    def test_fetch_sync_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection error")
        data = _fetch_sync("https://example.com")
        self.assertIsNone(data)


class TestFetchLyrics(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        _lyrics_cache.clear()

    def tearDown(self):
        _lyrics_cache.clear()

    @patch('utils.lyrics._fetch_sync')
    async def test_fetch_lyrics_exact_match_success(self, mock_fetch):
        mock_fetch.return_value = {
            'trackName': 'Exact Song',
            'artistName': 'Exact Artist',
            'syncedLyrics': '[00:10.00] Exact synced line',
            'plainLyrics': 'Exact plain text'
        }

        res = await fetch_lyrics("Exact Song", "Exact Artist")

        self.assertTrue(res['has_synced'])
        self.assertEqual(res['track'], 'Exact Song')
        self.assertEqual(res['artist'], 'Exact Artist')
        self.assertEqual(res['plain_text'], 'Exact plain text')
        self.assertEqual(res['synced_lines'], [{'time': 10.0, 'text': 'Exact synced line'}])

    @patch('utils.lyrics._fetch_sync')
    async def test_fetch_lyrics_search_fallback_success(self, mock_fetch):
        # First call (/api/get) returns None, second call (/api/search) returns list
        mock_fetch.side_effect = [
            None,
            [{
                'trackName': 'Search Song',
                'artistName': 'Search Artist',
                'syncedLyrics': '[00:05.00] Search line',
                'plainLyrics': 'Search plain lyrics'
            }]
        ]

        res = await fetch_lyrics("Search Song", "Search Artist")

        self.assertTrue(res['has_synced'])
        self.assertEqual(res['track'], 'Search Song')
        self.assertEqual(res['artist'], 'Search Artist')
        self.assertEqual(res['plain_text'], 'Search plain lyrics')

    @patch('utils.lyrics._fetch_sync')
    async def test_fetch_lyrics_no_results(self, mock_fetch):
        # Both /api/get and /api/search return no data
        mock_fetch.side_effect = [None, []]

        res = await fetch_lyrics("Unknown Track", "Unknown Artist")

        self.assertFalse(res['has_synced'])
        self.assertEqual(res['synced_lines'], [])
        self.assertEqual(res['plain_text'], 'No lyrics found for this track.')
        self.assertEqual(res['artist'], 'Unknown Artist')

    @patch('asyncio.get_event_loop')
    async def test_fetch_lyrics_exception_path(self, mock_get_loop):
        # Simulate run_in_executor raising an exception
        mock_loop = MagicMock()
        mock_loop.run_in_executor.side_effect = RuntimeError("Executor network error")
        mock_get_loop.return_value = mock_loop

        res = await fetch_lyrics("Error Track", "Error Artist")

        self.assertFalse(res['has_synced'])
        self.assertEqual(res['synced_lines'], [])
        self.assertEqual(res['plain_text'], 'Could not load lyrics: Executor network error')

    @patch('utils.lyrics._fetch_sync')
    async def test_fetch_lyrics_caching(self, mock_fetch):
        mock_fetch.return_value = {
            'trackName': 'Cached Song',
            'artistName': 'Cached Artist',
            'plainLyrics': 'Cached lyrics'
        }

        # First call fetches and caches
        res1 = await fetch_lyrics("Cached Song", "Cached Artist")
        # Second call should retrieve from cache without calling _fetch_sync again
        res2 = await fetch_lyrics("Cached Song", "Cached Artist")

        self.assertEqual(res1, res2)
        self.assertEqual(mock_fetch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
