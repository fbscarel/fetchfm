"""Curses-based TUI for track selection."""

import curses
import subprocess
from pathlib import Path


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
                    stop_preview()
                else:
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
