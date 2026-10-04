import os
import sys
import shutil
import platform
import subprocess
import urllib.request
import io
import tarfile

def is_working_ffmpeg(path):
    """Verifies that an executable at the given path can actually run without dynamic linking errors."""
    if not path or not os.path.exists(path):
        return False
    try:
        p = subprocess.run([path, '-version'], capture_output=True, text=True, timeout=5)
        return p.returncode == 0
    except Exception:
        return False

def get_install_dir():
    """Determines the best local directory to store downloaded binaries."""
    # Priority: /home/container/bin if in Pterodactyl, else project bin directory
    if os.path.exists('/home/container') and os.access('/home/container', os.W_OK):
        return '/home/container/bin'
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.path.join(base_dir, 'bin')

def download_static_ffmpeg(target_path):
    """Downloads a truly statically linked FFmpeg binary (musl-compatible, 0 external libc dependencies)."""
    machine = platform.machine().lower()
    if 'arm64' in machine or 'aarch64' in machine:
        arch = 'arm64'
    elif 'x86_64' in machine or 'amd64' in machine:
        arch = 'amd64'
    else:
        print(f"[FFmpeg] Unsupported architecture: {machine}")
        return None

    url = f"https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-{arch}-static.tar.xz"
    print(f"[FFmpeg] Downloading static Linux ({arch}) FFmpeg from {url}...")
    
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()

        print("[FFmpeg] Extracting static binary...")
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as tar:
            for member in tar.getmembers():
                if member.name.endswith('/ffmpeg'):
                    f = tar.extractfile(member)
                    with open(target_path, 'wb') as out_f:
                        out_f.write(f.read())
                    os.chmod(target_path, 0o755)
                    print(f"[FFmpeg] Successfully installed static FFmpeg to {target_path}")
                    return target_path
    except Exception as e:
        print(f"[FFmpeg] Failed to download static binary: {e}")
        return None

def ensure_ffmpeg():
    """Finds or automatically downloads a working FFmpeg binary, adding it to PATH."""
    # 1. Custom environment variable override
    custom = os.getenv('FFMPEG_PATH')
    if custom and is_working_ffmpeg(custom):
        return custom

    # 2. Check local install directory
    install_dir = get_install_dir()
    local_bin = os.path.join(install_dir, 'ffmpeg' + ('.exe' if os.name == 'nt' else ''))
    if is_working_ffmpeg(local_bin):
        if install_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = f"{install_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        return local_bin

    # 3. Check system PATH and standard Linux locations
    candidates = [
        shutil.which('ffmpeg'),
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        '/home/container/bin/ffmpeg',
    ]
    for cand in candidates:
        if cand and is_working_ffmpeg(cand):
            return cand

    # 4. Check imageio_ffmpeg fallback (mainly for Windows local testing)
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if is_working_ffmpeg(exe):
            return exe
    except Exception:
        pass

    # 5. On Linux (including Alpine / musl / Pterodactyl), download the self-contained static binary
    if sys.platform == 'linux':
        downloaded = download_static_ffmpeg(local_bin)
        if downloaded and is_working_ffmpeg(downloaded):
            if install_dir not in os.environ.get('PATH', ''):
                os.environ['PATH'] = f"{install_dir}{os.pathsep}{os.environ.get('PATH', '')}"
            return downloaded

    return None

def get_ffmpeg_executable():
    """Returns the verified working path to FFmpeg."""
    return ensure_ffmpeg()
