"""Configuration constants for fetchfm."""

from pathlib import Path

# Last.fm API
LASTFM_API_KEY = "8fc89f699e4ff45a21b968623a93ed52"  # Public demo key
LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"

# Paths
MUSIC_DIR = Path.home() / "Music"
DB_PATH = Path.home() / ".cache" / "fetchfm" / "songs.db"

# Audio file extensions to scan
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".wma"}

# Fuzzy matching threshold (0.0 - 1.0)
SIMILARITY_THRESHOLD = 0.70
