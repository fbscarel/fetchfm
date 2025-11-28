"""Download backends (spotdl, yt-dlp)."""

import subprocess
from pathlib import Path


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
