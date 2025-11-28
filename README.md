# fetchfm

A command-line tool to download top tracks for any artist, tag, or song title. Features a curses-based TUI with audio preview, fuzzy duplicate detection, automatic playlist generation, and smart download fallback.

## Features

- **Search by artist, tag/genre, or song title** - Uses Last.fm API for track discovery
- **Interactive TUI** - Full-screen curses interface with vim-style navigation
- **Audio preview** - Press `p` to preview any track before downloading
- **Duplicate detection** - Fuzzy matching against your local library (SQLite database)
- **Multiple backends** - Download via spotdl (default) or yt-dlp
- **Smart download fallback** - Verifies Spotify matches before downloading; falls back to yt-dlp when Spotify returns wrong tracks
- **Playlist generation** - Auto-generate .m3u playlists based on Last.fm artist tags (rock, electronic, 80s, etc.)

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

### Downloading Music

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

### Playlist Generation

Generate thematic playlists for your entire music library based on Last.fm artist tags:

```bash
# Step 1: Enrich your library with Last.fm tags (run once, cached in database)
uv run fetchfm.py --enrich

# Step 2: Generate playlists
uv run fetchfm.py --playlists

# Or do both in one command
uv run fetchfm.py --enrich --playlists

# List available tags and artist counts
uv run fetchfm.py --list-tags

# Customize output
uv run fetchfm.py --playlists --playlist-dir ~/Music/MyPlaylists --max-playlists 50
```

This creates `.m3u` playlist files like `rock.m3u`, `electronic.m3u`, `80s.m3u` in `~/Music/Playlists/` (default).

**How it works:**
1. Scans your `~/Music` directory and indexes all audio files
2. Fetches tags for each artist from Last.fm's `artist.gettoptags` API
3. Handles collaboration suffixes (`feat.`, `part.`, `participação especial`, etc.) by extracting base artist
4. Generates playlists for the most popular tags across your library

### Using justfile

```bash
# Search shortcuts (handles spaces in queries)
just artist "Artist Name"
just tag "80s rock"
just song "song title"

# Playlist generation
just enrich                    # Fetch Last.fm tags for all artists
just playlists                 # Generate .m3u playlists
just playlists --max-playlists 50
just generate-playlists        # Enrich + generate in one step
just list-tags                 # Show available tags

# Library management
just rescan                    # Force rescan local library
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

### Track Discovery & Download

1. **Search** - Queries Last.fm API for top tracks
2. **Scan** - Builds/updates local SQLite database of your music library
3. **Match** - Fuzzy matches results against local files (70% similarity threshold)
4. **Select** - Interactive TUI with local duplicates dimmed
5. **Preview** - Stream audio via mpv + yt-dlp
6. **Verify** - Check Spotify match before downloading (artist ≥50%, title ≥50%)
7. **Download** - Fetch via spotdl, or fall back to yt-dlp if Spotify matched wrong track

### Playlist Generation

1. **Index** - Scan local music files, extract artist/title from tags or filenames
2. **Enrich** - Fetch Last.fm tags for each artist (cached in SQLite)
3. **Inherit** - Variant artists (e.g., "Artist feat. X") inherit tags from base artist
4. **Generate** - Create .m3u playlists for popular tags with ≥5 tracks

## CLI Reference

```
usage: fetchfm.py [-h] [-t | -s] [-n NUMBER] [-o OUTPUT] [--backend {spotdl,yt-dlp}]
                  [-y] [--dry-run] [--rescan] [--no-db] [--enrich] [--playlists]
                  [--list-tags] [--playlist-dir PLAYLIST_DIR] [--max-playlists MAX_PLAYLISTS]
                  [query]

positional arguments:
  query                 Artist name, tag (-t), or song title (-s)

search modes:
  -t, --tag             Search by tag/genre (e.g., 'rock', '80s')
  -s, --song            Search by song title

options:
  -n, --number NUMBER   Number of top tracks to fetch (default: 15)
  -o, --output OUTPUT   Output directory (default: ~/Music/{Artist})
  --backend {spotdl,yt-dlp}
                        Download backend (default: spotdl)
  -y, --yes             Skip interactive selection, download all tracks
  --dry-run             Just show tracks, don't download
  --rescan              Force full rescan of local music library
  --no-db               Skip local database (no duplicate detection)

playlist generation:
  --enrich              Fetch Last.fm tags for all artists in library
  --playlists           Generate playlists based on Last.fm tags
  --list-tags           List available tags and artist counts
  --playlist-dir PATH   Output directory for playlists (default: ~/Music/Playlists)
  --max-playlists N     Maximum number of playlists to generate (default: 100)
```

## Configuration

| Setting | Location | Description |
|---------|----------|-------------|
| Database | `~/.cache/fetchfm/songs.db` | Local song index and artist tags cache |
| Music directory | `~/Music` | Default scan/download location |
| Playlists | `~/Music/Playlists` | Default playlist output directory |

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
