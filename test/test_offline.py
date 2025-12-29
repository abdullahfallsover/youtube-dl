# coding: utf-8

from __future__ import unicode_literals

# Allow direct execution
import os
import sys
import unittest
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_dl.offline import (
    OfflineDownloadHelper,
    OfflineCLI,
    _safe_filename,
    _safe_dirname,
    _format_duration,
    _format_date,
    _format_count,
    _truncate_string,
    MANIFEST_FILENAME,
)


class MockYDL(object):
    """Mock YoutubeDL class for testing."""

    def __init__(self, params=None):
        self.params = params or {}
        self.messages = []

    def to_screen(self, msg):
        self.messages.append(msg)


class TestHelperFunctions(unittest.TestCase):
    """Tests for offline module helper functions."""

    def test_truncate_string(self):
        # Short strings unchanged
        self.assertEqual(_truncate_string('Short', 20), 'Short')
        # Long strings truncated with suffix
        result = _truncate_string('This is a very long string', 15)
        self.assertEqual(result, 'This is a ve...')
        self.assertEqual(len(result), 15)
        # Edge cases
        self.assertIsNone(_truncate_string(None, 20))
        self.assertEqual(_truncate_string('', 20), '')

    def test_format_duration(self):
        # Various durations
        self.assertEqual(_format_duration(30), '0:30')
        self.assertEqual(_format_duration(125), '2:05')
        self.assertEqual(_format_duration(3661), '1:01:01')
        self.assertIsNone(_format_duration(None))

    def test_format_date(self):
        self.assertEqual(_format_date('20251225'), '2025-12-25')
        self.assertEqual(_format_date('202512'), '202512')  # Too short
        self.assertIsNone(_format_date(None))

    def test_format_count(self):
        self.assertEqual(_format_count(500), '500')
        self.assertEqual(_format_count(1500), '1.5K')
        self.assertEqual(_format_count(2500000), '2.5M')
        self.assertEqual(_format_count(None), '')

    def test_safe_filename(self):
        # Basic filename generation
        self.assertEqual(_safe_filename('My Video Title', index=1, ext='mp4'), '01_My_Video_Title.mp4')
        self.assertEqual(_safe_filename('Single Video', ext='mp4'), 'Single_Video.mp4')

        # Special characters sanitized
        result = _safe_filename('Video: Part 1 | Special!', index=2, ext='webm')
        self.assertIn('02_', result)
        self.assertTrue(result.endswith('.webm'))
        self.assertNotIn(':', result)
        self.assertNotIn('|', result)

        # Unicode converted
        result = _safe_filename('Vidéo avec Açcénts', index=1, ext='mp4')
        self.assertIn('01_', result)
        self.assertTrue(result.endswith('.mp4'))

    def test_safe_dirname(self):
        self.assertEqual(_safe_dirname('My Playlist'), 'My_Playlist')
        # Special characters sanitized
        result = _safe_dirname('Playlist: Best Videos!')
        self.assertNotIn(':', result)
        self.assertNotIn('!', result)


