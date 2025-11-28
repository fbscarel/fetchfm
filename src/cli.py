"""Command-line interface and main orchestration."""

import argparse
import sys
from pathlib import Path

from .config import MUSIC_DIR
from .db import SongDatabase, scan_music_library
from .download import download_with_spotdl, download_with_ytdlp
from .lastfm import (
    check_local_matches,
    get_top_tracks_by_artist,
    get_top_tracks_by_tag,
    search_tracks_by_title,
)
from .tui import interactive_select


def main():
    parser = argparse.ArgumentParser(description="Download top N songs for an artist")
    parser.add_argument("query", nargs="?", help="Artist name, tag (-t), or song title (-s)")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "-t",
        "--tag",
        action="store_true",
        help="Search by tag/genre (e.g., 'rock', '80s')",
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
        local_count = check_local_matches(tracks, db, title_only=args.song)
        print(f"found {local_count} match(es)")
        db.close()

    print(f"\nFound {len(tracks)} tracks ({local_count} already local).")

    if args.dry_run or args.yes:
        print()
        for i, t in enumerate(tracks, 1):
            if args.song:
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
        output_dir = MUSIC_DIR / args.query
    elif args.song:
        output_dir = MUSIC_DIR / tracks[0]["artist"]
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
