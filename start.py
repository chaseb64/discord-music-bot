import subprocess
import sys

def main():
    # Install dependencies
    print("Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Ensure ffmpeg binary paths are available
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass

    # Run the bot
    print("Starting the bot...")
    subprocess.check_call([sys.executable, "src/bot.py"])

if __name__ == "__main__":
    main()
