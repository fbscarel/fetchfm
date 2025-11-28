"""Download backends (spotdl, yt-dlp) with match verification."""

import json
import subprocess
import tempfile
from pathlib import Path

from .utils import normalize_text, similarity

# Similarity thresholds for match verification
ARTIST_THRESHOLD = 0.5
TITLE_THRESHOLD = 0.5
TITLE_HIGH_THRESHOLD = 0.8  # Very good title match can skip artist check


def get_spotdl_match(query: str) -> dict | None:
    """Get what spotdl would match for a query without downloading.

    Uses 'spotdl save' to get Spotify match metadata.

    Returns:
        Dict with 'artist', 'name', 'url' keys, or None if not found.
    """
    try:
        fd, temp_file = tempfile.mkstemp(suffix=".spotdl")
        import os

        os.close(fd)
    except Exception:
        return None

    try:
        cmd = ["spotdl", "save", query, "--save-file", temp_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        with open(temp_file, encoding="utf-8") as f:
            data = json.load(f)

        if not data or len(data) == 0:
            return None

        track = data[0]

        # Handle both 'artist' (string) and 'artists' (list) fields
        artist = track.get("artist", "")
        if not artist and track.get("artists"):
            artists = track["artists"]
            artist = artists[0] if isinstance(artists, list) else artists

        return {
            "artist": artist,
            "name": track.get("name", ""),
            "url": track.get("url", ""),
        }

    except subprocess.TimeoutExpired:
        return None
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return None
    except Exception:
        return None
    finally:
        try:
            Path(temp_file).unlink(missing_ok=True)
        except Exception:
            pass


def is_good_match(
    req_artist: str,
    req_title: str,
    match_artist: str,
    match_title: str,
) -> tuple[bool, float, float]:
    """Check if matched track is close enough to requested track.

    Returns:
        Tuple of (is_match, artist_similarity, title_similarity)
    """
    req_artist_norm = normalize_text(req_artist)
    req_title_norm = normalize_text(req_title)
    match_artist_norm = normalize_text(match_artist)
    match_title_norm = normalize_text(match_title)

    artist_sim = similarity(req_artist_norm, match_artist_norm)
    title_sim = similarity(req_title_norm, match_title_norm)

    # Good match if both artist and title are reasonable
    if artist_sim >= ARTIST_THRESHOLD and title_sim >= TITLE_THRESHOLD:
        return True, artist_sim, title_sim

    # Also accept if title is an excellent match
    # (handles cases where artist name might differ between services)
    if title_sim >= TITLE_HIGH_THRESHOLD:
        return True, artist_sim, title_sim

    return False, artist_sim, title_sim


def download_with_spotdl(artist: str, track: str, output_dir: Path) -> bool:
    """Download a track using spotdl with pre-verification.

    First checks what Spotify track spotdl would match. If the match
    seems wrong (low artist/title similarity), falls back to yt-dlp.
    """
    query = f"{artist} - {track}"

    # First, check what spotdl would match
    match = get_spotdl_match(query)

    if match and match.get("url"):
        is_match, artist_sim, title_sim = is_good_match(
            artist, track, match["artist"], match["name"]
        )

        if is_match:
            # Good match - download using the Spotify URL directly
            output_template = str(output_dir / "{artist} - {title}.{output-ext}")
            cmd = ["spotdl", match["url"], "--output", output_template]
            result = subprocess.run(cmd, capture_output=False)
            return result.returncode == 0
        else:
            # Bad match - Spotify returned wrong track
            print(
                f"  spotdl matched: {match['artist']} - {match['name']} "
                f"(artist={artist_sim:.0%}, title={title_sim:.0%})"
            )
            print("  Falling back to yt-dlp...")
            return download_with_ytdlp(artist, track, output_dir)

    # No match found at all
    print("  spotdl: no Spotify match, trying yt-dlp...")
    return download_with_ytdlp(artist, track, output_dir)


def download_with_ytdlp(artist: str, track: str, output_dir: Path) -> bool:
    """Download a track using yt-dlp (YouTube search)."""
    query = f"ytsearch1:{artist} {track} official audio"
    output_template = str(output_dir / f"{artist} - {track}.%(ext)s")

    cmd = [
        "yt-dlp",
        query,
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        output_template,
        "--no-playlist",
    ]
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0
