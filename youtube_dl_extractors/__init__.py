# coding: utf-8
"""
youtube_dl_extractors - Site-specific extractors for youtube-dl

This package contains all site-specific extractors that were previously bundled
with youtube-dl core. They are now distributed separately to allow:

1. The core youtube-dl to be distributed via app stores without site-specific code
2. Independent maintenance and updates of extractors
3. Users to install only the extractors they need
4. Third-party extractor development without forking the core

Usage:
    This package registers extractors automatically when installed via pip.
    Extractors are loaded through the youtube_dl.plugins.extractor entry point.

For plugin development, see:
    https://github.com/ytdl-org/youtube-dl/blob/master/docs/PLUGINS.md
"""

from __future__ import unicode_literals

__version__ = '2024.01.01'
__author__ = 'youtube-dl contributors'
