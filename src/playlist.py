"""Playlist generation using Last.fm artist tags.

This module provides functionality to:
1. Enrich local songs with Last.fm artist tags
2. Generate thematic playlists based on tags
"""

import json
import os
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from .config import LASTFM_API_KEY, LASTFM_API_URL, MUSIC_DIR
from .db import SongDatabase
from .utils import extract_base_artist, normalize_text

# Tags to ignore (not useful for playlists)
TAG_BLACKLIST = {
    "seen live",
    "favorites",
    "favourite",
    "favorite",
    "my music",
    "love",
    "loved",
    "amazing",
    "awesome",
    "beautiful",
    "best",
    "classic",
    "good",
    "great",
    "under 2000 listeners",
}

# Minimum tag count to be considered significant
MIN_TAG_COUNT = 10


def get_artist_tags_from_lastfm(artist: str) -> list[str]:
    """Fetch top tags for an artist from Last.fm API.

    Returns list of tag names (lowercase), sorted by popularity.
    """
    params = {
        "method": "artist.gettoptags",
        "artist": artist,
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

    # Filter and normalize tags
    result = []
    artist_norm = normalize_text(artist)

    for t in tags:
        name = t.get("name", "").lower().strip()
        count = int(t.get("count", 0))

        # Skip low-count tags
        if count < MIN_TAG_COUNT:
            continue

        # Skip blacklisted tags
        if name in TAG_BLACKLIST:
            continue

        # Skip tags that are just the artist name
        if normalize_text(name) == artist_norm:
            continue

        result.append(name)

    return result


def find_cached_tags_for_artist(
    artist: str, artist_norm: str, cached_artists: dict[str, list[str]]
) -> list[str] | None:
    """Try to find cached tags for an artist using various strategies.

    Strategies (in order):
    1. Exact match on normalized name
    2. Base artist extraction (remove "feat.", "part.", etc.)
    3. Prefix matching (artist starts with a cached artist name)

    Args:
        artist: Original artist name
        artist_norm: Normalized artist name
        cached_artists: Dict of artist_norm -> tags for already cached artists

    Returns:
        List of tags if found, None otherwise
    """
    # Strategy 1: Exact match (already in cache)
    if artist_norm in cached_artists:
        return cached_artists[artist_norm]

    # Strategy 2: Base artist extraction
    base_artist = extract_base_artist(artist)
    base_norm = normalize_text(base_artist)

    if base_norm != artist_norm and base_norm in cached_artists:
        tags = cached_artists[base_norm]
        if tags:  # Only inherit non-empty tags
            return tags

    # Strategy 3: Prefix matching - check if this artist starts with a known artist
    # Sort by length descending to match longest prefix first
    for cached_norm, tags in sorted(cached_artists.items(), key=lambda x: -len(x[0])):
        if not tags:  # Skip artists with no tags
            continue
        if len(cached_norm) < 3:  # Skip very short names
            continue
        if artist_norm.startswith(cached_norm + " "):
            return tags

    return None


def enrich_database_with_tags(db: SongDatabase, force: bool = False) -> int:
    """Fetch Last.fm tags for all artists in the database.

    Uses multiple strategies to maximize tag coverage:
    1. Direct API lookup
    2. Base artist extraction (strip "feat.", "part.", etc.)
    3. Cache inheritance from similar artists

    Args:
        db: Song database
        force: If True, re-fetch even if already cached

    Returns:
        Number of artists enriched
    """
    artists = db.get_unique_artists()
    print(f"Found {len(artists)} unique artists")

    # Build initial cache of already-fetched artists
    cached_artists = db.get_all_artist_tags()

    enriched = 0
    skipped = 0
    inherited = 0
    failed = 0

    for i, (artist_norm, artist) in enumerate(artists):
        # Check if already cached
        if not force and artist_norm in cached_artists:
            skipped += 1
            continue

        # Try to inherit from cache first (no API call needed)
        inherited_tags = find_cached_tags_for_artist(artist, artist_norm, cached_artists)
        if inherited_tags:
            db.set_artist_tags(artist_norm, artist, inherited_tags)
            cached_artists[artist_norm] = inherited_tags  # Update local cache
            print(f"  [{i + 1}/{len(artists)}] {artist}: inherited {len(inherited_tags)} tags")
            inherited += 1
            db.commit()
            continue

        # Try base artist for API lookup
        base_artist = extract_base_artist(artist)
        lookup_artist = base_artist if base_artist != artist else artist

        print(
            f"  [{i + 1}/{len(artists)}] Fetching tags for: {lookup_artist}...", end=" ", flush=True
        )

        tags = get_artist_tags_from_lastfm(lookup_artist)

        # If base artist lookup failed but it's different, try original
        if not tags and lookup_artist != artist:
            print("trying full name...", end=" ", flush=True)
            tags = get_artist_tags_from_lastfm(artist)
            time.sleep(0.25)  # Extra rate limiting for second request

        if tags:
            db.set_artist_tags(artist_norm, artist, tags)
            cached_artists[artist_norm] = tags  # Update local cache

            # Also cache the base artist if different
            base_norm = normalize_text(base_artist)
            if base_norm != artist_norm and base_norm not in cached_artists:
                db.set_artist_tags(base_norm, base_artist, tags)
                cached_artists[base_norm] = tags

            print(f"{len(tags)} tags")
            enriched += 1
        else:
            # Store empty list to mark as "attempted"
            db.set_artist_tags(artist_norm, artist, [])
            cached_artists[artist_norm] = []
            print("no tags found")
            failed += 1

        db.commit()

        # Rate limiting: Last.fm allows 5 req/sec
        time.sleep(0.25)

    print(
        f"\nDone! Enriched: {enriched}, Inherited: {inherited}, Skipped: {skipped}, No tags: {failed}"
    )
    return enriched + inherited


def get_tag_frequencies(db: SongDatabase) -> Counter:
    """Get frequency of each tag across all artists.

    Returns Counter mapping tag -> number of artists with that tag.
    """
    all_tags = db.get_all_artist_tags()
    counter: Counter = Counter()

    for tags in all_tags.values():
        for tag in tags:
            counter[tag.lower()] += 1

    return counter


def generate_playlist(
    db: SongDatabase,
    tag: str,
    output_path: Path,
    music_dir: Path = MUSIC_DIR,
) -> int:
    """Generate a .m3u playlist for songs matching a tag.

    Args:
        db: Song database with tags
        tag: Tag to match (e.g., "electronic", "80s")
        output_path: Path to write .m3u file
        music_dir: Base music directory (for relative paths)

    Returns:
        Number of tracks in generated playlist
    """
    # Find artists with this tag
    artist_norms = db.get_artists_by_tag(tag)
    if not artist_norms:
        return 0

    # Get songs by those artists
    songs = db.get_songs_by_artist_norm(artist_norms)
    if not songs:
        return 0

    # Sort by artist, then title
    songs.sort(key=lambda s: (s["artist"].lower(), s["title"].lower()))

    # Write .m3u file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# Playlist: {tag}\n")
        f.write("# Generated by fetchfm\n")
        f.write(f"# {len(songs)} tracks\n\n")

        for song in songs:
            # Calculate path relative to playlist file location
            song_path = Path(song["path"])
            rel_path = os.path.relpath(song_path, output_path.parent)

            f.write(f"#EXTINF:-1,{song['artist']} - {song['title']}\n")
            f.write(f"{rel_path}\n")

    return len(songs)


def generate_all_playlists(
    db: SongDatabase,
    output_dir: Path | None = None,
    min_songs: int = 5,
    max_playlists: int = 100,
) -> dict[str, int]:
    """Generate playlists for the most popular tags.

    Args:
        db: Song database with tags
        output_dir: Directory for playlist files (default: ~/Music/Playlists)
        min_songs: Minimum songs required to create a playlist
        max_playlists: Maximum number of playlists to generate

    Returns:
        Dict mapping tag name to track count
    """
    if output_dir is None:
        output_dir = MUSIC_DIR / "Playlists"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Get tag frequencies
    tag_freq = get_tag_frequencies(db)

    if not tag_freq:
        print("No tags found. Run --enrich first.")
        return {}

    # Sort by frequency
    popular_tags = tag_freq.most_common(max_playlists * 2)  # Get extra in case some are empty

    print(f"Generating playlists in: {output_dir}")
    results = {}

    for tag, _freq in popular_tags:
        if len(results) >= max_playlists:
            break

        # Skip very generic single-letter tags
        if len(tag) < 2:
            continue

        # Generate playlist
        safe_name = tag.replace("/", "-").replace("\\", "-")
        output_path = output_dir / f"{safe_name}.m3u"

        count = generate_playlist(db, tag, output_path, MUSIC_DIR)

        if count >= min_songs:
            print(f"  {tag}: {count} tracks")
            results[tag] = count
        elif output_path.exists():
            # Remove playlist if too few songs
            output_path.unlink()

    print(f"\nGenerated {len(results)} playlists")
    return results


def list_available_tags(db: SongDatabase, min_artists: int = 2) -> list[tuple[str, int]]:
    """List all available tags with their artist counts.

    Args:
        db: Song database with tags
        min_artists: Minimum number of artists for a tag to be listed

    Returns:
        List of (tag, artist_count) tuples, sorted by count descending
    """
    tag_freq = get_tag_frequencies(db)
    return [(tag, count) for tag, count in tag_freq.most_common() if count >= min_artists]
