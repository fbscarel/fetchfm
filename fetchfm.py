#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mutagen>=1.47.0",
# ]
# ///
"""
fetchfm - Download top tracks for any artist, tag, or song title.

Uses Last.fm API (free, no auth required) to get top tracks by play count,
then downloads via spotdl or yt-dlp.

Features:
- Local database of existing songs (auto-updated on startup)
- Duplicate detection with fuzzy matching
- Preview tracks before downloading
- Interactive selection

Usage:
    uv run fetchfm.py "Artist Name"           # Search by artist (default)
    uv run fetchfm.py -t "80s rock"           # Search by tag/genre
    uv run fetchfm.py -s "song title"         # Search by song title
    uv run fetchfm.py "Artist Name" -n 20     # Fetch 20 results
    uv run fetchfm.py "Artist Name" -y        # Download all without prompting
    uv run fetchfm.py --rescan                # Force rescan of local library
"""

from src.cli import main

if __name__ == "__main__":
    main()
