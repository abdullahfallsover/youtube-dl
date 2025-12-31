# coding: utf-8
from __future__ import unicode_literals

import json
import os
import subprocess
import sys
import time

from .compat import (
    compat_expanduser,
    compat_getenv,
    compat_input,
    compat_str,
)
from .utils import (
    encodeFilename,
    formatSeconds,
    hyphenate_date,
    limit_length,
    sanitize_filename,
    write_json_file,
)


MANIFEST_FILENAME = '.offline_manifest.json'
SCHEMA_VERSION = '1.1'
MAX_TITLE_LENGTH = 200

# Settings file configuration
SETTINGS_FILENAME = 'offline.json'
MAX_RECENT_DOWNLOADS = 10


def _get_settings_path():
    """Get cross-platform path for offline settings file.

    Follows youtube-dl conventions:
    - Windows: %APPDATA%/youtube-dl/offline.json
    - Linux/Mac: ~/.config/youtube-dl/offline.json (XDG)
    """
    xdg_config_home = compat_getenv('XDG_CONFIG_HOME')
    if xdg_config_home:
        return os.path.join(xdg_config_home, 'youtube-dl', SETTINGS_FILENAME)

    appdata = compat_getenv('APPDATA')
    if appdata:
        return os.path.join(appdata, 'youtube-dl', SETTINGS_FILENAME)

    return os.path.join(compat_expanduser('~'), '.config', 'youtube-dl', SETTINGS_FILENAME)


def _load_settings():
    """Load offline settings from disk.

    Returns:
        dict: Settings dictionary, empty dict if file doesn't exist or is invalid.
    """
    settings_path = _get_settings_path()

    if not os.path.exists(encodeFilename(settings_path)):
        return {}

    try:
        with open(encodeFilename(settings_path), 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}


def _save_settings(settings):
    """Save offline settings to disk atomically.

    Args:
        settings: dict to save
    """
    settings_path = _get_settings_path()

    # Ensure parent directory exists
    settings_dir = os.path.dirname(settings_path)
    if not os.path.exists(encodeFilename(settings_dir)):
        os.makedirs(encodeFilename(settings_dir))

    write_json_file(settings, settings_path)


def _looks_like_url(value):
    """Check if a string looks like a URL.

    Used to distinguish URLs from file paths in argument parsing.
    """
    if not value:
        return False
    return (value.startswith('http://') or
            value.startswith('https://') or
            value.startswith('www.'))


def _add_recent_download(settings, path, url, title, video_count):
    """Add or update an entry in the recent downloads list.

    Updates existing entry if path matches, otherwise adds new entry.
    Prunes list to MAX_RECENT_DOWNLOADS entries.
    """
    recent = settings.get('recent_downloads', [])
    new_entry = {
        'path': path,
        'url': url,
        'title': title or os.path.basename(path),
        'last_updated': _utc_timestamp(),
        'video_count': video_count,
    }
    recent = [r for r in recent if r.get('path') != path]
    recent.insert(0, new_entry)
    settings['recent_downloads'] = recent[:MAX_RECENT_DOWNLOADS]


def _utc_timestamp():
    """Get current UTC time as ISO 8601 string."""
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


class DirectoryType(object):
    """Constants for directory type detection."""
    UNKNOWN = 'unknown'
    SINGLE_PLAYLIST = 'single_playlist'
    MULTI_PLAYLIST = 'multi_playlist'
    INVALID = 'invalid'


def _format_duration(seconds):
    """Format duration in seconds to human readable string (MM:SS or HH:MM:SS)."""
    if seconds is None:
        return None
    return formatSeconds(int(seconds))


def _format_date(date_str):
    """Format YYYYMMDD date string to YYYY-MM-DD."""
    if not date_str:
        return date_str
    return hyphenate_date(date_str)


def _format_count(count):
    """Format large numbers with K/M suffix for display."""
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
    # Truncate if too long (without ellipsis for filenames)
    if len(safe_title) > max_title_len:
        safe_title = safe_title[:max_title_len]

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
    if len(safe_title) > MAX_TITLE_LENGTH:
        safe_title = safe_title[:MAX_TITLE_LENGTH]
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


