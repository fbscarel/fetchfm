"""Playlist generation using Last.fm tags.

This module provides functionality to:
1. Enrich local songs with Last.fm tags
2. Generate thematic playlists based on tags
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

from .config import LASTFM_API_KEY, LASTFM_API_URL, MUSIC_DIR
from .db import SongDatabase


def get_track_tags(artist: str, title: str) -> list[str]:
    """Fetch tags for a track from Last.fm API."""
    params = {
        "method": "track.gettoptags",
        "artist": artist,
        "track": title,
        "api_key": LASTFM_API_KEY,
        "format": "json",
    }
    url = f"{LASTFM_API_URL}?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception:
        return []

    if "error" in data:
        return []

    tags = data.get("toptags", {}).get("tag", [])
    # Return tag names, sorted by count (most popular first)
    return [t["name"].lower() for t in tags if int(t.get("count", 0)) > 0]


def enrich_database_with_tags(db: SongDatabase) -> int:
    """Fetch Last.fm tags for all songs in the database.

    Returns number of songs enriched.
    """
    # TODO: Add 'tags' column to database schema
    # TODO: Iterate through songs, fetch tags, store in DB
    # TODO: Rate limiting to avoid API throttling
    raise NotImplementedError("Tag enrichment not yet implemented")


def generate_playlist(
    db: SongDatabase,
    theme: str,
    output_path: Path,
    max_tracks: int = 50,
) -> int:
    """Generate a .m3u playlist based on theme/tags.

    Args:
        db: Song database with tags
        theme: Theme to match (e.g., "chill", "workout", "80s")
        output_path: Path to write .m3u file
        max_tracks: Maximum tracks in playlist

    Returns:
        Number of tracks in generated playlist
    """
    # TODO: Query songs by tag match
    # TODO: Sort by relevance
    # TODO: Write .m3u file with relative paths
    raise NotImplementedError("Playlist generation not yet implemented")


def generate_all_playlists(
    db: SongDatabase,
    output_dir: Path = MUSIC_DIR / "Playlists",
    themes: list[str] | None = None,
) -> dict[str, int]:
    """Generate multiple themed playlists.

    Args:
        db: Song database with tags
        output_dir: Directory for playlist files
        themes: List of themes, or None for auto-detection

    Returns:
        Dict mapping theme name to track count
    """
    # TODO: Auto-detect popular tags if themes not provided
    # TODO: Generate playlist for each theme
    raise NotImplementedError("Bulk playlist generation not yet implemented")
