"""
Aether Beats Version & Release Manifest
"""
import os
import re
import time
import shutil
import subprocess

__version__ = "2.4.0"
__codename__ = "Valkyrie"
__repo__ = "chaseb64/discord-music-bot"

_last_update_check = 0
_cached_update_info = None

def _get_git_binary():
    """Finds the git executable in PATH or standard installation directories."""
    git_bin = shutil.which("git")
    if git_bin:
        return git_bin
    mingit = r"C:\Users\Chase Brannen\AppData\Local\Programs\MinGit\cmd\git.exe"
    if os.path.exists(mingit):
        return mingit
    return "git"

def get_release_info() -> dict:
    """Returns detailed version and release metadata dynamically from Git if available."""
    commit_hash = "release"
    commit_date = ""
    commit_msg = ""
    git_tag_desc = ""

    if os.path.exists('.git'):
        try:
            git_bin = _get_git_binary()
            # Try git describe --tags --always
            desc = subprocess.run([git_bin, "describe", "--tags", "--always"], capture_output=True, text=True, timeout=2)
            if desc.returncode == 0 and desc.stdout.strip():
                git_tag_desc = desc.stdout.strip()

            h = subprocess.run([git_bin, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=2)
            if h.returncode == 0 and h.stdout.strip():
                commit_hash = h.stdout.strip()
            d = subprocess.run([git_bin, "log", "-1", "--format=%cd", "--date=short"], capture_output=True, text=True, timeout=2)
            if d.returncode == 0 and d.stdout.strip():
                commit_date = d.stdout.strip()
            m = subprocess.run([git_bin, "log", "-1", "--format=%s"], capture_output=True, text=True, timeout=2)
            if m.returncode == 0 and m.stdout.strip():
                commit_msg = m.stdout.strip()
        except Exception:
            pass

    # If git describe returned a tag like v2.4.0 or v2.4.0-2-gd075496, use it
    if git_tag_desc and git_tag_desc.startswith('v'):
        tag = git_tag_desc
        # Extract base semver
        match = re.search(r'v?(\d+\.\d+\.\d+)', git_tag_desc)
        version_num = match.group(1) if match else __version__
    else:
        tag = f"v{__version__} ({commit_hash})" if commit_hash != "release" else f"v{__version__}"
        version_num = __version__

    return {
        "version": version_num,
        "codename": __codename__,
        "commit": commit_hash,
        "date": commit_date,
        "commit_message": commit_msg,
        "tag": tag,
        "repo": __repo__,
        "repo_url": f"https://github.com/{__repo__}",
    }

async def check_github_update(force: bool = False) -> dict:
    """Checks the GitHub API to see if a newer release is published on GitHub."""
    global _last_update_check, _cached_update_info
    now = time.time()

    if not force and _cached_update_info and (now - _last_update_check < 1800):
        return _cached_update_info

    rel = get_release_info()
    current_ver = rel["version"]
    result = {
        "has_update": False,
        "current_version": f"v{current_ver}",
        "latest_version": f"v{current_ver}",
        "release_url": f"https://github.com/{__repo__}/releases",
        "release_name": "",
        "checked_at": int(now),
    }

    try:
        import aiohttp
        url = f"https://api.github.com/repos/{__repo__}/releases/latest"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"AetherBeats-Bot/{current_ver}"
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    latest_tag = data.get("tag_name", "").strip()
                    html_url = data.get("html_url", f"https://github.com/{__repo__}/releases")
                    name = data.get("name", latest_tag)

                    if latest_tag:
                        cur_parts = [int(x) for x in re.findall(r'\d+', current_ver)[:3]]
                        lat_parts = [int(x) for x in re.findall(r'\d+', latest_tag)[:3]]
                        has_update = lat_parts > cur_parts

                        result = {
                            "has_update": has_update,
                            "current_version": f"v{current_ver}",
                            "latest_version": latest_tag,
                            "release_url": html_url,
                            "release_name": name,
                            "checked_at": int(now),
                        }
    except Exception:
        pass

    _cached_update_info = result
    _last_update_check = now
    return result
