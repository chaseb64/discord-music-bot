import os
import subprocess
import sys

# Add src to sys.path so utils can be imported
sys.path.insert(0, os.path.abspath('src'))

def main():
    # Remove incompatible static-ffmpeg package if it was previously installed
    try:
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "static-ffmpeg"], capture_output=True)
    except Exception:
        pass

    # Auto-sync latest code from GitHub if .git directory exists
    if os.path.exists('.git'):
        try:
            print("[Auto-Sync] Pulling latest code from GitHub...")
            res = subprocess.run(["git", "pull", "--ff-only"], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                print(f"[Auto-Sync] Code up-to-date: {res.stdout.strip()}")
            else:
                print(f"[Auto-Sync] Git pull notice: {res.stderr.strip()}")
        except Exception as e:
            print(f"[Auto-Sync] Notice: Could not auto-pull git updates: {e}")

    # Install dependencies and ensure yt-dlp is latest
    print("Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"], capture_output=True, timeout=30)
    except Exception:
        pass

    # Ensure working FFmpeg binary is available (auto-downloads static musl binary on Linux if needed)
    try:
        from utils.ffmpeg import ensure_ffmpeg
        ffmpeg_bin = ensure_ffmpeg()
        if ffmpeg_bin:
            print(f"[FFmpeg] Verified working FFmpeg at: {ffmpeg_bin}")
        else:
            print("[FFmpeg] Notice: System FFmpeg was not detected.")
    except Exception as e:
        print(f"[FFmpeg] Verification note: {e}")

    # Ensure working Opus library is available (auto-downloads musl binary on Alpine Linux if needed)
    try:
        from utils.opus import ensure_opus
        if ensure_opus():
            print("[Opus] Verified working Opus library.")
        else:
            print("[Opus] Notice: Opus library could not be verified.")
    except Exception as e:
        print(f"[Opus] Verification note: {e}")

    # Clean up downloads and uploads directory on startup
    downloads_dir = os.path.abspath('downloads')
    if os.path.exists(downloads_dir):
        for root, dirs, files in os.walk(downloads_dir):
            for f in files:
                p = os.path.join(root, f)
                try:
                    os.remove(p)
                except Exception:
                    pass

    # Run the bot
    print("Starting the bot...")
    subprocess.check_call([sys.executable, "src/bot.py"])

if __name__ == "__main__":
    main()