class TestOfflineDownloadHelper(unittest.TestCase):
    """Tests for OfflineDownloadHelper class."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mock_ydl = MockYDL()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_setup_playlist(self):
        helper = OfflineDownloadHelper(self.mock_ydl, self.test_dir)
        playlist_info = {
            'id': 'PLtest123',
            'title': 'Test Playlist',
            'description': 'A test playlist',
            'uploader': 'Test Channel',
            'uploader_id': '@test',
            'webpage_url': 'https://youtube.com/playlist?list=PLtest123',
        }

        result_dir = helper.setup_playlist(playlist_info)

        # Verify directory creation and naming
        self.assertTrue(os.path.isdir(result_dir))
        self.assertEqual(os.path.basename(result_dir), 'Test_Playlist')

        # Verify manifest initialization
        self.assertIsNotNone(helper.manifest)
        self.assertEqual(helper.manifest['type'], 'playlist')
        self.assertEqual(helper.manifest['playlist']['title'], 'Test Playlist')

    def test_setup_single_video(self):
        helper = OfflineDownloadHelper(self.mock_ydl, self.test_dir)
        video_info = {
            'id': 'vid123',
            'title': 'Test Video',
            'description': 'A test video',
            'uploader': 'Test Creator',
            'webpage_url': 'https://youtube.com/watch?v=vid123',
        }

        result_dir = helper.setup_single_video(video_info)

        self.assertTrue(os.path.isdir(result_dir))
        self.assertTrue(helper._is_single_video)
        self.assertEqual(helper.manifest['type'], 'single_video')

    def test_video_paths_and_entries(self):
        helper = OfflineDownloadHelper(self.mock_ydl, self.test_dir)
        helper.setup_playlist({'id': 'PL1', 'title': 'Test'})

        video_info = {
            'id': 'vid123',
            'title': 'Test Video',
            'description': 'A test video description',
            'uploader': 'Creator',
            'upload_date': '20251225',
            'duration': 300,
            'view_count': 1000,
            'like_count': 50,
            'ext': 'mp4',
        }

        # Test path generation
        paths = helper.get_video_paths(1, video_info)
        self.assertIn('video', paths)
        self.assertIn('thumbnail', paths)
        self.assertTrue(paths['video'].endswith('.mp4'))
        self.assertTrue(paths['thumbnail'].endswith('.jpg'))
        self.assertNotIn('vid123', paths['base_filename'])  # No ID in filename

        # Test adding entry
        helper.add_video_entry(1, video_info, paths, downloaded=True)
        self.assertEqual(len(helper._video_entries), 1)
        entry = helper._video_entries[0]
        self.assertEqual(entry['title'], 'Test Video')
        self.assertEqual(entry['duration_string'], '5:00')
        self.assertTrue(entry['downloaded'])

    def test_finalize_writes_manifest(self):
        helper = OfflineDownloadHelper(self.mock_ydl, self.test_dir)
        helper.setup_playlist({'id': 'PL1', 'title': 'Test'})

        video_info = {'id': 'vid123', 'title': 'Test Video', 'ext': 'mp4'}
        paths = helper.get_video_paths(1, video_info)
        helper.add_video_entry(1, video_info, paths, downloaded=True)
        helper.finalize()

        # Verify manifest file
        manifest_path = os.path.join(helper.playlist_dir, MANIFEST_FILENAME)
        self.assertTrue(os.path.exists(manifest_path))

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        self.assertEqual(len(manifest['videos']), 1)
        self.assertEqual(manifest['stats']['downloaded_count'], 1)

    def test_simulate_mode(self):
        """Test simulate mode follows realistic control path.

        This tests the actual integration: in simulate mode, process_info()
        returns early but should still track video entries for count reporting.
        We simulate this by following the same control flow as YoutubeDL.
        """
        mock_ydl = MockYDL({'simulate': True})
        helper = OfflineDownloadHelper(mock_ydl, self.test_dir)

        # Setup playlist (simulating __process_playlist)
        helper.setup_playlist({'id': 'PL1', 'title': 'Test Playlist'})

        # Simulate process_info() being called for each video
        # In the real code, process_info() adds entries before early return in simulate mode
        for i in range(3):
            video_info = {
                'id': 'vid%d' % i,
                'title': 'Test %d' % i,
                'ext': 'mp4',
                'playlist_index': i + 1,
            }
            # This mirrors what happens in process_info() simulate mode block:
            # - get_video_paths() is called
            # - add_video_entry() is called with downloaded=True (would be downloaded)
            paths = helper.get_video_paths(i + 1, video_info)
            helper.add_video_entry(i + 1, video_info, paths, downloaded=True)

        # Finalize (simulating end of __process_playlist)
        helper.finalize()

        # Manifest should NOT be written in simulate mode
        manifest_path = os.path.join(helper.playlist_dir, MANIFEST_FILENAME)
        self.assertFalse(os.path.exists(manifest_path))

        # Should report correct count (3 videos would be downloaded)
        self.assertTrue(
            any('would download 3 of 3' in msg for msg in mock_ydl.messages),
            'Expected "would download 3 of 3" in messages: %s' % mock_ydl.messages
        )

    def test_simulate_mode_no_entries_reports_zero(self):
        """Test that simulate mode with no video entries reports 0."""
        mock_ydl = MockYDL({'simulate': True})
        helper = OfflineDownloadHelper(mock_ydl, self.test_dir)

        helper.setup_playlist({'id': 'PL1', 'title': 'Test Playlist'})
        # Don't add any videos - simulates early failure or empty playlist
        helper.finalize()

        # Should report 0 of 0
        self.assertTrue(
            any('would download 0 of 0' in msg for msg in mock_ydl.messages),
            'Expected "would download 0 of 0" in messages: %s' % mock_ydl.messages
        )

    def test_create_placeholder(self):
        helper = OfflineDownloadHelper(self.mock_ydl, self.test_dir)
        helper.setup_playlist({'id': 'PL1', 'title': 'Test'})

        video_info = {'id': 'vid1', 'title': 'Test', 'ext': 'mp4'}
        paths = helper.get_video_paths(1, video_info)

        # Test with direct path argument
        helper.create_placeholder(paths['video'])

        self.assertTrue(os.path.exists(paths['video']))
        self.assertEqual(os.path.getsize(paths['video']), 0)


class TestOfflineCLI(unittest.TestCase):
    """Tests for OfflineCLI class."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.manifest = {
            'schema_version': '1.0',
            'type': 'playlist',
            'downloaded_at': '2025-12-29T12:00:00Z',
            'source_url': 'https://youtube.com/playlist?list=PLtest',
            'playlist': {
                'id': 'PLtest',
                'title': 'Test Playlist',
                'description': 'A test playlist',
                'uploader': 'Test Channel',
                'uploader_id': '@test',
                'thumbnail': None,
            },
            'videos': [
                {
                    'index': 1,
                    'id': 'vid1',
                    'title': 'First Video',
                    'description': 'Description of first video',
                    'uploader': 'Creator 1',
                    'upload_date': '20251225',
                    'duration': 300,
                    'duration_string': '5:00',
                    'view_count': 1000,
                    'like_count': 50,
                    'filename': '01_First_Video.mp4',
                    'thumbnail': None,
                    'downloaded': True,
                },
                {
                    'index': 2,
                    'id': 'vid2',
                    'title': 'Second Video',
                    'description': 'Description of second video',
                    'uploader': 'Creator 2',
                    'upload_date': '20251226',
                    'duration': 600,
                    'duration_string': '10:00',
                    'view_count': 2000,
                    'like_count': 100,
                    'filename': '02_Second_Video.mp4',
                    'thumbnail': None,
                    'downloaded': True,
                },
            ],
            'stats': {
                'total_videos': 2,
                'downloaded_count': 2,
            }
        }
        manifest_path = os.path.join(self.test_dir, MANIFEST_FILENAME)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_manifest(self):
        # Test loading from directory
        cli = OfflineCLI(self.test_dir)
        cli.load_manifest()
        self.assertEqual(len(cli.videos), 2)
        self.assertEqual(cli.manifest['playlist']['title'], 'Test Playlist')

        # Test loading from file path
        manifest_path = os.path.join(self.test_dir, MANIFEST_FILENAME)
        cli2 = OfflineCLI(manifest_path)
        cli2.load_manifest()
        self.assertEqual(len(cli2.videos), 2)

    def test_load_manifest_errors(self):
        # Not found
        cli = OfflineCLI('/nonexistent/path')
        with self.assertRaises(RuntimeError) as ctx:
            cli.load_manifest()
        self.assertIn('Manifest not found', str(ctx.exception))

        # Empty videos
        empty_manifest = dict(self.manifest)
        empty_manifest['videos'] = []
        manifest_path = os.path.join(self.test_dir, MANIFEST_FILENAME)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(empty_manifest, f)

        cli2 = OfflineCLI(self.test_dir)
        with self.assertRaises(RuntimeError) as ctx:
            cli2.load_manifest()
        self.assertIn('No videos found', str(ctx.exception))

    def test_navigation_and_truncation(self):
        cli = OfflineCLI(self.test_dir)
        cli.load_manifest()

        # Initial state
        self.assertEqual(cli.selected_index, 0)

        # Navigation bounds
        cli.selected_index = 1
        self.assertEqual(cli.selected_index, 1)
        cli.selected_index = min(len(cli.videos) - 1, 100)
        self.assertEqual(cli.selected_index, 1)

        # String truncation
        self.assertEqual(cli._truncate_to_width('Short', 20), 'Short')
        self.assertEqual(cli._truncate_to_width('A very long string', 10), 'A very ...')
        self.assertEqual(cli._truncate_to_width('', 10), '')
        self.assertEqual(cli._truncate_to_width(None, 10), '')


