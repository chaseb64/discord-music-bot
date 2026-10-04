import json
import re
import urllib.parse
import urllib.request
import asyncio

_lyrics_cache = {}

def clean_title(title: str) -> tuple[str, str]:
    """
    Cleans up track titles by stripping common suffixes like:
    [Official Music Video], (Audio), (Lyrics), feat. X, etc.
    Returns (cleaned_title, extracted_artist).
    """
    if not title:
        return "", ""

    # Split by hyphen if title is formatted as "Artist - Title"
    artist = ""
    clean = title
    if " - " in clean:
        parts = clean.split(" - ", 1)
        artist = parts[0].strip()
        clean = parts[1].strip()

    # Strip bracketed metadata
    clean = re.sub(r'\[.*?\]', '', clean)
    clean = re.sub(r'\(.*?(official|video|audio|lyrics|remix|feat|ft|prod).*?\)', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s(feat\.?|ft\.?)\s.*$', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s+', ' ', clean).strip()

    return clean, artist

def parse_lrc(lrc_text: str) -> list[dict]:
    """
    Parses LRC time-coded string into a list of { time: float, text: str }.
    Format: [00:12.34] Some lyrics text
    """
    lines = []
    pattern = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')
    for raw_line in lrc_text.splitlines():
        match = pattern.match(raw_line.strip())
        if match:
            mins = int(match.group(1))
            secs = float(match.group(2))
            total_sec = round(mins * 60 + secs, 2)
            text = match.group(3).strip()
            if text:  # Ignore empty timestamp markers
                lines.append({'time': total_sec, 'text': text})
    return lines

def _fetch_sync(url: str):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'DiscordMusicBot/2.0 (GitHub: chaseb64/discord-music-bot)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"[Lyrics] Sync fetch notice ({type(e).__name__}): {e}")
    return None

async def fetch_lyrics(title: str, artist: str = "") -> dict:
    """
    Fetches time-synced lyrics from LRCLIB.
    Returns dict with { track, artist, synced_lines: [...], plain_text: str, has_synced: bool }
    """
    cleaned_title, extracted_artist = clean_title(title)
    search_artist = artist or extracted_artist

    cache_key = f"{cleaned_title.lower()}|{search_artist.lower()}"
    if cache_key in _lyrics_cache:
        return _lyrics_cache[cache_key]

    result = {
        'track': title,
        'artist': search_artist or 'Unknown',
        'has_synced': False,
        'synced_lines': [],
        'plain_text': 'No lyrics found for this track.'
    }

    loop = asyncio.get_event_loop()

    try:
        # 1. Attempt exact match via /api/get
        params = {'track_name': cleaned_title}
        if search_artist:
            params['artist_name'] = search_artist

        url = f"https://lrclib.net/api/get?{urllib.parse.urlencode(params)}"
        data = await loop.run_in_executor(None, _fetch_sync, url)
        if data and isinstance(data, dict):
            synced = data.get('syncedLyrics')
            plain = data.get('plainLyrics')
            if synced:
                lines = parse_lrc(synced)
                result['has_synced'] = len(lines) > 0
                result['synced_lines'] = lines
            if plain:
                result['plain_text'] = plain
            result['artist'] = data.get('artistName') or search_artist
            result['track'] = data.get('trackName') or cleaned_title
            _lyrics_cache[cache_key] = result
            return result

        # 2. Fallback to /api/search
        q = f"{search_artist} {cleaned_title}".strip() if search_artist else cleaned_title
        url_search = f"https://lrclib.net/api/search?{urllib.parse.urlencode({'q': q})}"
        search_data = await loop.run_in_executor(None, _fetch_sync, url_search)
        if search_data and isinstance(search_data, list) and len(search_data) > 0:
            best = search_data[0]
            synced = best.get('syncedLyrics')
            plain = best.get('plainLyrics')
            if synced:
                lines = parse_lrc(synced)
                result['has_synced'] = len(lines) > 0
                result['synced_lines'] = lines
            if plain:
                result['plain_text'] = plain
            result['artist'] = best.get('artistName') or search_artist
            result['track'] = best.get('trackName') or cleaned_title
            _lyrics_cache[cache_key] = result
            return result

    except Exception as e:
        result['plain_text'] = f"Could not load lyrics: {e}"

    _lyrics_cache[cache_key] = result
    return result
