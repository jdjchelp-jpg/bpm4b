"""
Cross-Platform Folder Asset Portability Engine

Abstracts all file system interactions using native path-joining mechanics
(pathlib.Path / os.path.join) instead of hardcoded slashes, ensuring
correct resolution on Windows, macOS, and Linux.

Feature #6 from the BPM4B v13 feature set.
"""

import os
import sys
import tempfile
import shutil
import platform
from pathlib import Path
from typing import Union, List, Optional


# ─── Path Abstraction Layer ───────────────────────────────────

def safe_path(*parts: str) -> Path:
    """
    Join path components using the OS-native separator.
    Always returns a pathlib.Path object.
    """
    return Path(*parts).resolve()


def safe_str(*parts: str) -> str:
    """Return a native string path (forward slashes on Unix, backslashes on Windows)."""
    return str(safe_path(*parts))


def portable_join(*parts: str) -> str:
    """Join path parts portably — prefer this over string concatenation with '/' or '\\'."""
    return os.path.join(*parts)


def ensure_dir(path: Union[str, Path]) -> Path:
    """Ensure a directory exists, creating parent dirs as needed. Returns the Path."""
    p = Path(path) if isinstance(path, str) else path
    p.mkdir(parents=True, exist_ok=True)
    return p


def temp_dir(prefix: str = 'bpm4b_') -> str:
    """Create a temporary directory and return its portable string path."""
    return tempfile.mkdtemp(prefix=prefix)


def cleanup_dir(path: Union[str, Path]) -> None:
    """Safely remove a directory tree."""
    p = str(path)
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)


def cleanup_file(path: Union[str, Path]) -> None:
    """Safely remove a single file."""
    p = str(path)
    try:
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass


def platform_temp_dir() -> str:
    """Return a platform-appropriate temp directory path."""
    return tempfile.gettempdir()


def is_windows() -> bool:
    return platform.system() == 'Windows'


def is_macos() -> bool:
    return platform.system() == 'Darwin'


def is_linux() -> bool:
    return platform.system() == 'Linux'


# ─── FFmpeg Escaping (platform-safe) ─────────────────────────

def ffmpeg_escape_path(path: Union[str, Path]) -> str:
    """
    Escape a file path for use in FFmpeg concat list files.
    FFmpeg expects forward slashes on all platforms in concat format.
    """
    p = str(path).replace('\\', '/')
    # Escape single quotes for FFmpeg concat
    return p.replace("'", "'\\''")


def ffmpeg_concat_entry(path: Union[str, Path]) -> str:
    """Generate a concat list file entry with proper escaping."""
    return f"file '{ffmpeg_escape_path(path)}'"


# ─── Home Directory Helpers ──────────────────────────────────

def home_dir() -> Path:
    """Return the user's home directory."""
    return Path.home()


def config_dir(app_name: str = 'bpm4b') -> Path:
    """Return a platform-appropriate config directory."""
    if is_windows():
        base = Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming')))
    elif is_macos():
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return ensure_dir(base / app_name)


def cache_dir(app_name: str = 'bpm4b') -> Path:
    """Return a platform-appropriate cache directory."""
    if is_windows():
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    elif is_macos():
        base = Path.home() / 'Library' / 'Caches'
    else:
        base = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
    return ensure_dir(base / app_name)


def data_dir(app_name: str = 'bpm4b') -> Path:
    """Return a platform-appropriate data directory."""
    if is_windows():
        base = Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming')))
    elif is_macos():
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share')))
    return ensure_dir(base / app_name)