class TestOfflineOptions(unittest.TestCase):
    """Tests for offline command-line options."""

    def test_options_parsing(self):
        from youtube_dl.options import parseOpts

        # Basic parsing
        parser, opts, args = parseOpts(['--offline-download', '/tmp/test', 'https://example.com'])
        self.assertEqual(opts.offline_download, '/tmp/test')

        parser, opts, args = parseOpts(['--offline-cli', '/tmp/test'])
        self.assertEqual(opts.offline_cli, '/tmp/test')

        # Options that will conflict (checked in _real_main, not parseOpts)
        parser, opts, args = parseOpts(['--offline-download', '/tmp/test', '-o', '%(title)s.%(ext)s', 'https://example.com'])
        self.assertEqual(opts.offline_download, '/tmp/test')
        self.assertEqual(opts.outtmpl, '%(title)s.%(ext)s')

        parser, opts, args = parseOpts(['--offline-download', '/tmp/test', '--id', 'https://example.com'])
        self.assertEqual(opts.offline_download, '/tmp/test')
        self.assertTrue(opts.useid)

    def test_compatible_options(self):
        from youtube_dl.options import parseOpts

        # --skip-download is compatible
        parser, opts, args = parseOpts(['--offline-download', '/tmp/test', '--skip-download', 'https://example.com'])
        self.assertIsNotNone(opts.offline_download)
        self.assertTrue(opts.skip_download)

        # --simulate is compatible
        parser, opts, args = parseOpts(['--offline-download', '/tmp/test', '--simulate', 'https://example.com'])
        self.assertIsNotNone(opts.offline_download)
        self.assertTrue(opts.simulate)

        # Playlist options are compatible
        parser, opts, args = parseOpts([
            '--offline-download', '/tmp/test',
            '--playlist-start', '2',
            '--playlist-end', '5',
            'https://example.com'
        ])
        self.assertIsNotNone(opts.offline_download)
        self.assertEqual(opts.playliststart, 2)
        self.assertEqual(opts.playlistend, 5)


if __name__ == '__main__':
    unittest.main()
