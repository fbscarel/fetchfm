#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mutagen>=1.47.0",
# ]
# ///
# Requires: mpv (for preview playback)
"""
Fetch top N songs for an artist and download them.

Uses Last.fm API (free, no auth required) to get top tracks by play count,
then downloads via spotdl or yt-dlp.

Features:
- Local database of existing songs (auto-updated on startup)
- Duplicate detection with fuzzy matching
- Preview tracks before downloading
- Interactive selection

Usage:
    uv run fetch_artist.py "Phil Collins"           # Search by artist (default)
    uv run fetch_artist.py -t "mpb"                 # Search by tag/genre
    uv run fetch_artist.py -s "Bohemian Rhapsody"   # Search by song title
    uv run fetch_artist.py "Basshunter" -n 20       # Fetch 20 results
    uv run fetch_artist.py "Basshunter" -y          # Download all without prompting
    uv run fetch_artist.py --rescan                 # Force rescan of local library
"""

import argparse
import curses
import difflib
import json
import re
import sqlite3
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from mutagen import File as MutagenFile

LASTFM_API_KEY = "8fc89f699e4ff45a21b968623a93ed52"  # Public demo key
LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
MUSIC_DIR = Path.home() / "Music"
DB_PATH = Path.home() / ".cache" / "fetch_artist" / "songs.db"
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".wma"}
SIMILARITY_THRESHOLD = 0.70


# =============================================================================
# String Normalization
# =============================================================================


