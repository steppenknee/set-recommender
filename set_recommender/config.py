"""
Rekordbox DJ Set Recommender - Configuration & Cache Manager
Filename: set_recommender/config.py

This module initializes the application environment (under macOS-native standard Library paths or fallbacks),
manages CLI settings (config.json), caches resolved track metadata (cache.json), 
and securely retrieves Gemini API keys from environment variables or local configs.
Also handles automatic migration of existing settings and caches from ~/.rekordbox-recommender.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any

# Define macOS Native paths or fallback to standard XDG paths
if sys.platform == "darwin":
    CONFIG_DIR = Path.home() / "Library/Application Support/rekordbox-recommender"
    CACHE_DIR = Path.home() / "Library/Caches/rekordbox-recommender"
else:
    # Linux/Unix standard fallbacks (XDG Base Directory Specification)
    CONFIG_DIR = Path.home() / ".config/rekordbox-recommender"
    CACHE_DIR = Path.home() / ".cache/rekordbox-recommender"

CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_FILE = CACHE_DIR / "cache.json"

# Legacy directory definition for automatic migration
OLD_APP_DIR = Path.home() / ".rekordbox-recommender"
OLD_CONFIG_FILE = OLD_APP_DIR / "config.json"
OLD_CACHE_FILE = OLD_APP_DIR / "cache.json"

def ensure_app_dir():
    """
    Ensure the application configuration and cache directories exist.
    Also safely handles automatic migration from the legacy ~/.rekordbox-recommender directory.
    """
    # 1. Perform Migration if legacy directory exists
    if OLD_APP_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Move config.json to its new native directory
        if OLD_CONFIG_FILE.exists() and not CONFIG_FILE.exists():
            try:
                OLD_CONFIG_FILE.rename(CONFIG_FILE)
            except Exception:
                try:
                    # Fallback if partition boundary issues occur
                    CONFIG_FILE.write_text(OLD_CONFIG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
                    OLD_CONFIG_FILE.unlink()
                except Exception:
                    pass
                    
        # Move cache.json to its new native directory
        if OLD_CACHE_FILE.exists() and not CACHE_FILE.exists():
            try:
                OLD_CACHE_FILE.rename(CACHE_FILE)
            except Exception:
                try:
                    # Fallback if partition boundary issues occur
                    CACHE_FILE.write_text(OLD_CACHE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
                    OLD_CACHE_FILE.unlink()
                except Exception:
                    pass
                    
        # Clean up old directory if empty or containing only standard leftover dotfiles
        try:
            for item in OLD_APP_DIR.glob("*"):
                if item.is_file():
                    item.unlink()
            OLD_APP_DIR.rmdir()
        except Exception:
            pass

    # 2. Ensure both target directories exist
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def load_config() -> Dict[str, Any]:
    """
    Load user configuration profiles from config.json.
    
    Returns:
        Dict[str, Any]: Key-value configuration mappings. Returns an empty dict
                        if the file does not exist or fails to parse.
    """
    ensure_app_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_config(config: Dict[str, Any]):
    """
    Persist configuration parameters to config.json.
    
    Args:
        config (Dict[str, Any]): Dictionary of configuration parameters to save.
    """
    ensure_app_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def get_api_key(override_key: str = None) -> str:
    """
    Retrieve the Gemini API key from standard storage options in order of precedence:
    1. CLI argument override
    2. GEMINI_API_KEY environment variable
    3. Stored parameter in native config.json
    
    Args:
        override_key (str, optional): Key provided directly in CLI arguments.
        
    Returns:
        str: Resolved API key, or an empty string if not found.
    """
    if override_key:
        return override_key
    
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key
        
    config = load_config()
    return config.get("GEMINI_API_KEY", "")

def load_cache() -> Dict[str, Any]:
    """
    Load the resolved track style/energy metadata database from cache.json.
    
    Returns:
        Dict[str, Any]: A mapping of track hashes to style/energy metadata profiles.
    """
    ensure_app_dir()
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache: Dict[str, Any]):
    """
    Persist the updated track style/energy metadata database to cache.json.
    
    Args:
        cache (Dict[str, Any]): The track metadata dictionary to persist.
    """
    ensure_app_dir()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