def detect_directory_type(dirpath):
    """Detect whether a directory is a single playlist or a directory of playlists.

    Returns:
        tuple: (DirectoryType, list of playlist directories or None, warning message or None)
    """
    dirpath = os.path.abspath(dirpath)

    if not os.path.isdir(dirpath):
        return DirectoryType.INVALID, None, 'Path is not a directory: %s' % dirpath

    # Check if this directory itself has a manifest (single playlist)
    manifest_path = os.path.join(dirpath, MANIFEST_FILENAME)
    if os.path.exists(manifest_path):
        return DirectoryType.SINGLE_PLAYLIST, [dirpath], None

    # Check for subdirectories with manifests (directory of playlists)
    playlist_dirs = []
    non_playlist_items = []

    for item in os.listdir(encodeFilename(dirpath)):
        item_path = os.path.join(dirpath, item)
        if os.path.isdir(encodeFilename(item_path)):
            sub_manifest = os.path.join(item_path, MANIFEST_FILENAME)
            if os.path.exists(encodeFilename(sub_manifest)):
                playlist_dirs.append(item_path)
            else:
                non_playlist_items.append(item)
        elif item != MANIFEST_FILENAME:  # Ignore manifest file at root if we got here
            non_playlist_items.append(item)

    if playlist_dirs:
        warning = None
        if non_playlist_items:
            warning = ('Directory contains %d items that are not offline playlists: %s'
                       % (len(non_playlist_items), ', '.join(non_playlist_items[:3])
                          + ('...' if len(non_playlist_items) > 3 else '')))
        return DirectoryType.MULTI_PLAYLIST, sorted(playlist_dirs), warning

    return DirectoryType.UNKNOWN, None, 'No offline playlists found in: %s' % dirpath


