import subprocess
import sys

def main():
    # Install dependencies
    print("Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "-r", "requirements.txt"])

    # Run the bot
    print("Starting the bot...")
    subprocess.check_call([sys.executable, "src/bot.py"])

if __name__ == "__main__":
    main()
