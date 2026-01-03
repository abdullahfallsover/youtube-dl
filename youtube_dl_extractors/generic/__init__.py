# coding: utf-8
"""
GenericIE - Fallback extractor for arbitrary URLs

This extractor handles:
- Direct video file URLs
- Embedded video players from various platforms
- RSS/Atom feeds with media enclosures
- Open Graph and JSON-LD video metadata
- HTML5 video tags

Since GenericIE can download from arbitrary sites, it is distributed
as a separate plugin to allow the core youtube-dl to be distributed
via app stores that prohibit such functionality.

Installation:
    pip install youtube-dl-generic

The extractor will be automatically loaded by youtube-dl when installed.
"""

from __future__ import unicode_literals

# Re-export GenericIE for plugin registration
from youtube_dl.extractor.generic import GenericIE

__all__ = ['GenericIE']
__version__ = '2024.01.01'
