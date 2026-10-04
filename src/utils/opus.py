import os
import sys
import platform
import urllib.request
import io
import tarfile
import discord.opus

def get_install_lib_dir():
    """Determines the best local directory to store downloaded libraries."""
    if os.path.exists('/home/container') and os.access('/home/container', os.W_OK):
        return '/home/container/lib'
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.path.join(base_dir, 'lib')

def download_alpine_opus(target_dir):
    """Downloads musl-compatible libopus from Alpine Linux official mirror."""
    machine = platform.machine().lower()
    if 'arm64' in machine or 'aarch64' in machine:
        arch = 'aarch64'
    elif 'x86_64' in machine or 'amd64' in machine:
        arch = 'x86_64'
    else:
        print(f"[Opus] Unsupported architecture for automatic download: {machine}")
        return None

    urls = [
        f"https://dl-cdn.alpinelinux.org/alpine/edge/main/{arch}/opus-1.6.1-r0.apk",
        f"https://dl-cdn.alpinelinux.org/alpine/v3.20/main/{arch}/opus-1.5.2-r0.apk",
    ]

    os.makedirs(target_dir, exist_ok=True)
    req_headers = {'User-Agent': 'Mozilla/5.0'}

    for url in urls:
        print(f"[Opus] Downloading musl libopus ({arch}) from {url}...")
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()

            extracted_target = os.path.join(target_dir, 'libopus.so.0')
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as tar:
                for member in tar.getmembers():
                    if member.isreg() and 'libopus.so' in member.name:
                        f = tar.extractfile(member)
                        if f:
                            content = f.read()
                            # Write both the full version name and libopus.so.0
                            filename = os.path.basename(member.name)
                            out_version_path = os.path.join(target_dir, filename)
                            with open(out_version_path, 'wb') as out_f:
                                out_f.write(content)
                            os.chmod(out_version_path, 0o755)

                            with open(extracted_target, 'wb') as out_f2:
                                out_f2.write(content)
                            os.chmod(extracted_target, 0o755)

            if os.path.exists(extracted_target):
                print(f"[Opus] Successfully extracted libopus to: {extracted_target}")
                return extracted_target
        except Exception as e:
            print(f"[Opus] Download attempt failed from {url}: {e}")
            continue

    return None

def ensure_opus():
    """Ensures that the Opus shared library is loaded into discord.opus."""
    if discord.opus.is_loaded():
        return True

    # 1. Custom environment variable override
    custom = os.getenv('OPUS_PATH')
    if custom and os.path.exists(custom):
        try:
            discord.opus.load_opus(custom)
            if discord.opus.is_loaded():
                print(f"[Opus] Loaded from OPUS_PATH: {custom}")
                return True
        except Exception as e:
            print(f"[Opus] Failed to load OPUS_PATH ({custom}): {e}")

    # 2. Check local directories
    local_dir = get_install_lib_dir()
    local_candidates = [
        os.path.join(local_dir, 'libopus.so.0'),
        os.path.join(local_dir, 'libopus.so'),
        os.path.join('/home/container/bin', 'libopus.so.0'),
        os.path.join(os.path.abspath('bin'), 'libopus.so.0'),
    ]
    for cand in local_candidates:
        if os.path.exists(cand):
            try:
                discord.opus.load_opus(cand)
                if discord.opus.is_loaded():
                    print(f"[Opus] Loaded local Opus library from: {cand}")
                    return True
            except Exception:
                pass

    # 3. Check system standard locations (Alpine, Debian, Ubuntu)
    system_candidates = [
        'libopus.so.0',
        'libopus.so',
        '/usr/lib/libopus.so.0',
        '/usr/lib/libopus.so',
        '/usr/local/lib/libopus.so.0',
        '/usr/local/lib/libopus.so',
        '/lib/libopus.so.0',
        '/lib/libopus.so',
        '/usr/lib/aarch64-linux-gnu/libopus.so.0',
        '/usr/lib/x86_64-linux-gnu/libopus.so.0',
    ]
    for cand in system_candidates:
        try:
            discord.opus.load_opus(cand)
            if discord.opus.is_loaded():
                print(f"[Opus] Loaded system Opus library from: {cand}")
                return True
        except Exception:
            pass

    # 4. On Linux (e.g. Alpine without opus package installed), download musl libopus
    if sys.platform == 'linux':
        downloaded = download_alpine_opus(local_dir)
        if downloaded:
            try:
                discord.opus.load_opus(downloaded)
                if discord.opus.is_loaded():
                    print(f"[Opus] Loaded downloaded Opus library: {downloaded}")
                    return True
            except Exception as e:
                print(f"[Opus] Error loading downloaded library ({downloaded}): {e}")

    # 5. On Windows, discord.py typically bundles libopus DLL in discord/bin/
    return discord.opus.is_loaded()
