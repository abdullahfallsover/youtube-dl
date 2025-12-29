# coding: utf-8
from __future__ import unicode_literals

import datetime
import json
import os
import subprocess
import sys

from .compat import (
    compat_str,
)
from .utils import (
    encodeFilename,
    sanitize_filename,
    write_json_file,
)


MANIFEST_FILENAME = '.offline_manifest.json'
SCHEMA_VERSION = '1.0'
MAX_TITLE_LENGTH = 200


def _truncate_string(s, max_len, suffix='...'):
    """Truncate string to max_len, adding suffix if truncated."""
    if not s or len(s) <= max_len:
        return s
    return s[:max_len - len(suffix)] + suffix


def _format_duration(seconds):
    """Format duration in seconds to human readable string."""
    if seconds is None:
        return None
    seconds = int(seconds)
    if seconds < 3600:
        return '%d:%02d' % (seconds // 60, seconds % 60)
    return '%d:%02d:%02d' % (seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def _format_date(date_str):
    """Format YYYYMMDD date string to YYYY-MM-DD."""
    if not date_str or len(date_str) < 8:
        return date_str
    return '%s-%s-%s' % (date_str[:4], date_str[4:6], date_str[6:8])


def _format_count(count):
    """Format large numbers with K/M suffix."""
    if count is None:
        return ''
    if count >= 1000000:
        return '%.1fM' % (count / 1000000)
    if count >= 1000:
        return '%.1fK' % (count / 1000)
    return str(count)


def _safe_filename(title, index=None, ext=None, max_title_len=MAX_TITLE_LENGTH):
    """Generate a safe filename from title.

    Format: [index_]<sanitized_title>[.ext]
    """
    # Sanitize the title for cross-platform compatibility
    safe_title = sanitize_filename(title or 'video', restricted=True)
    # Truncate if too long
    safe_title = _truncate_string(safe_title, max_title_len, '')

    parts = []
    if index is not None:
        parts.append('%02d' % index)
        parts.append(safe_title)
        filename = '_'.join(parts)
    else:
        filename = safe_title

    if ext:
        filename = filename + '.' + ext
    return filename


def _safe_dirname(title):
    """Generate a safe directory name from playlist title."""
    safe_title = sanitize_filename(title or 'playlist', restricted=True)
    safe_title = _truncate_string(safe_title, MAX_TITLE_LENGTH, '')
    return safe_title


def open_with_default_player(filepath):
    """Open a file with the system's default application.

    Cross-platform support for Windows, macOS, and Linux.
    """
    filepath = os.path.abspath(filepath)

    if sys.platform == 'darwin':  # macOS
        subprocess.Popen(['open', filepath])
    elif sys.platform == 'win32':  # Windows
        os.startfile(filepath)
    else:  # Linux and other Unix-like
        # Try xdg-open first, then fallback to other openers
        openers = ['xdg-open', 'gnome-open', 'kde-open']
        for opener in openers:
            try:
                subprocess.Popen(
                    [opener, filepath],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return
            except OSError:
                continue
        raise RuntimeError('No suitable file opener found. Please install xdg-utils.')


class OfflineDownloadHelper(object):
    """Helper class for managing offline downloads."""

    def __init__(self, ydl, output_dir):
        self.ydl = ydl
        self.output_dir = os.path.abspath(output_dir)
        self.playlist_dir = None
        self.manifest = None
        self.current_playlist_info = None
        self._video_entries = []
        self._is_single_video = False
        self._simulate = ydl.params.get('simulate', False)
        self._skip_download = ydl.params.get('skip_download', False)

    def setup_playlist(self, playlist_info):
        """Set up the playlist directory and initialize the manifest.

        Called when processing a playlist.
        """
        playlist_title = playlist_info.get('title') or playlist_info.get('id') or 'playlist'

        dirname = _safe_dirname(playlist_title)
        self.playlist_dir = os.path.join(self.output_dir, dirname)

        # Create directory if it doesn't exist (unless simulating)
        if not self._simulate and not os.path.exists(encodeFilename(self.playlist_dir)):
            os.makedirs(encodeFilename(self.playlist_dir))

        self.current_playlist_info = playlist_info
        self._video_entries = []

        # Initialize manifest
        self.manifest = {
            'schema_version': SCHEMA_VERSION,
            'type': 'playlist',
            'downloaded_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'source_url': playlist_info.get('webpage_url'),
            'playlist': {
                'id': playlist_info.get('id'),
                'title': playlist_title,
                'description': playlist_info.get('description'),
                'uploader': playlist_info.get('uploader'),
                'uploader_id': playlist_info.get('uploader_id'),
                'uploader_url': playlist_info.get('uploader_url'),
                'thumbnail': None,
            },
            'videos': [],
            'stats': {
                'total_videos': 0,
                'downloaded_count': 0,
            }
        }

        self.ydl.to_screen('[offline] Created offline directory: %s' % self.playlist_dir)
        return self.playlist_dir

    def setup_single_video(self, video_info):
        """Set up directory for a single video (not a playlist).

        Creates a playlist-like structure with a single video entry.
        """
        video_title = video_info.get('title') or video_info.get('id') or 'video'

        # For single videos, use the video title as the "playlist" name
        dirname = _safe_dirname(video_title)
        self.playlist_dir = os.path.join(self.output_dir, dirname)

        # Create directory if it doesn't exist (unless simulating)
        if not self._simulate and not os.path.exists(encodeFilename(self.playlist_dir)):
            os.makedirs(encodeFilename(self.playlist_dir))

        self._is_single_video = True
        self._video_entries = []

        # Initialize manifest for single video
        self.manifest = {
            'schema_version': SCHEMA_VERSION,
            'type': 'single_video',
            'downloaded_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'source_url': video_info.get('webpage_url'),
            'playlist': {
                'id': video_info.get('id'),
                'title': video_title,
                'description': video_info.get('description'),
                'uploader': video_info.get('uploader'),
                'uploader_id': video_info.get('uploader_id'),
                'uploader_url': video_info.get('uploader_url'),
                'thumbnail': None,
            },
            'videos': [],
            'stats': {
                'total_videos': 1,
                'downloaded_count': 0,
            }
        }

        self.ydl.to_screen('[offline] Created offline directory: %s' % self.playlist_dir)
        return self.playlist_dir

    def get_video_paths(self, index, video_info):
        """Get the output paths for a video and its thumbnail.

        Returns a dict with 'video' and 'thumbnail' paths.
        """
        if self.playlist_dir is None:
            raise RuntimeError('Playlist not set up. Call setup_playlist() or setup_single_video() first.')

        video_title = video_info.get('title') or video_info.get('id') or 'video'
        ext = video_info.get('ext') or 'mp4'

        # Generate base filename (without extension)
        base_filename = _safe_filename(video_title, index=index)

        video_path = os.path.join(self.playlist_dir, base_filename + '.' + ext)
        thumb_path = os.path.join(self.playlist_dir, base_filename + '.jpg')

        return {
            'video': video_path,
            'thumbnail': thumb_path,
            'base_filename': base_filename,
        }

    def add_video_entry(self, index, video_info, paths, downloaded=True):
        """Add a video entry to the manifest.

        Called after processing each video.
        """
        video_title = video_info.get('title') or video_info.get('id') or 'video'
        ext = video_info.get('ext') or 'mp4'

        base_filename = paths['base_filename']
        video_filename = base_filename + '.' + ext
        thumb_filename = base_filename + '.jpg'

        # Check if thumbnail was actually downloaded (unless simulating)
        has_thumbnail = False
        if not self._simulate:
            thumb_path = os.path.join(self.playlist_dir, thumb_filename)
            has_thumbnail = os.path.exists(encodeFilename(thumb_path))

        entry = {
            'index': index,
            'id': video_info.get('id'),
            'title': video_title,
            'description': video_info.get('description'),
            'uploader': video_info.get('uploader'),
            'uploader_id': video_info.get('uploader_id'),
            'upload_date': video_info.get('upload_date'),
            'duration': video_info.get('duration'),
            'duration_string': _format_duration(video_info.get('duration')),
            'view_count': video_info.get('view_count'),
            'like_count': video_info.get('like_count'),
            'filename': video_filename,
            'thumbnail': thumb_filename if has_thumbnail else None,
            'downloaded': downloaded,
        }

        self._video_entries.append(entry)

        # Update stats
        self.manifest['stats']['total_videos'] = len(self._video_entries)
        if downloaded:
            self.manifest['stats']['downloaded_count'] += 1

    def create_placeholder(self, video_path):
        """Create an empty placeholder file for --skip-download mode.

        Args:
            video_path: Path to the placeholder file to create.
        """
        if self._simulate:
            return

        if not os.path.exists(encodeFilename(video_path)):
            # Create empty placeholder file
            with open(encodeFilename(video_path), 'wb') as f:
                pass  # Empty file
            self.ydl.to_screen('[offline] Created placeholder: %s' % video_path)

    def finalize(self):
        """Finalize the manifest and write it to disk.

        Called after all videos have been processed.
        """
        if self.manifest is None or self.playlist_dir is None:
            return

        # Don't write anything in simulate mode
        if self._simulate:
            self.ydl.to_screen('[offline] Simulate mode: would download %d of %d videos' % (
                self.manifest['stats']['total_videos'],
                self.manifest['stats']['total_videos']))
            return

        # Update manifest with all video entries
        self.manifest['videos'] = self._video_entries

        # Write manifest
        manifest_path = os.path.join(self.playlist_dir, MANIFEST_FILENAME)
        write_json_file(self.manifest, manifest_path)

        self.ydl.to_screen('[offline] Wrote manifest: %s' % manifest_path)
        self.ydl.to_screen('[offline] Downloaded %d of %d videos' % (
            self.manifest['stats']['downloaded_count'],
            self.manifest['stats']['total_videos']
        ))


class OfflineCLI(object):
    """Interactive CLI for browsing offline playlists."""

    def __init__(self, manifest_path, no_color=False):
        self.manifest_path = manifest_path
        self.no_color = no_color
        self.manifest = None
        self.playlist_dir = None
        self.videos = []
        self.selected_index = 0
        self.scroll_offset = 0
        self.running = True

        # Terminal dimensions
        self.term_height = 24
        self.term_width = 80

        # Number of video rows visible
        self.visible_rows = 10

    def load_manifest(self):
        """Load the manifest file."""
        if os.path.isdir(self.manifest_path):
            manifest_file = os.path.join(self.manifest_path, MANIFEST_FILENAME)
        else:
            manifest_file = self.manifest_path

        self.playlist_dir = os.path.dirname(os.path.abspath(manifest_file))

        if not os.path.exists(manifest_file):
            raise RuntimeError('Manifest not found: %s' % manifest_file)

        with open(manifest_file, 'r', encoding='utf-8') as f:
            self.manifest = json.load(f)

        self.videos = self.manifest.get('videos', [])

        if not self.videos:
            raise RuntimeError('No videos found in manifest')

    def _get_terminal_size(self):
        """Get terminal size, with fallback."""
        try:
            import shutil
            size = shutil.get_terminal_size()
            return size.lines, size.columns
        except Exception:
            return 24, 80

    def _clear_screen(self):
        """Clear the terminal screen."""
        if sys.platform == 'win32':
            os.system('cls')
        else:
            sys.stdout.write('\033[2J\033[H')
            sys.stdout.flush()

    def _truncate_to_width(self, s, width):
        """Truncate string to fit width."""
        if not s:
            return ''
        s = compat_str(s)
        if len(s) <= width:
            return s
        return s[:width - 3] + '...'

    def draw(self):
        """Draw the interface with all video details in the list."""
        self.term_height, self.term_width = self._get_terminal_size()
        self._clear_screen()

        playlist = self.manifest.get('playlist', {})
        stats = self.manifest.get('stats', {})

        # Header
        title = playlist.get('title', 'Unknown Playlist')
        print('=' * self.term_width)
        print('PLAYLIST: %s' % self._truncate_to_width(title, self.term_width - 11))
        uploader = playlist.get('uploader') or playlist.get('uploader_id') or 'Unknown'
        total = stats.get('total_videos', len(self.videos))
        downloaded = stats.get('downloaded_count', total)
        print('By: %s | %d videos (%d downloaded)' % (
            self._truncate_to_width(uploader, 30), total, downloaded))
        print('=' * self.term_width)

        # Calculate visible area - each video takes 3 lines
        lines_per_video = 3
        self.visible_rows = max(1, (self.term_height - 8) // lines_per_video)

        # Adjust scroll offset if needed
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + self.visible_rows:
            self.scroll_offset = self.selected_index - self.visible_rows + 1

        # Video list with details
        visible_videos = self.videos[self.scroll_offset:self.scroll_offset + self.visible_rows]
        for i, video in enumerate(visible_videos):
            actual_index = self.scroll_offset + i
            is_selected = actual_index == self.selected_index

            marker = '>' if is_selected else ' '
            idx_str = str(video.get('index', actual_index + 1))

            # Line 1: Index, Title, Duration
            title_str = video.get('title', 'Unknown')
            duration = video.get('duration_string') or _format_duration(video.get('duration')) or ''
            title_width = self.term_width - 12
            line1 = '%s%s. %s' % (marker, idx_str.rjust(3), self._truncate_to_width(title_str, title_width))
            if duration:
                line1 = line1[:self.term_width - len(duration) - 2] + ' [' + duration + ']'

            # Line 2: Uploader, Date, Views, Likes
            uploader_str = video.get('uploader', '')
            upload_date = video.get('upload_date', '')
            if upload_date:
                upload_date = _format_date(upload_date)
            views = _format_count(video.get('view_count'))
            likes = _format_count(video.get('like_count'))

            details = []
            if uploader_str:
                details.append(self._truncate_to_width(uploader_str, 25))
            if upload_date:
                details.append(upload_date)
            if views:
                details.append('%s views' % views)
            if likes:
                details.append('%s likes' % likes)
            line2 = '     ' + ' | '.join(details) if details else ''

            # Line 3: Description (truncated)
            desc = video.get('description', '')
            if desc:
                # Get first line of description, truncated
                desc_line = desc.split('\n')[0]
                line3 = '     ' + self._truncate_to_width(desc_line, self.term_width - 6)
            else:
                line3 = ''

            # Print with highlighting
            if is_selected and not self.no_color:
                print('\033[7m%s\033[0m' % line1[:self.term_width].ljust(self.term_width))
                if line2:
                    print('\033[7m%s\033[0m' % line2[:self.term_width].ljust(self.term_width))
                if line3:
                    print('\033[7m%s\033[0m' % line3[:self.term_width].ljust(self.term_width))
            else:
                print(line1[:self.term_width])
                if line2:
                    print(line2[:self.term_width])
                if line3:
                    print(line3[:self.term_width])

            # Separator between videos
            if i < len(visible_videos) - 1:
                print('-' * self.term_width)

        # Footer
        print('=' * self.term_width)
        print('Video %d of %d' % (self.selected_index + 1, len(self.videos)))
        print('[Up/Down/j/k] Navigate  [Enter] Play  [q] Quit')

    def play_selected(self):
        """Play the selected video."""
        if not self.videos:
            return

        video = self.videos[self.selected_index]
        filename = video.get('filename')

        if not filename:
            print('Error: No filename for this video')
            return

        filepath = os.path.join(self.playlist_dir, filename)

        if not os.path.exists(filepath):
            print('Error: Video file not found: %s' % filepath)
            self._read_key()
            return

        # Check if it's an empty placeholder
        if os.path.getsize(filepath) == 0:
            print('Error: Video not downloaded (placeholder file)')
            self._read_key()
            return

        try:
            open_with_default_player(filepath)
        except Exception as e:
            print('Error opening video: %s' % e)
            self._read_key()

    def _read_key(self):
        """Read a single key press."""
        if sys.platform == 'win32':
            import msvcrt
            key = msvcrt.getch()
            if key in (b'\x00', b'\xe0'):  # Special key prefix
                key = msvcrt.getch()
                if key == b'H':  # Up arrow
                    return 'up'
                elif key == b'P':  # Down arrow
                    return 'down'
                elif key == b'I':  # Page Up
                    return 'pageup'
                elif key == b'Q':  # Page Down
                    return 'pagedown'
            key = key.decode('utf-8', errors='ignore')
        else:
            import tty
            import termios
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                key = sys.stdin.read(1)
                if key == '\x1b':  # Escape sequence
                    key2 = sys.stdin.read(1)
                    if key2 == '[':
                        key3 = sys.stdin.read(1)
                        if key3 == 'A':
                            return 'up'
                        elif key3 == 'B':
                            return 'down'
                        elif key3 == '5':
                            sys.stdin.read(1)  # consume ~
                            return 'pageup'
                        elif key3 == '6':
                            sys.stdin.read(1)  # consume ~
                            return 'pagedown'
                    return 'escape'
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        return key

    def handle_input(self):
        """Handle keyboard input."""
        key = self._read_key()

        if key in ('q', 'Q', 'escape', '\x03'):  # q, Q, Escape, Ctrl+C
            self.running = False
        elif key in ('up', 'k', 'K'):
            if self.selected_index > 0:
                self.selected_index -= 1
        elif key in ('down', 'j', 'J'):
            if self.selected_index < len(self.videos) - 1:
                self.selected_index += 1
        elif key in ('\r', '\n', ' '):  # Enter or Space
            self.play_selected()
        elif key in ('g',):  # Go to first
            self.selected_index = 0
        elif key in ('G',):  # Go to last
            self.selected_index = len(self.videos) - 1
        elif key == 'pageup':
            self.selected_index = max(0, self.selected_index - self.visible_rows)
        elif key == 'pagedown':
            self.selected_index = min(len(self.videos) - 1, self.selected_index + self.visible_rows)

    def run(self):
        """Main loop."""
        self.load_manifest()

        while self.running:
            self.draw()
            self.handle_input()

        self._clear_screen()
        print('Goodbye!')


def run_offline_cli(dirpath, no_color=False):
    """Entry point for the offline CLI.

    Args:
        dirpath: Path to the offline playlist directory or manifest file.
        no_color: If True, disable color output.
    """
    try:
        cli = OfflineCLI(dirpath, no_color=no_color)
        cli.run()
    except KeyboardInterrupt:
        print('\nInterrupted.')
    except Exception as e:
        print('Error: %s' % e)
        sys.exit(1)
