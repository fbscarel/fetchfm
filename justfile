set shell := ["bash", "-uc"]

# Default recipe - show help
default:
    @just --list

# Install dependencies
install:
    uv sync

# Install with dev dependencies
install-dev:
    uv sync --all-extras

# Run fetchfm with arguments (use specific recipes below for queries with spaces)
run *ARGS:
    uv run python fetchfm.py {{ARGS}}

# Search by artist name
artist QUERY *ARGS:
    uv run python fetchfm.py "{{QUERY}}" {{ARGS}}

# Search by tag/genre
tag QUERY *ARGS:
    uv run python fetchfm.py -t "{{QUERY}}" {{ARGS}}

# Search by song title
song QUERY *ARGS:
    uv run python fetchfm.py -s "{{QUERY}}" {{ARGS}}

# Format code
fmt:
    uv run ruff format .
    uv run ruff check . --fix

# Lint code
lint:
    uv run ruff check .

# Format check (CI)
fmt-check:
    uv run ruff format . --check
    uv run ruff check .

# Run tests
test:
    uv run pytest -v

# Check system dependencies
check:
    @echo "=== System Dependencies ==="
    @echo ""
    @echo -n "Python: "
    @python3 --version 2>/dev/null || echo "Not found"
    @echo -n "mpv: "
    @mpv --version 2>/dev/null | head -n1 || echo "Not found (needed for preview)"
    @echo -n "yt-dlp: "
    @yt-dlp --version 2>/dev/null || echo "Not found (optional backend)"
    @echo -n "spotdl: "
    @spotdl --version 2>/dev/null || echo "Not found (default backend)"
    @echo ""
    @echo "Install missing dependencies:"
    @echo "  macOS:   brew install mpv yt-dlp"
    @echo "  Ubuntu:  sudo apt install mpv && pip install yt-dlp spotdl"
    @echo "  Arch:    sudo pacman -S mpv yt-dlp && pip install spotdl"

# Clean cache and build artifacts
clean:
    rm -rf __pycache__ .pytest_cache .ruff_cache
    rm -rf dist build *.egg-info
    rm -rf ~/.cache/fetchfm

# Force rescan local music library
rescan:
    uv run python fetchfm.py --rescan
