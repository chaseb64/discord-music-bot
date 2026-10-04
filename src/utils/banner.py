"""
ASCII Art & Startup Banner for Aether Beats
High-fidelity neon terminal display with cross-platform ANSI compatibility.
"""

import sys
import os
import platform

def get_ansi_colors():
    """Return color codes if terminal supports ANSI, otherwise empty strings."""
    # Check if ANSI colors should be enabled
    no_color = os.getenv("NO_COLOR") is not None
    if no_color:
        return {k: "" for k in [
            "cyan", "blurple", "magenta", "pink", "green",
            "yellow", "white", "dim", "bold", "reset", "bg_dark"
        ]}

    # Enable ANSI escape sequences on Windows console if needed
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # STD_OUTPUT_HANDLE = -11
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass

    return {
        "cyan": "\033[96m",
        "blurple": "\033[38;5;105m",
        "magenta": "\033[95m",
        "pink": "\033[38;5;213m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "white": "\033[97m",
        "dim": "\033[2m",
        "bold": "\033[1m",
        "reset": "\033[0m"
    }

def print_banner(port: int = 25567):
    """Prints the futuristic Aether Beats startup ASCII art banner."""
    # Ensure stdout handles encoding gracefully without throwing UnicodeEncodeError
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    c = get_ansi_colors()
    cyan = c["cyan"]
    blurple = c["blurple"]
    magenta = c["magenta"]
    pink = c["pink"]
    green = c["green"]
    yellow = c["yellow"]
    white = c["white"]
    dim = c["dim"]
    bold = c["bold"]
    rst = c["reset"]

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_name = f"{platform.system()} {platform.machine()}"

    try:
        from version import get_release_info
        rel = get_release_info()
    except Exception:
        rel = {"version": "2.4.0", "tag": "v2.4.0", "codename": "Valkyrie", "commit": ""}

    lines = [
        "",
        rf"{cyan}                 .------------------------.                 {rst}",
        rf"{cyan}                /                          \                {rst}",
        rf"{blurple}               |        /\   /\  /\         |               {rst}",
        rf"{magenta}              .-.      /  \ /  \/  \  /\   .-.              {rst}",
        rf"{pink}             (   )    /    V        \/    (   )             {rst}",
        rf"{pink}             |===|    || | |||| ||| | ||  |===|             {rst}",
        rf"{magenta}              '-'                          '-'              {rst}",
        "",
        rf"{cyan}    ___   _____ _____ _   _ _____ ____    {magenta} ____  _____    _  _____ ____   {rst}",
        rf"{cyan}   / _ \ | ____|_   _| | | | ____|  _ \   {magenta}| __ )| ____|  / \|_   _/ ___|  {rst}",
        rf"{cyan}  / /_\ \|  _|   | | | |_| |  _| | |_) |  {magenta}|  _ \|  _|   / _ \ | | \___ \  {rst}",
        rf"{cyan} / /_   \| |___  | | |  _  | |___|  _ <   {magenta}| |_) | |___ / ___ \| |  ___) | {rst}",
        rf"{cyan}/_/  \_|_|_____| |_| |_| |_|_____|_| \_\  {magenta}|____/|_____/_/   \_\_| |____/  {rst}",
        "",
        rf"{blurple}  ==================================================================={rst}",
        rf"  {bold}{white}AETHER BEATS{rst} {dim}::{rst} {pink}Pro Discord Audio Engine & Command Center{rst}",
        rf"  {cyan}> Release Build :{rst} {yellow}{bold}{rel['tag']}{rst} {dim}[{rel['codename']} Edition]{rst}",
        rf"{blurple}  ==================================================================={rst}",
        rf"  {cyan}> Web Dashboard :{rst} {green}http://localhost:{port}{rst} {dim}(Bound to 0.0.0.0:{port}){rst}",
        rf"  {cyan}> Audio Core    :{rst} FFmpeg {dim}(192k Stereo PCM){rst} + Hardware Opus",
        rf"  {cyan}> DSP FX Engine :{rst} 8 Studio Filters {dim}(Bass Boost, Nightcore, 8D...){rst}",
        rf"  {cyan}> Interactive   :{rst} Real-time Visualizer, Karaoke Lyrics & MP3 Uploader",
        rf"  {cyan}> Architecture  :{rst} Python {py_ver} {dim}on {os_name}{rst}",
        rf"{blurple}  ==================================================================={rst}",
        ""
    ]

    for line in lines:
        try:
            print(line)
        except Exception:
            # Fallback if raw printing fails
            pass

if __name__ == "__main__":
    print_banner()
