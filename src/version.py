"""
Aether Beats Version & Release Manifest
"""
import os
import subprocess

__version__ = "2.4.0"
__codename__ = "Valkyrie"

def get_release_info() -> dict:
    """Returns detailed version and release metadata, including git commit if available."""
    commit_hash = "release"
    commit_date = ""
    commit_msg = ""

    if os.path.exists('.git'):
        try:
            h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=2)
            if h.returncode == 0 and h.stdout.strip():
                commit_hash = h.stdout.strip()
            d = subprocess.run(["git", "log", "-1", "--format=%cd", "--date=short"], capture_output=True, text=True, timeout=2)
            if d.returncode == 0 and d.stdout.strip():
                commit_date = d.stdout.strip()
            m = subprocess.run(["git", "log", "-1", "--format=%s"], capture_output=True, text=True, timeout=2)
            if m.returncode == 0 and m.stdout.strip():
                commit_msg = m.stdout.strip()
        except Exception:
            pass

    tag = f"v{__version__} ({commit_hash})" if commit_hash != "release" else f"v{__version__}"

    return {
        "version": __version__,
        "codename": __codename__,
        "commit": commit_hash,
        "date": commit_date,
        "commit_message": commit_msg,
        "tag": tag,
    }