def normalize_text(text: str) -> str:
    """Normalize text for fuzzy matching."""
    if not text:
        return ""
    text = text.lower()
    # Remove common suffixes in parentheses/brackets
    text = re.sub(
        r"\s*[\(\[].*?(radio|edit|remaster|live|version|remix|acoustic|"
        r"feat\.?|ft\.?|bonus|extended|single|album|original|official|"
        r"video|audio|hd|hq|\d{4}).*?[\)\]]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Remove " - Remastered YYYY" style suffixes
    text = re.sub(
        r"\s*[-–—]\s*(remaster|live|acoustic|remix|ao vivo|remasterizado).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Normalize unicode (é -> e)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Keep only alphanumeric and spaces
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse whitespace
    text = " ".join(text.split())
    return text


def similarity(s1: str, s2: str) -> float:
    """Calculate similarity ratio between two strings."""
    return difflib.SequenceMatcher(None, s1, s2).ratio()


# =============================================================================
# Local Song Database
# =============================================================================


class SongDatabase:
    """SQLite database for local music library."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                artist TEXT,
                artist_norm TEXT,
                title TEXT,
                title_norm TEXT,
                mtime REAL
            );
            CREATE INDEX IF NOT EXISTS idx_artist_norm ON songs(artist_norm);
            CREATE INDEX IF NOT EXISTS idx_path ON songs(path);
        """)
        self.conn.commit()

    def get_song_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]

    def get_all_paths(self) -> set[str]:
        rows = self.conn.execute("SELECT path FROM songs").fetchall()
        return {r[0] for r in rows}

    def add_song(self, path: str, artist: str, title: str, mtime: float):
        self.conn.execute(
            """INSERT OR REPLACE INTO songs
               (path, artist, artist_norm, title, title_norm, mtime)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (path, artist, normalize_text(artist), title, normalize_text(title), mtime),
        )

    def remove_missing(self, existing_paths: set[str]):
        """Remove entries for files that no longer exist."""
        db_paths = self.get_all_paths()
        missing = db_paths - existing_paths
        if missing:
            placeholders = ",".join("?" * len(missing))
            self.conn.execute(
                f"DELETE FROM songs WHERE path IN ({placeholders})",
                tuple(missing),
            )

    def commit(self):
        self.conn.commit()

    def find_match(self, artist: str, title: str) -> dict | None:
        """Find a local song matching artist and title (fuzzy)."""
        artist_norm = normalize_text(artist)
        title_norm = normalize_text(title)

        # Get all songs (could optimize with LIKE query first)
        rows = self.conn.execute(
            "SELECT path, artist, title, artist_norm, title_norm FROM songs"
        ).fetchall()

        best_match = None
        best_score = 0

        for row in rows:
            # Check artist similarity
            artist_sim = similarity(artist_norm, row["artist_norm"])
            if artist_sim < SIMILARITY_THRESHOLD:
                continue

            # Check title similarity
            title_sim = similarity(title_norm, row["title_norm"])
            if title_sim < SIMILARITY_THRESHOLD:
                continue

            # Combined score (weighted towards title match)
            score = artist_sim * 0.3 + title_sim * 0.7
            if score > best_score:
                best_score = score
                best_match = {
                    "path": row["path"],
                    "artist": row["artist"],
                    "title": row["title"],
                    "score": score,
                }

        return best_match

    def find_match_by_title(self, title: str, threshold: float = 0.80) -> dict | None:
        """Find a local song matching by title only (higher threshold)."""
        title_norm = normalize_text(title)

        rows = self.conn.execute(
            "SELECT path, artist, title, artist_norm, title_norm FROM songs"
        ).fetchall()

        best_match = None
        best_score = 0

        for row in rows:
            title_sim = similarity(title_norm, row["title_norm"])
            if title_sim < threshold:
                continue

            if title_sim > best_score:
                best_score = title_sim
                best_match = {
                    "path": row["path"],
                    "artist": row["artist"],
                    "title": row["title"],
                    "score": title_sim,
                }

        return best_match

    def close(self):
        self.conn.close()


def get_song_metadata(filepath: Path) -> tuple[str, str]:
    """Extract artist and title from audio file tags or filename."""
    artist, title = "", ""

    # Try reading tags
    try:
        audio = MutagenFile(filepath, easy=True)
        if audio:
            artist = (audio.get("artist") or audio.get("albumartist") or [""])[0]
            title = (audio.get("title") or [""])[0]
    except Exception:
        pass

    # Fallback to filename parsing
    if not title:
        name = filepath.stem
        # Remove leading track numbers
        name = re.sub(r"^\d+[\s.\-_]+", "", name)
        # Try "Artist - Title" pattern
        match = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", name)
        if match:
            if not artist:
                artist = match.group(1).strip()
            title = match.group(2).strip()
        else:
            title = name

    # Final fallback for artist: use parent directory name
    if not artist:
        artist = filepath.parent.name

    return artist, title


def scan_music_library(db: SongDatabase, music_dir: Path, force: bool = False) -> int:
    """Scan music directory and update database."""
    print("Scanning local music library...", end=" ", flush=True)

    # Find all audio files
    audio_files = []
    for ext in AUDIO_EXTENSIONS:
        audio_files.extend(music_dir.rglob(f"*{ext}"))
        audio_files.extend(music_dir.rglob(f"*{ext.upper()}"))

    existing_paths = {str(f) for f in audio_files}

    # Remove entries for deleted files
    db.remove_missing(existing_paths)

    # Get already indexed paths with their mtimes
    indexed = {}
    for row in db.conn.execute("SELECT path, mtime FROM songs").fetchall():
        indexed[row[0]] = row[1]

    # Add/update new or modified files
    added = 0
    for filepath in audio_files:
        path_str = str(filepath)
        mtime = filepath.stat().st_mtime

        # Skip if already indexed and not modified
        if not force and path_str in indexed and indexed[path_str] >= mtime:
            continue

        artist, title = get_song_metadata(filepath)
        db.add_song(path_str, artist, title, mtime)
        added += 1

    db.commit()
    total = db.get_song_count()
    print(f"done ({total} songs, {added} new/updated)")
    return total


# =============================================================================
# Last.fm API
# =============================================================================


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
            "local_match": None,  # Will be populated later
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
            "playcount": int(t.get("listeners", 0)),  # Use listeners as popularity
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


# =============================================================================
# Preview & Download
# =============================================================================


def preview_track(artist: str, track: str, duration: int = 30) -> None:
    """Play a preview snippet of a track using yt-dlp + mpv."""
    query = f"ytsearch1:{artist} {track} official audio"
    print(f"\n  ▶ Previewing: {artist} - {track}...")

    cmd = [
        "mpv",
        "--no-video",
        "--really-quiet",
        "--start=30",
        f"--length={duration}",
        f"ytdl://{query}",
    ]
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError:
        print("  Error: mpv not found. Install with: sudo pacman -S mpv")
    except KeyboardInterrupt:
        pass
    print()


def download_with_spotdl(artist: str, track: str, output_dir: Path) -> bool:
    """Download a track using spotdl."""
    query = f"{artist} - {track}"
    output_template = str(output_dir / "{artist} - {title}.{output-ext}")

    cmd = ["spotdl", query, "--output", output_template]
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def download_with_ytdlp(artist: str, track: str, output_dir: Path) -> bool:
    """Download a track using yt-dlp (fallback)."""
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


# =============================================================================
# Interactive Selection (curses TUI)
# =============================================================================


def interactive_select(tracks: list[dict], show_artist: bool = False) -> list[dict]:
    """Interactive multi-select menu using curses.

    Args:
        tracks: List of track dicts
        show_artist: If True, always show artist (for song title searches)
    """

    # Determine which tracks are local
    has_local = [bool(t.get("local_match")) for t in tracks]

    # Pre-select only non-local tracks
    selected = set(i for i, is_local in enumerate(has_local) if not is_local)

    def run_curses(stdscr) -> list[int]:
        """Curses main loop, returns selected indices."""
        nonlocal selected

        curses.curs_set(0)  # Hide cursor
        curses.use_default_colors()

        # Initialize color pairs
        curses.init_pair(1, curses.COLOR_GREEN, -1)  # Selected marker
        curses.init_pair(2, curses.COLOR_YELLOW, -1)  # Local match
        curses.init_pair(3, curses.COLOR_CYAN, -1)  # Header
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)  # Now playing

        cursor = 0
        scroll_offset = 0

        # Preview state
        preview_proc = None
        playing_idx = None

        def stop_preview():
            nonlocal preview_proc, playing_idx
            if preview_proc and preview_proc.poll() is None:
                preview_proc.terminate()
                try:
                    preview_proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    preview_proc.kill()
            preview_proc = None
            playing_idx = None

        def start_preview(idx):
            nonlocal preview_proc, playing_idx
            stop_preview()
            t = tracks[idx]
            query = f"ytsearch1:{t['artist']} {t['name']} official audio"
            cmd = [
                "mpv",
                "--no-video",
                "--really-quiet",
                "--start=30",
                "--length=30",
                f"ytdl://{query}",
            ]
            try:
                preview_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                playing_idx = idx
            except FileNotFoundError:
                pass  # mpv not installed

        while True:
            # Check if preview finished
            if preview_proc and preview_proc.poll() is not None:
                preview_proc = None
                playing_idx = None

            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Header
            header = "Select tracks to download"
            controls = "↑↓:move  SPACE:toggle  a:all  n:none  p:play/stop  ENTER:confirm  q:quit"
            stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
            stdscr.addstr(0, 0, header[: width - 1])
            stdscr.attroff(curses.color_pair(3) | curses.A_BOLD)
            stdscr.addstr(1, 0, controls[: width - 1])
            stdscr.addstr(2, 0, "─" * min(width - 1, 70))

            # Calculate visible area
            list_start = 3
            list_height = height - list_start - 1
            visible_count = min(list_height, len(tracks))

            # Adjust scroll to keep cursor visible
            if cursor < scroll_offset:
                scroll_offset = cursor
            elif cursor >= scroll_offset + visible_count:
                scroll_offset = cursor - visible_count + 1

            # Draw track list
            for i in range(visible_count):
                track_idx = scroll_offset + i
                if track_idx >= len(tracks):
                    break

                t = tracks[track_idx]
                is_selected = track_idx in selected
                is_local = has_local[track_idx]
                is_cursor = track_idx == cursor
                is_playing = track_idx == playing_idx

                # Build the line
                if is_playing:
                    marker = "▶  " if is_selected else "▶  "
                else:
                    marker = "[*]" if is_selected else "[ ]"

                name = t["name"][:35]
                if show_artist:
                    # Song title search: show artist and listeners
                    artist_str = t["artist"][:18]
                    listeners = t["playcount"] or 0
                    suffix = f"- {artist_str} ({listeners:,})"
                elif t["playcount"]:
                    suffix = f"({t['playcount']:,})"
                else:
                    suffix = f"- {t['artist'][:15]}"

                if is_local:
                    # Show album/folder name instead of title
                    local_path = Path(t["local_match"]["path"])
                    album = local_path.parent.name[:18]
                    line = f"{marker} {name:<36} {suffix:<20} [{album}]"
                else:
                    line = f"{marker} {name:<36} {suffix}"

                line = line[: width - 1]
                y = list_start + i

                # Apply styling
                if is_playing:
                    stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
                elif is_cursor:
                    stdscr.attron(curses.A_REVERSE)

                if is_local and not is_playing:
                    stdscr.attron(curses.A_DIM)

                if is_selected and not is_playing:
                    stdscr.attron(curses.color_pair(1))

                try:
                    stdscr.addstr(y, 0, line)
                except curses.error:
                    pass  # Ignore if line too long

                # Reset attributes
                stdscr.attroff(curses.A_REVERSE | curses.A_DIM | curses.A_BOLD)
                stdscr.attroff(curses.color_pair(1) | curses.color_pair(4))

            # Status bar
            if playing_idx is not None:
                playing_name = tracks[playing_idx]["name"][:30]
                status = (
                    f" ▶ {playing_name} | {len(selected)} selected | {cursor + 1}/{len(tracks)}"
                )
            else:
                status = f" {len(selected)} selected, {sum(has_local)} local | Track {cursor + 1}/{len(tracks)}"
            try:
                stdscr.addstr(height - 1, 0, status[: width - 1], curses.A_REVERSE)
            except curses.error:
                pass

            stdscr.refresh()

            # Handle input (non-blocking check for preview updates)
            stdscr.timeout(200)  # 200ms timeout for getch
            key = stdscr.getch()

            if key == -1:  # Timeout, no key pressed
                continue

            if key == ord("q") or key == 27:  # q or ESC
                stop_preview()
                return []
            elif key == curses.KEY_UP or key == ord("k"):
                cursor = max(0, cursor - 1)
            elif key == curses.KEY_DOWN or key == ord("j"):
                cursor = min(len(tracks) - 1, cursor + 1)
            elif key == curses.KEY_PPAGE:  # Page Up
                cursor = max(0, cursor - visible_count)
            elif key == curses.KEY_NPAGE:  # Page Down
                cursor = min(len(tracks) - 1, cursor + visible_count)
            elif key == curses.KEY_HOME:
                cursor = 0
            elif key == curses.KEY_END:
                cursor = len(tracks) - 1
            elif key == ord(" "):  # Space - toggle
                if cursor in selected:
                    selected.discard(cursor)
                else:
                    selected.add(cursor)
                cursor = min(len(tracks) - 1, cursor + 1)
            elif key == ord("a"):  # Select all
                selected = set(range(len(tracks)))
            elif key == ord("n"):  # Select none
                selected = set()
            elif key == ord("p"):  # Preview toggle
                if playing_idx == cursor:
                    # Stop if same track
                    stop_preview()
                else:
                    # Start preview of current track
                    start_preview(cursor)
            elif key == ord("s"):  # Stop preview
                stop_preview()
            elif key == ord("\n") or key == curses.KEY_ENTER:  # Enter
                stop_preview()
                return list(sorted(selected))

        return []

    # Run curses wrapper (handles init/cleanup)
    try:
        result = curses.wrapper(run_curses)
        return [tracks[i] for i in result]
    except KeyboardInterrupt:
        return []


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Download top N songs for an artist")
    parser.add_argument("query", nargs="?", help="Artist name, tag (-t), or song title (-s)")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "-t",
        "--tag",
        action="store_true",
        help="Search by tag/genre (e.g., 'mpb', 'rock', '80s')",
    )
    mode_group.add_argument(
        "-s",
        "--song",
        action="store_true",
        help="Search by song title",
    )
    parser.add_argument(
        "-n",
        "--number",
        type=int,
        default=15,
        help="Number of top tracks to fetch (default: 15)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: ~/Music/{Artist})",
    )
    parser.add_argument(
        "--backend",
        choices=["spotdl", "yt-dlp"],
        default="spotdl",
        help="Download backend (default: spotdl)",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip interactive selection, download all tracks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Just show tracks, don't download",
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Force full rescan of local music library",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip local database (no duplicate detection)",
    )
    args = parser.parse_args()

    # Handle rescan-only mode
    if args.rescan and not args.query:
        db = SongDatabase()
        scan_music_library(db, MUSIC_DIR, force=True)
        db.close()
        return

    if not args.query:
        parser.error("query is required (artist name or tag with -t)")

    # Initialize and update local database
    db = None
    if not args.no_db:
        db = SongDatabase()
        scan_music_library(db, MUSIC_DIR, force=args.rescan)

    # Get top tracks
    if args.tag:
        print(f"Fetching top {args.number} tracks for tag '{args.query}' from Last.fm...")
        tracks = get_top_tracks_by_tag(args.query, args.number)
    elif args.song:
        print(f"Searching for '{args.query}' by song title from Last.fm...")
        tracks = search_tracks_by_title(args.query, args.number)
    else:
        print(f"Fetching top {args.number} tracks for artist '{args.query}' from Last.fm...")
        tracks = get_top_tracks_by_artist(args.query, args.number)

    if not tracks:
        print("No tracks found!", file=sys.stderr)
        if db:
            db.close()
        sys.exit(1)

    # Check for local matches
    local_count = 0
    if db:
        print("Checking for local duplicates...", end=" ", flush=True)
        # For song title search, match by title only (ignores artist)
        local_count = check_local_matches(tracks, db, title_only=args.song)
        print(f"found {local_count} match(es)")
        db.close()

    print(f"\nFound {len(tracks)} tracks ({local_count} already local).")

    if args.dry_run or args.yes:
        print()
        for i, t in enumerate(tracks, 1):
            if args.song:
                # Song search: always show artist
                suffix = f"- {t['artist'][:20]} ({t['playcount'] or 0:,})"
            elif t["playcount"]:
                suffix = f"({t['playcount']:,} plays)"
            else:
                suffix = f"- {t['artist']}"
            local_marker = " [LOCAL]" if t["local_match"] else ""
            print(f"  {i:2}. {t['name']:<40} {suffix}{local_marker}")
        if args.dry_run:
            print("\n(Dry run - not downloading)")
            return

    # Interactive selection
    if not args.yes:
        tracks = interactive_select(tracks, show_artist=args.song)
        if not tracks:
            print("\nNo tracks selected. Exiting.")
            return
        print(f"\nSelected {len(tracks)} tracks for download.")

    # Setup output directory
    if args.output:
        output_dir = args.output
    elif args.tag:
        output_dir = MUSIC_DIR / args.query  # Use tag name as folder
    elif args.song:
        output_dir = MUSIC_DIR / tracks[0]["artist"]  # Use first result's artist
    else:
        output_dir = MUSIC_DIR / tracks[0]["artist"]
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nDownloading to: {output_dir}\n")

    # Download
    download_fn = download_with_spotdl if args.backend == "spotdl" else download_with_ytdlp

    success = 0
    failed = []
    for i, t in enumerate(tracks, 1):
        print(f"[{i}/{len(tracks)}] Downloading: {t['artist']} - {t['name']}")
        if download_fn(t["artist"], t["name"], output_dir):
            success += 1
        else:
            failed.append(t["name"])

    print(f"\nDone! {success}/{len(tracks)} downloaded successfully.")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
