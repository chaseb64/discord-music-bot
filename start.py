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

    # Install dependencies
    print("Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

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

    # Run the bot
    print("Starting the bot...")
    subprocess.check_call([sys.executable, "src/bot.py"])

if __name__ == "__main__":
    main()
