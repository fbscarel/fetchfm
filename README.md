# fetchfm

A command-line tool to download top tracks for any artist, tag, or song title. Features a curses-based TUI with audio preview, fuzzy duplicate detection, and multiple search modes.

## Features

- **Search by artist, tag/genre, or song title** - Uses Last.fm API for track discovery
- **Interactive TUI** - Full-screen curses interface like htop
- **Audio preview** - Press `p` to preview any track before downloading
- **Duplicate detection** - Fuzzy matching against your local library (SQLite database)
- **Multiple backends** - Download via spotdl (default) or yt-dlp

## Installation

### Prerequisites

You'll need these system dependencies:

| Dependency | Purpose | Installation |
|------------|---------|--------------|
| **mpv** | Audio preview | `brew install mpv` / `apt install mpv` / `pacman -S mpv` |
| **spotdl** | Download backend (default) | `pip install spotdl` |
| **yt-dlp** | Download backend (alternative) | `pip install yt-dlp` or system package |

### Install fetchfm

```bash
# Clone the repository
git clone https://github.com/fbscarel/fetchfm.git
cd fetchfm

# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

## Usage

```bash
# Search by artist (default)
uv run fetchfm.py "Artist Name"

# Search by tag/genre
uv run fetchfm.py -t "80s rock"
uv run fetchfm.py -t "brazilian jazz" -n 30

# Search by song title
uv run fetchfm.py -s "song title"

# Non-interactive mode (skip selection, download all)
uv run fetchfm.py "Artist Name" -y

# Use yt-dlp instead of spotdl
uv run fetchfm.py "Artist Name" --backend yt-dlp

# Dry run (show tracks without downloading)
uv run fetchfm.py "Artist Name" --dry-run

# Force rescan local library
uv run fetchfm.py --rescan
```

## TUI Controls

| Key | Action |
|-----|--------|
| `↑`/`↓` or `j`/`k` | Navigate |
| `Space` | Toggle selection |
| `a` | Select all |
| `n` | Select none |
| `p` | Preview track (plays 30s snippet) |
| `s` | Stop preview |
| `Enter` | Confirm and download |
| `q` / `Esc` | Quit |
| `PgUp`/`PgDn` | Page navigation |

## How It Works

1. **Search** - Queries Last.fm API for top tracks
2. **Scan** - Builds/updates local SQLite database of your music library
3. **Match** - Fuzzy matches results against local files (70% similarity threshold)
4. **Select** - Interactive TUI with local duplicates dimmed
5. **Preview** - Stream audio via mpv + yt-dlp
6. **Download** - Fetch selected tracks via spotdl or yt-dlp

## Configuration

The local database is stored at `~/.cache/fetchfm/songs.db`.

Music is downloaded to `~/Music/{Artist}/` by default. Override with `-o`:

```bash
uv run fetchfm.py "Artist" -o /path/to/music
```

## Development

```bash
# Install dev dependencies
just install-dev

# Format code
just fmt

# Lint
just lint

# Run tests
just test

# Check system dependencies
just check
```

## License

MIT
