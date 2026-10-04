import unittest
from unittest.mock import patch, MagicMock
import subprocess

from cogs.music import probe_audio_duration


class TestProbeAudioDuration(unittest.TestCase):

    @patch('cogs.music.get_ffmpeg_executable', return_value=None)
    def test_missing_ffmpeg_bin(self, mock_get_ffmpeg):
        duration = probe_audio_duration("/path/to/song.mp3")
        self.assertEqual(duration, 0.0)

    @patch('cogs.music.get_ffmpeg_executable', return_value="/usr/bin/ffmpeg")
    @patch('os.path.exists', return_value=False)
    def test_file_does_not_exist(self, mock_exists, mock_get_ffmpeg):
        duration = probe_audio_duration("/path/to/nonexistent.mp3")
        self.assertEqual(duration, 0.0)

    @patch('cogs.music.get_ffmpeg_executable', return_value="/usr/bin/ffmpeg")
    @patch('os.path.exists', return_value=True)
    @patch('subprocess.run')
    def test_successful_duration_probe(self, mock_run, mock_exists, mock_get_ffmpeg):
        mock_res = MagicMock()
        mock_res.stderr = "Input #0, mp3, from '/path/to/song.mp3':\n  Duration: 00:03:45.50, start: 0.000000, bitrate: 128 kb/s"
        mock_run.return_value = mock_res

        duration = probe_audio_duration("/path/to/song.mp3")
        self.assertEqual(duration, 225.5)
        mock_run.assert_called_once_with(["/usr/bin/ffmpeg", "-i", "/path/to/song.mp3", "-f", "null", "-"], capture_output=True, text=True)

    @patch('cogs.music.get_ffmpeg_executable', return_value="/usr/bin/ffmpeg")
    @patch('os.path.exists', return_value=True)
    @patch('subprocess.run')
    def test_successful_duration_probe_hours(self, mock_run, mock_exists, mock_get_ffmpeg):
        mock_res = MagicMock()
        mock_res.stderr = "Duration: 01:02:03.25, start: 0.000000, bitrate: 192 kb/s"
        mock_run.return_value = mock_res

        duration = probe_audio_duration("/path/to/long_song.mp3")
        self.assertEqual(duration, 3723.25)

    @patch('cogs.music.get_ffmpeg_executable', return_value="/usr/bin/ffmpeg")
    @patch('os.path.exists', return_value=True)
    @patch('subprocess.run')
    def test_no_duration_match_in_stderr(self, mock_run, mock_exists, mock_get_ffmpeg):
        mock_res = MagicMock()
        mock_res.stderr = "Invalid data found when processing input"
        mock_run.return_value = mock_res

        duration = probe_audio_duration("/path/to/corrupt.mp3")
        self.assertEqual(duration, 0.0)

    @patch('cogs.music.get_ffmpeg_executable', return_value="/usr/bin/ffmpeg")
    @patch('os.path.exists', return_value=True)
    @patch('subprocess.run', side_effect=subprocess.SubprocessError("Subprocess failed"))
    def test_subprocess_exception_handling(self, mock_run, mock_exists, mock_get_ffmpeg):
        duration = probe_audio_duration("/path/to/song.mp3")
        self.assertEqual(duration, 0.0)


if __name__ == '__main__':
    unittest.main()