def load_playlist_info(playlist_dir):
    """Load basic playlist information from a manifest file.

    Returns:
        dict: Playlist metadata including title, description, video count, etc.
    """
    manifest_path = os.path.join(playlist_dir, MANIFEST_FILENAME)

    if not os.path.exists(encodeFilename(manifest_path)):
        return None

    try:
        with open(encodeFilename(manifest_path), 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except (IOError, ValueError):
        return None

    playlist = manifest.get('playlist', {})
    stats = manifest.get('stats', {})
    videos = manifest.get('videos', [])

    return {
        'path': playlist_dir,
        'dirname': os.path.basename(playlist_dir),
        'title': playlist.get('title') or os.path.basename(playlist_dir),
        'description': playlist.get('description'),
        'uploader': playlist.get('uploader'),
        'uploader_id': playlist.get('uploader_id'),
        'total_videos': stats.get('total_videos', len(videos)),
        'downloaded_count': stats.get('downloaded_count', len(videos)),
        'downloaded_at': manifest.get('downloaded_at'),
        'source_url': manifest.get('source_url'),
        'type': manifest.get('type', 'playlist'),
    }


class OfflineDownloadHelper(object):
    """Helper class for managing offline downloads."""

    def __init__(self, ydl, output_dir):
        self.ydl = ydl
        self.output_dir = os.path.abspath(output_dir)
        self.playlist_dir = None
        self.manifest = None
        self.current_playlist_info = None
        self._video_entries = []
        self._existing_video_ids = set()  # Track existing videos for resume support
        self._is_single_video = False
        self._simulate = ydl.params.get('simulate', False)
        self._skip_download = ydl.params.get('skip_download', False)
        self._resumed = False
        self._skipped_count = 0
        self._new_downloads = 0  # Count of newly downloaded videos this session
        self._existing_count_at_start = 0  # Number of videos that existed before this run

    def _load_existing_manifest(self, manifest_path):
        """Load an existing manifest file for resume support.

        Returns:
            dict or None: The loaded manifest, or None if not found/invalid.
        """
        if not os.path.exists(encodeFilename(manifest_path)):
            return None

        try:
            with open(encodeFilename(manifest_path), 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, ValueError) as e:
            self.ydl.report_warning('[offline] Could not load existing manifest: %s' % e)
            return None

    def _merge_existing_manifest(self, existing_manifest, playlist_info, manifest_type='playlist'):
        """Merge existing manifest data with new playlist info.

        Returns:
            dict: The merged manifest.
        """
        # Track existing video IDs
        existing_videos = existing_manifest.get('videos', [])
        for video in existing_videos:
            if video.get('id'):
                self._existing_video_ids.add(video['id'])

        # Keep existing video entries
        self._video_entries = list(existing_videos)
        self._existing_count_at_start = len(existing_videos)

        playlist_title = playlist_info.get('title') or playlist_info.get('id') or 'playlist'

        # Create updated manifest, preserving original download time
        manifest = {
            'schema_version': SCHEMA_VERSION,
            'type': manifest_type,
            'downloaded_at': existing_manifest.get('downloaded_at',
                                                   _utc_timestamp()),
            'updated_at': _utc_timestamp(),
            'source_url': playlist_info.get('webpage_url') or existing_manifest.get('source_url'),
            'playlist': {
                'id': playlist_info.get('id') or existing_manifest.get('playlist', {}).get('id'),
                'title': playlist_title,
                'description': playlist_info.get('description') or existing_manifest.get('playlist', {}).get('description'),
                'uploader': playlist_info.get('uploader') or existing_manifest.get('playlist', {}).get('uploader'),
                'uploader_id': playlist_info.get('uploader_id') or existing_manifest.get('playlist', {}).get('uploader_id'),
                'uploader_url': playlist_info.get('uploader_url') or existing_manifest.get('playlist', {}).get('uploader_url'),
                'thumbnail': existing_manifest.get('playlist', {}).get('thumbnail'),
            },
            'videos': [],
            'stats': {
                'total_videos': len(existing_videos),
                'downloaded_count': existing_manifest.get('stats', {}).get('downloaded_count', 0),
            }
        }

        return manifest

    def setup_playlist(self, playlist_info):
        """Set up the playlist directory and initialize the manifest.

        Called when processing a playlist. Supports resuming by loading
        existing manifests and skipping already-downloaded videos.
        """
        playlist_title = playlist_info.get('title') or playlist_info.get('id') or 'playlist'

        dirname = _safe_dirname(playlist_title)
        self.playlist_dir = os.path.join(self.output_dir, dirname)

        # Check for existing manifest (resume support)
        manifest_path = os.path.join(self.playlist_dir, MANIFEST_FILENAME)
        existing_manifest = self._load_existing_manifest(manifest_path)

        if existing_manifest:
            self._resumed = True
            self.manifest = self._merge_existing_manifest(existing_manifest, playlist_info, 'playlist')
            self.ydl.to_screen('[offline] Resuming offline download in: %s (%d existing videos)'
                               % (self.playlist_dir, len(self._existing_video_ids)))
        else:
            # Create directory if it doesn't exist (unless simulating)
            if not self._simulate and not os.path.exists(encodeFilename(self.playlist_dir)):
                os.makedirs(encodeFilename(self.playlist_dir))

            self._video_entries = []

            # Initialize new manifest
            self.manifest = {
                'schema_version': SCHEMA_VERSION,
                'type': 'playlist',
                'downloaded_at': _utc_timestamp(),
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

        self.current_playlist_info = playlist_info
        return self.playlist_dir

    def setup_single_video(self, video_info):
        """Set up directory for a single video (not a playlist).

        Creates a playlist-like structure with a single video entry.
        Supports resuming by loading existing manifests.
        """
        video_title = video_info.get('title') or video_info.get('id') or 'video'

        # For single videos, use the video title as the "playlist" name
        dirname = _safe_dirname(video_title)
        self.playlist_dir = os.path.join(self.output_dir, dirname)

        # Check for existing manifest (resume support)
        manifest_path = os.path.join(self.playlist_dir, MANIFEST_FILENAME)
        existing_manifest = self._load_existing_manifest(manifest_path)

        if existing_manifest:
            self._resumed = True
            self.manifest = self._merge_existing_manifest(existing_manifest, video_info, 'single_video')
            self.ydl.to_screen('[offline] Resuming offline download in: %s (%d existing videos)'
                               % (self.playlist_dir, len(self._existing_video_ids)))
        else:
            # Create directory if it doesn't exist (unless simulating)
            if not self._simulate and not os.path.exists(encodeFilename(self.playlist_dir)):
                os.makedirs(encodeFilename(self.playlist_dir))

            self._video_entries = []

            # Initialize manifest for single video
            self.manifest = {
                'schema_version': SCHEMA_VERSION,
                'type': 'single_video',
                'downloaded_at': _utc_timestamp(),
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

        self._is_single_video = True
        return self.playlist_dir

    def is_video_already_downloaded(self, video_info):
        """Check if a video has already been downloaded (for resume support).

        Returns:
            bool: True if video already exists in manifest, False otherwise.
        """
        video_id = video_info.get('id')
        if video_id and video_id in self._existing_video_ids:
            return True
        return False

    def skip_existing_video(self, video_info):
        """Mark a video as skipped because it already exists.

        Called instead of downloading when resuming.
        """
        self._skipped_count += 1
        self.ydl.to_screen('[offline] Skipping already downloaded: %s'
                           % (video_info.get('title') or video_info.get('id')))

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
            self._new_downloads += 1

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

        # Report download statistics
        total = len(self._video_entries)
        if self._resumed:
            # Resumed session: report existing + newly added
            self.ydl.to_screen('[offline] Offline playlist now has %d videos (%d new, %d previously existed)'
                               % (total, self._new_downloads, self._existing_count_at_start))
        else:
            # Fresh download
            self.ydl.to_screen('[offline] Downloaded %d videos to offline playlist' % total)

        # Update settings with this download for recent downloads list
        try:
            settings = _load_settings()
            _add_recent_download(
                settings,
                path=self.playlist_dir,
                url=self.manifest.get('source_url'),
                title=self.manifest.get('playlist', {}).get('title'),
                video_count=total,
            )
            settings['last_download_directory'] = self.output_dir
            _save_settings(settings)
        except Exception:
            pass  # Don't fail the download if settings can't be saved


class OfflineCLIBase(object):
    """Base class for offline CLI interfaces with shared functionality."""

    def __init__(self, no_color=False):
        self.no_color = no_color
        self.selected_index = 0
        self.scroll_offset = 0
        self.running = True

        # Terminal dimensions
        self.term_height = 24
        self.term_width = 80

        # Number of visible rows
        self.visible_rows = 10

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

    def _print_highlighted(self, text, is_selected):
        """Print text with optional highlighting."""
        text = text[:self.term_width]
        if is_selected and not self.no_color:
            print('\033[7m%s\033[0m' % text.ljust(self.term_width))
        else:
            print(text)


class OfflinePlaylistBrowser(OfflineCLIBase):
    """Interactive CLI for browsing multiple offline playlists."""

    def __init__(self, dirpath, playlist_dirs, no_color=False):
        super(OfflinePlaylistBrowser, self).__init__(no_color)
        self.dirpath = os.path.abspath(dirpath)
        self.playlist_dirs = playlist_dirs
        self.playlists = []

    def load_playlists(self):
        """Load playlist information from all manifest files."""
        self.playlists = []
        for playlist_dir in self.playlist_dirs:
            info = load_playlist_info(playlist_dir)
            if info:
                self.playlists.append(info)

        if not self.playlists:
            raise RuntimeError('No valid playlists found')

    def draw(self):
        """Draw the playlist browser interface."""
        self.term_height, self.term_width = self._get_terminal_size()
        self._clear_screen()

        # Header - similar style to video list for consistency
        print('=' * self.term_width)
        print('OFFLINE PLAYLISTS')
        print('Location: %s' % self._truncate_to_width(self.dirpath, self.term_width - 11))
        print('%d playlists available' % len(self.playlists))
        print('=' * self.term_width)

        # Calculate visible area - each playlist takes 3 lines (similar to video list)
        lines_per_playlist = 3
        self.visible_rows = max(1, (self.term_height - 9) // lines_per_playlist)

        # Adjust scroll offset if needed
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + self.visible_rows:
            self.scroll_offset = self.selected_index - self.visible_rows + 1

        # Playlist list with details
        visible_playlists = self.playlists[self.scroll_offset:self.scroll_offset + self.visible_rows]
        for i, playlist in enumerate(visible_playlists):
            actual_index = self.scroll_offset + i
            is_selected = actual_index == self.selected_index

            marker = '>' if is_selected else ' '
            idx_str = str(actual_index + 1)

            # Line 1: Index, Title, Video count
            title_str = playlist.get('title', 'Unknown Playlist')
            total = playlist.get('total_videos', 0)
            downloaded = playlist.get('downloaded_count', total)
            video_info = '%d videos' % total
            if downloaded < total:
                video_info = '%d/%d videos' % (downloaded, total)

            title_width = self.term_width - 20
            line1 = '%s%s. %s' % (marker, idx_str.rjust(3), self._truncate_to_width(title_str, title_width))
            line1 = line1[:self.term_width - len(video_info) - 2] + ' [' + video_info + ']'

            # Line 2: Uploader, Type, Download date
            uploader = playlist.get('uploader') or playlist.get('uploader_id') or ''
            ptype = playlist.get('type', 'playlist')
            downloaded_at = playlist.get('downloaded_at', '')
            if downloaded_at:
                # Format: 2025-12-29T12:00:00Z -> 2025-12-29
                downloaded_at = downloaded_at[:10]

            details = []
            if uploader:
                details.append(self._truncate_to_width(uploader, 25))
            if ptype == 'single_video':
                details.append('Single video')
            if downloaded_at:
                details.append('Downloaded: %s' % downloaded_at)
            line2 = '     ' + ' | '.join(details) if details else ''

            # Line 3: Description (truncated)
            desc = playlist.get('description', '')
            if desc:
                desc_line = desc.split('\n')[0]
                line3 = '     ' + self._truncate_to_width(desc_line, self.term_width - 6)
            else:
                line3 = ''

            # Print with highlighting
            self._print_highlighted(line1, is_selected)
            if line2:
                self._print_highlighted(line2, is_selected)
            if line3:
                self._print_highlighted(line3, is_selected)

            # Separator between playlists
            if i < len(visible_playlists) - 1:
                print('-' * self.term_width)

        # Footer
        print('=' * self.term_width)
        print('Playlist %d of %d' % (self.selected_index + 1, len(self.playlists)))
        print('[Up/Down/j/k] Navigate  [Enter] Open  [q] Quit')

    def handle_input(self):
        """Handle keyboard input."""
        key = self._read_key()

        if key in ('q', 'Q', 'escape', '\x03'):  # q, Q, Escape, Ctrl+C
            self.running = False
            return None
        elif key in ('up', 'k', 'K'):
            if self.selected_index > 0:
                self.selected_index -= 1
        elif key in ('down', 'j', 'J'):
            if self.selected_index < len(self.playlists) - 1:
                self.selected_index += 1
        elif key in ('\r', '\n', ' '):  # Enter or Space
            return self.playlists[self.selected_index]['path']
        elif key in ('g',):  # Go to first
            self.selected_index = 0
        elif key in ('G',):  # Go to last
            self.selected_index = len(self.playlists) - 1
        elif key == 'pageup':
            self.selected_index = max(0, self.selected_index - self.visible_rows)
        elif key == 'pagedown':
            self.selected_index = min(len(self.playlists) - 1, self.selected_index + self.visible_rows)

        return None

    def run(self):
        """Main loop. Returns selected playlist path or None if quit."""
        self.load_playlists()

        while self.running:
            self.draw()
            selected_path = self.handle_input()
            if selected_path:
                return selected_path

        self._clear_screen()
        return None


class OfflineCLI(OfflineCLIBase):
    """Interactive CLI for browsing offline playlists."""

    def __init__(self, manifest_path, no_color=False, return_to_browser=False):
        super(OfflineCLI, self).__init__(no_color)
        self.manifest_path = manifest_path
        self.manifest = None
        self.playlist_dir = None
        self.videos = []
        self.return_to_browser = return_to_browser  # If True, 'b' key returns to browser

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
            self._print_highlighted(line1, is_selected)
            if line2:
                self._print_highlighted(line2, is_selected)
            if line3:
                self._print_highlighted(line3, is_selected)

            # Separator between videos
            if i < len(visible_videos) - 1:
                print('-' * self.term_width)

        # Footer
        print('=' * self.term_width)
        print('Video %d of %d' % (self.selected_index + 1, len(self.videos)))
        if self.return_to_browser:
            print('[Enter] Play  [d] Update  [D] New download  [b] Back  [q] Quit')
        else:
            print('[Enter] Play  [d] Update  [D] New download  [q] Quit')

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

    def _show_message(self, message):
        """Show a message and wait for keypress."""
        self._clear_screen()
        print(message)
        print('\nPress any key to continue...')
        self._read_key()

    def _update_playlist(self):
        """Update the current playlist from its source URL."""
        source_url = self.manifest.get('source_url')
        if not source_url:
            self._show_message('Error: No source URL saved in manifest.\n'
                               'This playlist cannot be updated automatically.')
            return

        self._clear_screen()
        print('=' * 60)
        print('UPDATING PLAYLIST')
        print('=' * 60)
        print()
        print('Source: %s' % source_url)
        print('Location: %s' % self.playlist_dir)
        print()

        try:
            # Import YoutubeDL and run the download
            from . import YoutubeDL

            ydl_opts = {
                'offline_download': os.path.dirname(self.playlist_dir),
                'writethumbnail': True,
                'ignoreerrors': True,
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([source_url])

            print('\nUpdate complete!')
        except Exception as e:
            print('\nError during update: %s' % e)

        print('\nPress any key to continue...')
        self._read_key()

        # Reload manifest to show new videos
        try:
            self.load_manifest()
        except Exception:
            pass  # Keep showing existing data if reload fails

    def _launch_wizard(self):
        """Launch the interactive download wizard."""
        url, directory = run_download_wizard(no_color=self.no_color)
        if not url or not directory:
            return  # User cancelled

        self._clear_screen()
        print('=' * 60)
        print('DOWNLOADING')
        print('=' * 60)
        print()
        print('URL: %s' % url)
        print('Location: %s' % directory)
        print()

        try:
            from . import YoutubeDL

            ydl_opts = {
                'offline_download': directory,
                'writethumbnail': True,
                'ignoreerrors': True,
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            print('\nDownload complete!')
        except Exception as e:
            print('\nError during download: %s' % e)

        print('\nPress any key to continue...')
        self._read_key()

        # If we downloaded to the same location, reload
        if directory == os.path.dirname(self.playlist_dir):
            try:
                self.load_manifest()
            except Exception:
                pass

    def handle_input(self):
        """Handle keyboard input. Returns 'back' if user wants to return to browser."""
        key = self._read_key()

        if key in ('q', 'Q', '\x03'):  # q, Q, Ctrl+C
            self.running = False
            return 'quit'
        elif key == 'escape':
            if self.return_to_browser:
                return 'back'
            self.running = False
            return 'quit'
        elif key in ('b', 'B') and self.return_to_browser:
            return 'back'
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
        elif key == 'd':
            self._update_playlist()
        elif key == 'D':
            self._launch_wizard()

        return None

    def run(self):
        """Main loop. Returns 'back' if user wants to return to browser, None otherwise."""
        self.load_manifest()

        while self.running:
            self.draw()
            result = self.handle_input()
            if result == 'back':
                return 'back'

        self._clear_screen()
        print('Goodbye!')
        return None


def run_offline_cli(dirpath, no_color=False):
    """Entry point for the offline CLI.

    Automatically detects whether the path is a single playlist directory
    or a directory containing multiple playlists, and launches the
    appropriate interface.

    Args:
        dirpath: Path to the offline playlist directory, manifest file,
                 or directory containing multiple playlists.
        no_color: If True, disable color output.
    """
    try:
        # Detect directory type
        dir_type, playlist_dirs, warning = detect_directory_type(dirpath)

        if warning:
            print('Warning: %s' % warning)

        if dir_type == DirectoryType.INVALID:
            print('Error: %s' % warning)
            sys.exit(1)

        if dir_type == DirectoryType.UNKNOWN:
            print('Error: %s' % warning)
            sys.exit(1)

        if dir_type == DirectoryType.SINGLE_PLAYLIST:
            # Single playlist mode - run CLI directly
            cli = OfflineCLI(dirpath, no_color=no_color, return_to_browser=False)
            cli.run()
        else:
            # Multi-playlist mode - run playlist browser with navigation
            while True:
                browser = OfflinePlaylistBrowser(dirpath, playlist_dirs, no_color=no_color)
                selected_playlist = browser.run()

                if selected_playlist is None:
                    # User quit from browser
                    break

                # User selected a playlist - open it with back navigation enabled
                cli = OfflineCLI(selected_playlist, no_color=no_color, return_to_browser=True)
                result = cli.run()

                if result != 'back':
                    # User quit from CLI (not just going back)
                    break

    except KeyboardInterrupt:
        print('\nInterrupted.')
    except Exception as e:
        print('Error: %s' % e)
        sys.exit(1)


class OfflineDownloadWizard(OfflineCLIBase):
    """Interactive wizard for offline downloads.

    Guides users through the download process with prompts for URL
    and directory, validation, and recent downloads list.
    """

    def __init__(self, no_color=False):
        super(OfflineDownloadWizard, self).__init__(no_color)
        self.settings = _load_settings()

    def _prompt_input(self, prompt, default=None):
        """Prompt for line input with optional default.

        Args:
            prompt: The prompt text to display
            default: Optional default value shown in brackets

        Returns:
            str: User input, or default if user pressed Enter with empty input
        """
        if default:
            full_prompt = '%s [%s]: ' % (prompt, default)
        else:
            full_prompt = '%s: ' % prompt

        try:
            response = compat_input(full_prompt).strip()
        except EOFError:
            return None

        return response if response else default

    def _prompt_yes_no(self, prompt, default=True):
        """Prompt for yes/no input.

        Args:
            prompt: The prompt text to display
            default: Default value (True for yes, False for no)

        Returns:
            bool: True for yes, False for no, None if cancelled
        """
        if default:
            hint = 'Y/n'
        else:
            hint = 'y/N'

        full_prompt = '%s [%s]: ' % (prompt, hint)

        try:
            response = compat_input(full_prompt).strip().lower()
        except EOFError:
            return None

        if not response:
            return default
        return response in ('y', 'yes')

    def _validate_url(self, url):
        """Validate URL using youtube-dl's extractors."""
        if not url:
            return False, 'URL cannot be empty'

        if not (_looks_like_url(url) or '.' in url):
            return False, 'Invalid URL format'

        if url.startswith('www.'):
            url = 'https://' + url

        try:
            from .extractor import gen_extractors
            for ie in gen_extractors():
                if ie.suitable(url):
                    return True, ie.IE_NAME
            return False, 'No extractor found for this URL. Supported sites include YouTube, Vimeo, and many others.'
        except Exception as e:
            return False, 'Error checking URL: %s' % str(e)

    def _validate_directory(self, path):
        """Validate directory path, offering to create if it doesn't exist.

        Args:
            path: Directory path to validate

        Returns:
            tuple: (is_valid, expanded_path or error_message)
        """
        if not path:
            return False, 'Directory path cannot be empty'

        # Expand user home directory
        expanded = compat_expanduser(path)
        expanded = os.path.abspath(expanded)

        if os.path.exists(encodeFilename(expanded)):
            if os.path.isdir(encodeFilename(expanded)):
                return True, expanded
            else:
                return False, 'Path exists but is not a directory: %s' % expanded

        # Directory doesn't exist - offer to create
        print('Directory does not exist: %s' % expanded)
        create = self._prompt_yes_no('Create it?', default=True)
        if create:
            try:
                os.makedirs(encodeFilename(expanded))
                print('Created directory: %s' % expanded)
                return True, expanded
            except OSError as e:
                return False, 'Failed to create directory: %s' % str(e)
        else:
            return False, 'Directory not created'

    def _show_recent_downloads(self):
        """Display the recent downloads list with full paths.

        Returns:
            list: Recent downloads entries
        """
        recent = self.settings.get('recent_downloads', [])
        if not recent:
            print('No recent downloads.\n')
            return []

        print('Recent downloads:')
        print()
        for i, entry in enumerate(recent[:5], 1):
            title = entry.get('title', 'Unknown')
            video_count = entry.get('video_count', 0)
            last_updated = entry.get('last_updated', '')
            path = entry.get('path', '')
            if last_updated:
                last_updated = last_updated[:10]  # Just the date part

            # Line 1: Number and title
            print('  %d. %s' % (i, title))
            # Line 2: Path
            print('     Path: %s' % path)
            # Line 3: Stats
            stats_parts = ['%d videos' % video_count]
            if last_updated:
                stats_parts.append('updated %s' % last_updated)
            print('     %s' % ', '.join(stats_parts))
            print()

        print('  N. New download')
        print()
        return recent[:5]

    def _prompt_url(self):
        """Prompt for URL with validation and retry.

        Returns:
            str: Valid URL, or None if cancelled
        """
        while True:
            url = self._prompt_input('Enter playlist/video URL')
            if url is None:
                return None
            if not url:
                print('Please enter a URL.\n')
                continue

            valid, info = self._validate_url(url)
            if valid:
                print('Detected: %s\n' % info)
                return url
            else:
                print('Error: %s' % info)
                print('Examples:')
                print('  - https://youtube.com/watch?v=xxxxx')
                print('  - https://youtube.com/playlist?list=PLxxxxx')
                print('  - https://youtu.be/xxxxx')
                print()

    def _prompt_directory(self):
        """Prompt for download directory with validation and retry.

        Returns:
            str: Valid directory path, or None if cancelled
        """
        default_dir = self.settings.get('last_download_directory')
        if not default_dir:
            default_dir = os.path.join(compat_expanduser('~'), 'offline')

        while True:
            path = self._prompt_input('Where to save?', default=default_dir)
            if path is None:
                return None

            valid, result = self._validate_directory(path)
            if valid:
                return result
            else:
                print('Error: %s\n' % result)

    def run(self):
        """Main wizard flow.

        Returns:
            tuple: (url, directory) if successful, (None, None) if cancelled
        """
        self._clear_screen()
        print('=' * 60)
        print('OFFLINE DOWNLOAD WIZARD')
        print('=' * 60)
        print()

        # Show recent downloads
        recent = self._show_recent_downloads()

        # If there are recent downloads, let user select one or start new
        url = None
        directory = None

        if recent:
            choice = self._prompt_input('Select option', 'N')
            if choice is None:
                return None, None

            if choice.upper() != 'N' and choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(recent):
                    entry = recent[idx]
                    url = entry.get('url')
                    directory = entry.get('path')
                    if url and directory:
                        print('\nUpdating: %s' % entry.get('title', 'Unknown'))
                        print('Source: %s' % url)
                        print('Location: %s\n' % directory)
                        return url, directory
                    else:
                        print('Error: Recent entry missing URL or path, starting new download.\n')

        # New download flow
        print()
        url = self._prompt_url()
        if not url:
            return None, None

        directory = self._prompt_directory()
        if not directory:
            return None, None

        # Save the directory as last used
        self.settings['last_download_directory'] = directory
        _save_settings(self.settings)

        print('\nDownloading to: %s\n' % directory)
        return url, directory


def run_download_wizard(no_color=False):
    """Entry point for the interactive download wizard.

    Args:
        no_color: If True, disable color output.

    Returns:
        tuple: (url, directory) if successful, (None, None) if cancelled
    """
    try:
        wizard = OfflineDownloadWizard(no_color=no_color)
        return wizard.run()
    except KeyboardInterrupt:
        print('\nCancelled.')
        return None, None
    except Exception as e:
        print('Error: %s' % e)
        return None, None


def _prompt_launch_browser(download_dir, no_color=False):
    """Prompt user to launch the offline browser after download.

    Args:
        download_dir: The directory where content was downloaded
        no_color: If True, disable color output
    """
    print()
    print('=' * 60)
    print('Download complete!')
    print('=' * 60)
    print()
    print('What would you like to do?')
    print('  1. Browse downloaded content')
    print('  2. Download another playlist')
    print('  3. Exit')
    print()

    try:
        choice = compat_input('Select [1]: ').strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not choice or choice == '1':
        # Launch browser
        run_offline_cli(download_dir, no_color=no_color)
    elif choice == '2':
        # Launch wizard again
        url, directory = run_download_wizard(no_color=no_color)
        if url and directory:
            # Need to do the download - import here to avoid circular import
            try:
                from . import YoutubeDL
                ydl_opts = {
                    'offline_download': directory,
                    'writethumbnail': True,
                    'ignoreerrors': True,
                }
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                # Recurse to show menu again
                _prompt_launch_browser(directory, no_color)
            except Exception as e:
                print('Error during download: %s' % e)
    # Choice 3 or anything else: just exit
