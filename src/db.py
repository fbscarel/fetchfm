"""Local music database management."""

import re
import sqlite3
from pathlib import Path

from mutagen import File as MutagenFile

from .config import AUDIO_EXTENSIONS, DB_PATH, SIMILARITY_THRESHOLD
from .utils import normalize_text, similarity


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

            CREATE TABLE IF NOT EXISTS artist_tags (
                artist_norm TEXT PRIMARY KEY,
                artist TEXT,
                tags TEXT,
                fetched_at REAL
            );
        """)
        self.conn.commit()

    def get_song_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]

    def get_all_paths(self) -> set[str]:
        rows = self.conn.execute("SELECT path FROM songs").fetchall()
        return {r[0] for r in rows}

    def get_all_songs(self) -> list[dict]:
        """Get all songs from the database."""
        rows = self.conn.execute(
            "SELECT path, artist, title, artist_norm, title_norm FROM songs"
        ).fetchall()
        return [dict(row) for row in rows]

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

        rows = self.conn.execute(
            "SELECT path, artist, title, artist_norm, title_norm FROM songs"
        ).fetchall()

        best_match = None
        best_score = 0

        for row in rows:
            artist_sim = similarity(artist_norm, row["artist_norm"])
            if artist_sim < SIMILARITY_THRESHOLD:
                continue

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

    # =========================================================================
    # Artist Tags
    # =========================================================================

    def get_unique_artists(self) -> list[tuple[str, str]]:
        """Get unique artists from songs table.

        Returns list of (artist_norm, artist) tuples.
        """
        rows = self.conn.execute(
            "SELECT DISTINCT artist_norm, artist FROM songs WHERE artist_norm != ''"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def get_artist_tags(self, artist_norm: str) -> list[str] | None:
        """Get cached tags for an artist, or None if not cached."""
        row = self.conn.execute(
            "SELECT tags FROM artist_tags WHERE artist_norm = ?", (artist_norm,)
        ).fetchone()
        if row and row[0]:
            import json

            return json.loads(row[0])
        return None

    def set_artist_tags(self, artist_norm: str, artist: str, tags: list[str]):
        """Cache tags for an artist."""
        import json
        import time

        self.conn.execute(
            """INSERT OR REPLACE INTO artist_tags (artist_norm, artist, tags, fetched_at)
               VALUES (?, ?, ?, ?)""",
            (artist_norm, artist, json.dumps(tags), time.time()),
        )

    def get_all_artist_tags(self) -> dict[str, list[str]]:
        """Get all cached artist tags.

        Returns dict mapping artist_norm -> list of tags.
        """
        import json

        rows = self.conn.execute("SELECT artist_norm, tags FROM artist_tags").fetchall()
        return {r[0]: json.loads(r[1]) if r[1] else [] for r in rows}

    def get_artists_by_tag(self, tag: str) -> list[str]:
        """Get all artist_norm values that have a specific tag."""
        import json

        rows = self.conn.execute("SELECT artist_norm, tags FROM artist_tags").fetchall()
        matching = []
        tag_lower = tag.lower()
        for r in rows:
            if r[1]:
                tags = json.loads(r[1])
                if any(t.lower() == tag_lower for t in tags):
                    matching.append(r[0])
        return matching

    def get_songs_by_artist_norm(self, artist_norms: list[str]) -> list[dict]:
        """Get all songs for a list of normalized artist names."""
        if not artist_norms:
            return []
        placeholders = ",".join("?" * len(artist_norms))
        rows = self.conn.execute(
            f"SELECT path, artist, title FROM songs WHERE artist_norm IN ({placeholders})",
            tuple(artist_norms),
        ).fetchall()
        return [dict(row) for row in rows]

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
