# 🎵 Aether Beats - Discord Music Bot & Real-Time Web Dashboard

A feature-packed, high-performance Discord music bot powered by `discord.py` (v2.0+) and an integrated live **Web Command Center Dashboard** built with modern glassmorphism aesthetics, real-time WebSockets, dynamic audio visualization, and zero-latency player synchronization.

---

## ✨ Features

### 🎧 Discord Bot Core
- **Slash Commands Only**: Built exclusively with `discord.app_commands` (`/play`, `/pause`, `/skip`, `/stop`, `/queue`, `/nowplaying`, `/volume`, `/resources`, etc.).
- **SoundCloud & Direct Stream Engine**: Default search powered by SoundCloud for pristine audio streaming without YouTube bot-detection blocks, plus direct audio/radio URL playback.
- **Embedded Pagination Queue**: Browse large server queues cleanly with multi-page interactive embeds.
- **Resilient Audio Pipelines**: Automatic static FFmpeg binary installation and musl/glibc Opus library auto-discovery for Alpine Linux / Pterodactyl hosting environments.

### 🌐 Integrated Web Command Center Dashboard
- **Single Process / Zero Latency**: Integrated `aiohttp` web server running inside the bot event loop—no external databases, Redis, or separate backend containers required.
- **Real-Time WebSockets**: Live status synchronization every 1.5 seconds directly updating UI without page refreshes.
- **Now Playing Player Deck**:
  - Track title, artist/uploader, requester, and source tags.
  - Interactive scrub bar with live time progress.
  - Cyberpunk glowing vinyl disc animation synchronized with playback.
  - Real-time 32-bar frequency audio visualizer canvas.
- **Full Player Controls**:
  - Play / Pause toggle
  - Skip to next track
  - Stop and clear voice connection
  - Replay current track
  - Smooth volume control slider with instant mute toggle
- **Interactive Live Queue**:
  - Enqueue songs directly from the browser using SoundCloud search or direct URLs.
  - View real-time queued songs with album artwork, durations, and requester tags.
  - Instant one-click queue item removal.
- **System Vitals & Telemetry**:
  - Live CPU Load %, RAM usage (MB), Gateway Ping (ms), Bot Uptime, and Total Streams Completed.
- **Multi-Server Picker**:
  - Dropdown selector allows operators to monitor and manage playback across different Discord servers where the bot is active.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+
- A Discord Bot Token (from [Discord Developer Portal](https://discord.com/developers/applications))

### 2. Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/chaseb64/discord-music-bot.git
   cd discord-music-bot
   ```

2. **Configure Environment Variables:**
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and supply your Discord Bot Token:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   DASHBOARD_PORT=8080
   ```

3. **Launch the Bot & Dashboard:**
   Use the monolithic startup script:
   ```bash
   python start.py
   ```
   The startup script will automatically:
   - Install required packages from `requirements.txt`.
   - Verify/download static FFmpeg and Opus libraries if needed.
   - Clean up cached temporary audio files.
   - Launch the bot and the web dashboard concurrently.

4. **Access the Dashboard:**
   Open your browser to:
   ```text
   http://localhost:8080
   ```
   *(Or `http://<your-server-ip>:8080` if hosted remotely)*

---

## 🎛️ Discord Slash Commands

| Command | Description |
| :--- | :--- |
| `/play <query>` | Search SoundCloud or provide a direct audio URL to play/queue |
| `/pause` | Toggle pause or resume on current playback |
| `/skip` | Skip the currently playing track |
| `/stop` | Stop playback and disconnect the bot from voice |
| `/nowplaying` | Display an interactive rich embed of the current track and progress |
| `/queue [page]` | View the list of upcoming tracks with embedded pagination |
| `/volume <1-100>` | Adjust player volume |
| `/resources` | View real-time CPU, RAM, uptime, and stream statistics |

---

## 🛠️ Tech Stack

- **Bot Runtime**: Python 3.11+, `discord.py` v2.4+, `yt-dlp`, `psutil`
- **Dashboard Backend**: `aiohttp.web` (embedded inside Discord client loop)
- **Dashboard Frontend**: HTML5 Semantic markup, Modern Vanilla CSS (Glassmorphism, custom mesh glows, responsive grids), Vanilla JavaScript (Canvas Audio Equalizer, WebSockets, REST API).

---

## 📄 License
MIT License
