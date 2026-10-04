import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from utils.banner import get_ansi_colors, print_banner


class TestBannerColors(unittest.TestCase):

    def test_get_ansi_colors_with_no_color_env(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            colors = get_ansi_colors()
            for key, val in colors.items():
                self.assertEqual(val, "", f"Expected empty string for key {key} when NO_COLOR is set")

    def test_get_ansi_colors_normal(self):
        with patch.dict(os.environ, {}, clear=True):
            colors = get_ansi_colors()
            self.assertEqual(colors["cyan"], "\033[96m")
            self.assertEqual(colors["reset"], "\033[0m")

    @patch("os.name", "nt")
    def test_get_ansi_colors_windows_support(self):
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch.dict(os.environ, {}, clear=True):
                colors = get_ansi_colors()
                self.assertIn("cyan", colors)
                mock_kernel32.GetStdHandle.assert_called_once_with(-11)
                mock_kernel32.SetConsoleMode.assert_called_once()

    @patch("os.name", "nt")
    def test_get_ansi_colors_windows_exception_handled(self):
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.GetStdHandle.side_effect = RuntimeError("Console error")

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch.dict(os.environ, {}, clear=True):
                # Should not raise exception
                colors = get_ansi_colors()
                self.assertIn("cyan", colors)


class TestPrintBanner(unittest.TestCase):

    def test_print_banner_normal(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_banner(port=9999)

        output = buf.getvalue()
        self.assertIn("AETHER BEATS", output)
        self.assertIn("9999", output)
        self.assertIn("http://localhost:9999", output)

    def test_print_banner_reconfigure_raises_exception(self):
        mock_stdout = MagicMock()
        mock_stdout.reconfigure.side_effect = RuntimeError("stdout reconfigure failed")

        with patch.object(sys, 'stdout', mock_stdout):
            print_banner(port=8080)

        mock_stdout.reconfigure.assert_called_once_with(encoding='utf-8', errors='replace')
        self.assertTrue(mock_stdout.write.called)

    def test_print_banner_stdout_without_reconfigure(self):
        # Create a mock stdout object that lacks 'reconfigure' attribute
        mock_stdout = MagicMock(spec=['write', 'flush'])

        with patch.object(sys, 'stdout', mock_stdout):
            print_banner(port=7070)

        self.assertFalse(hasattr(mock_stdout, 'reconfigure'))
        self.assertTrue(mock_stdout.write.called)

    def test_print_banner_release_info_import_error(self):
        buf = io.StringIO()
        with patch.dict(sys.modules, {'version': None}):
            with redirect_stdout(buf):
                print_banner(port=8888)

        output = buf.getvalue()
        self.assertIn("v2.4.2", output)
        self.assertIn("Valkyrie", output)

    def test_print_banner_line_print_exception(self):
        # Test line-level print exception handling
        with patch("builtins.print", side_effect=OSError("Disk full or stream closed")):
            # Should gracefully handle exceptions inside the for line in lines loop
            try:
                print_banner(port=5555)
            except Exception as e:
                self.fail(f"print_banner raised an unexpected exception: {e}")


if __name__ == "__main__":
    unittest.main()
