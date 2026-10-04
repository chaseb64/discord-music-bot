# AGENTS.md

## Project Overview
- **Project Name:** Discord Music Bot
- **Language/Runtime:** Python 3.11+
- **Primary Libraries:** `discord.py` (v2.0+), `yt-dlp` (modern fork of yt-dl), `wavelink` or `disnake` (if using Lavalink)
- **External Dependencies:** `ffmpeg` (system binary), Java JRE (if Lavalink is selected)

## Architecture & Layout
- `/src/bot.py`: Main entry point initializing the Discord client and loading extensions.
- `/src/cogs/`: Directory housing system features split by domain.
  - `music.py`: Core playback, queue manipulation, and connection loops.
  - `stats.py`: Server resource analytics and playback statistics tracking.
- `/src/utils/`: Helper functions for `ffmpeg` processes, queue arrays, and data formatting.
- `requirements.txt`: Python package manifest.
- `run.sh` or `start.py`: Monolithic startup script managing both the bot process and background dependencies.

## Dual-Process Startup Engineering (Crucial for Jules)
- If implementing **Lavalink**, the startup script must autonomously orchestrate downloading the `Lavalink.jar` file, writing the `application.yml` file, spinning up the Java process in the background, and verifying port availability before starting the Python bot.
- If bypassing Lavalink, `ffmpeg` subprocess calls must include precise flags to optimize audio streaming performance and buffer sizing (`-vn -b:a 192k -reconnect 1`).

## Code Style & Slash Command Conventions
- All user-facing functions must strictly utilize **Discord Application (Slash) Commands** via `discord.app_commands`. Traditional prefix commands (`!play`) are explicitly forbidden.
- The `queue` command must display an embedded pagination system if active tracks exceed 10 entries.
- The `resources` command must gather metrics dynamically utilizing the `psutil` library (CPU, RAM, runtime uptime, and total streams completed).

## Build, Test & Validation Loops
- **Environment Boot:** `pip install -r requirements.txt`
- **Lavalink Validation (Optional):** `curl http://localhost:2333` (Verifies background server integrity)
- **Local Testing Loop:** `python src/bot.py`

## Git Workflow, Deployment & Versioning Rules
- **Automatic Push to Main:** Always automatically stage, commit, and push code changes to the `main` branch upon completing requested edits, fixes, or features so the remote repository is never behind.
- **Ask Before Versioning / Tagging:** NEVER create or push a new release tag automatically without asking first. After pushing changes to `main`, explicitly ask the user if they would like to cut a new release version (e.g., `v2.4.1` or `v2.5.0`). Only create the tag and trigger release packaging when the user confirms.
- **MinGit Path on Windows:** Always invoke Git commands on Windows using `& "C:\Users\Chase Brannen\AppData\Local\Programs\MinGit\cmd\git.exe"`.

