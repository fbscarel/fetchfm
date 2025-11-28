"""Last.fm API functions."""

import json
import sys
import urllib.parse
import urllib.request

from .config import LASTFM_API_KEY, LASTFM_API_URL
from .db import SongDatabase


def get_top_tracks_by_artist(artist: str, limit: int = 20) -> list[dict]:
    """Fetch top tracks for an artist from Last.fm API."""
    params = {
        "method": "artist.gettoptracks",
        "artist": artist,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit,
    }
    url = f"{LASTFM_API_URL}?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching from Last.fm: {e}", file=sys.stderr)
        return []

    if "error" in data:
        print(
            f"Last.fm API error: {data.get('message', 'Unknown error')}",
            file=sys.stderr,
        )
        return []

    tracks = data.get("toptracks", {}).get("track", [])
    return [
        {
            "name": t["name"],
            "artist": t["artist"]["name"],
            "playcount": int(t.get("playcount", 0)),
            "local_match": None,
        }
        for t in tracks
    ]


def get_top_tracks_by_tag(tag: str, limit: int = 20) -> list[dict]:
    """Fetch top tracks for a tag/genre from Last.fm API."""
    params = {
        "method": "tag.gettoptracks",
        "tag": tag,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit,
    }
    url = f"{LASTFM_API_URL}?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching from Last.fm: {e}", file=sys.stderr)
        return []

    if "error" in data:
        print(
            f"Last.fm API error: {data.get('message', 'Unknown error')}",
            file=sys.stderr,
        )
        return []

    tracks = data.get("tracks", {}).get("track", [])
    return [
        {
            "name": t["name"],
            "artist": t["artist"]["name"],
            "playcount": None,
            "local_match": None,
        }
        for t in tracks
    ]


def search_tracks_by_title(title: str, limit: int = 20) -> list[dict]:
    """Search for tracks by title from Last.fm API."""
    params = {
        "method": "track.search",
        "track": title,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit,
    }
    url = f"{LASTFM_API_URL}?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching from Last.fm: {e}", file=sys.stderr)
        return []

    if "error" in data:
        print(
            f"Last.fm API error: {data.get('message', 'Unknown error')}",
            file=sys.stderr,
        )
        return []

    tracks = data.get("results", {}).get("trackmatches", {}).get("track", [])
    return [
        {
            "name": t["name"],
            "artist": t["artist"],
            "playcount": int(t.get("listeners", 0)),
            "local_match": None,
        }
        for t in tracks
    ]


def check_local_matches(tracks: list[dict], db: SongDatabase, title_only: bool = False) -> int:
    """Check tracks against local database, return number of matches.

    Args:
        tracks: List of track dicts to check
        db: Song database
        title_only: If True, match by title only (for song title searches)
    """
    matches = 0
    for t in tracks:
        if title_only:
            match = db.find_match_by_title(t["name"])
        else:
            match = db.find_match(t["artist"], t["name"])
        if match:
            t["local_match"] = match
            matches += 1
    return matches
