import os
import shutil
import subprocess
import sys

def check_ffmpeg():
    candidates = [
        os.getenv('FFMPEG_PATH'),
        shutil.which('ffmpeg'),
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        'ffmpeg'
    ]
    for c in candidates:
        if c:
            try:
                p = subprocess.run([c, '-version'], capture_output=True, text=True, timeout=3)
                if p.returncode == 0:
                    return c
            except Exception:
                pass
    return None

def main():
    # Install dependencies
    print("Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Check for working FFmpeg executable
    ffmpeg_bin = check_ffmpeg()
    if ffmpeg_bin:
        print(f"Verified working FFmpeg at: {ffmpeg_bin}")
    else:
        print("=" * 65)
        print("[WARNING] No working FFmpeg binary found for your operating system.")
        print("If you are running in a Pterodactyl container (Alpine Linux):")
        print("  1. Go to your server web panel -> 'Startup' tab.")
        print("  2. In 'Additional Packages' (or 'PACKAGES'), enter: ffmpeg")
        print("  3. Restart your server.")
        print("=" * 65)

    # Run the bot
    print("Starting the bot...")
    subprocess.check_call([sys.executable, "src/bot.py"])

if __name__ == "__main__":
    main()
