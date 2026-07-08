"""
Headless CLI Processing Profile Manager

Allows power users to save conversion flag sets into reusable local config files.
Reads .bpm4brc configuration files from home and project directories.

Feature #11 from the BPM4B v13 feature set.
"""

import os
import json
import configparser
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .path_utils import home_dir, config_dir, ensure_dir

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────

RC_FILENAMES = ['.bpm4brc', 'bpm4brc.ini', 'bpm4brc.json', '.bpm4brc.json']

DEFAULT_PROFILE = {
    'audio': {
        'quality': '64k',
        'format': 'm4b',
        'normalize': False,
        'volume': 1.0,
        'concurrency': 0,  # 0 = auto
    },
    'tts': {
        'voice': 'af_heart',
        'speed': 1.0,
        'engine': 'kokoro',
    },
    'metadata': {
        'author': '',
        'genre': '',
        'language': 'en',
        'embed_cover': True,
    },
    'processing': {
        'cache_enabled': False,
        'cache_dir': '',
        'auto_trim_silence': False,
        'trim_threshold': '-50dB',
        'roman_numeral_resolve': True,
        'stat_block_compact': False,
    },
    'logging': {
        'level': 'INFO',
        'log_file': '',
        'job_history': True,
    },
}


# ─── Config Loading ──────────────────────────────────────────

def find_rc_file() -> Optional[str]:
    """
    Search for config files in order of priority:
    1. Current working directory
    2. Project root (parent dirs up to 3 levels)
    3. Home directory
    4. Platform config directory
    """
    search_dirs = [
        os.getcwd(),
        home_dir(),
        str(config_dir('bpm4b')),
    ]

    # Add parent dirs of cwd (up to 3 levels)
    cwd = Path(os.getcwd())
    for parent in cwd.parents:
        if len(search_dirs) > 6:
            break
        search_dirs.append(str(parent))

    seen = set()
    for directory in search_dirs:
        if directory in seen:
            continue
        seen.add(directory)
        for rc_name in RC_FILENAMES:
            rc_path = os.path.join(directory, rc_name)
            if os.path.isfile(rc_path):
                return rc_path

    return None


def load_profile(profile_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load a processing profile from a config file.
    Merges with defaults so all keys are present.

    Args:
        profile_path: Path to config file (auto-find if None)

    Returns:
        Merged profile dict
    """
    config: Dict[str, Any] = {}
    config.update(_deep_copy(DEFAULT_PROFILE))

    if profile_path is None:
        profile_path = find_rc_file()

    if not profile_path or not os.path.isfile(profile_path):
        return config

    try:
        ext = os.path.splitext(profile_path)[1].lower()
        if ext == '.json':
            loaded = _load_json(profile_path)
        else:
            loaded = _load_ini(profile_path)

        # Deep merge loaded values into defaults
        _deep_merge(config, loaded)
        logger.info(f"Loaded profile from: {profile_path}")
    except Exception as e:
        logger.warning(f"Failed to load profile '{profile_path}': {e}")

    return config


def save_profile(profile: Dict[str, Any], profile_path: str) -> None:
    """
    Save a profile to a config file.
    Supports .json and .ini formats based on file extension.
    """
    ext = os.path.splitext(profile_path)[1].lower()
    if ext == '.json':
        _save_json(profile, profile_path)
    else:
        _save_ini(profile, profile_path)
    logger.info(f"Saved profile to: {profile_path}")


def create_default_profile(profile_path: str) -> None:
    """Create a default profile file with comments/examples."""
    ext = os.path.splitext(profile_path)[1].lower()
    if ext == '.json':
        with open(profile_path, 'w') as f:
            json.dump(DEFAULT_PROFILE, f, indent=2)
    else:
        _save_ini(DEFAULT_PROFILE, profile_path)
    logger.info(f"Created default profile: {profile_path}")


def list_saved_profiles() -> List[Dict[str, Any]]:
    """List all available profiles from known locations."""
    profiles = []
    seen = set()

    for directory in [os.getcwd(), str(home_dir()), str(config_dir('bpm4b'))]:
        for fname in os.listdir(directory):
            if any(fname.endswith(ext) or fname == ext for ext in RC_FILENAMES):
                fpath = os.path.join(directory, fname)
                if fpath not in seen and os.path.isfile(fpath):
                    seen.add(fpath)
                    profiles.append({
                        'path': fpath,
                        'filename': fname,
                        'size': os.path.getsize(fpath),
                        'modified': os.path.getmtime(fpath),
                    })

    return profiles


# ─── Internal helpers ────────────────────────────────────────

def _load_json(path: str) -> Dict[str, Any]:
    with open(path, 'r') as f:
        return json.load(f)


def _load_ini(path: str) -> Dict[str, Any]:
    parser = configparser.ConfigParser()
    parser.read(path)
    config: Dict[str, Any] = {}
    for section in parser.sections():
        config[section] = {}
        for key, value in parser[section].items():
            # Try to interpret types
            config[section][key] = _parse_ini_value(value)
    return config


def _parse_ini_value(value: str) -> Any:
    """Parse INI values into appropriate types."""
    if value.lower() in ('true', 'yes', 'on'):
        return True
    if value.lower() in ('false', 'no', 'off'):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _save_json(profile: Dict[str, Any], path: str) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, 'w') as f:
        json.dump(profile, f, indent=2)


def _save_ini(profile: Dict[str, Any], path: str) -> None:
    ensure_dir(os.path.dirname(path))
    parser = configparser.ConfigParser()
    for section, values in profile.items():
        if isinstance(values, dict):
            parser[section] = {k: str(v) for k, v in values.items() if v is not None}
    with open(path, 'w') as f:
        parser.write(f)


def _deep_copy(d: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy a dictionary."""
    return json.loads(json.dumps(d))


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> None:
    """Deep merge overrides into base (modifies base in place)."""
    for key, value in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
