# flake8: noqa
"""
Extractor imports for youtube_dl_extractors package.

This file imports all site-specific extractors so they can be registered
as plugins via the entry point system.

Note: This is auto-generated. Run `make update-extractors` to regenerate.
"""
from __future__ import unicode_literals

# Import all extractors from the legacy location
# These will be gradually migrated to this package
from youtube_dl.extractor.extractors import *
