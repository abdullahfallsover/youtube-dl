# youtube-dl Architecture: Plugin-Based Extractors

This document describes the architecture for youtube-dl's plugin-based extractor system.

## Overview

youtube-dl is transitioning from a monolithic architecture (where all site extractors are bundled with the core) to a plugin-based architecture where:

1. **Core Package (`youtube-dl`)**: Contains the download engine, post-processors, and plugin loading infrastructure. Can be distributed via app stores.

2. **Extractor Plugins**: Site-specific code distributed as separate Python packages that register via entry points.

## Why This Change?

- **App Store Distribution**: The core can be distributed via app stores that prohibit site-specific download functionality
- **Independent Updates**: Extractors can be updated without waiting for core releases
- **Modularity**: Users can install only the extractors they need
- **Third-Party Development**: Anyone can create extractors without forking the core

## Package Structure

```
youtube-dl (core)
├── youtube_dl/
│   ├── __init__.py          # CLI entry point
│   ├── YoutubeDL.py          # Main downloader class
│   ├── plugins.py            # Plugin loading infrastructure
│   ├── extractor/
│   │   ├── __init__.py       # Extractor registry (plugin-aware)
│   │   ├── common.py         # InfoExtractor base class
│   │   └── commonprotocols.py # RTMP/MMS protocol handlers
│   ├── downloader/           # Download backends
│   └── postprocessor/        # Post-processing modules

youtube-dl-extractors (plugin package)
├── youtube_dl_extractors/
│   ├── __init__.py
│   ├── extractors.py         # Imports all extractors
│   └── generic/              # GenericIE subpackage
│       └── __init__.py
└── setup.py                  # Entry point registration
```

## Plugin Loading

### Entry Points

Plugins register via the `youtube_dl.plugins.extractor` entry point group:

```python
# setup.py
setup(
    name='youtube-dl-extractors',
    entry_points={
        'youtube_dl.plugins.extractor': [
            'extractors = youtube_dl_extractors.extractors',
        ],
    },
)
```

### Directory-Based Plugins

Users can also drop `.py` files in plugin directories:

- Linux/macOS: `~/.config/youtube-dl/plugins/extractor/`
- Windows: `%APPDATA%\youtube-dl\plugins\extractor\`
- Custom: Set `YTDL_PLUGIN_DIRS` environment variable

### Loading Order

1. Entry point plugins (pip-installed packages)
2. Directory plugins (user before system)
3. Built-in extractors (if available)
4. GenericIE is always last

## Extractor Base Class

All extractors must inherit from `InfoExtractor`:

```python
from youtube_dl.extractor.common import InfoExtractor

class MyServiceIE(InfoExtractor):
    _VALID_URL = r'https?://myservice\.example/(?P<id>[0-9]+)'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        # ... extraction logic ...
        return {
            'id': video_id,
            'title': 'Video Title',
            'url': 'https://...',
        }
```

## Plugin API Version

Plugins can declare their API version requirement:

```python
class MyServiceIE(InfoExtractor):
    PLUGIN_API_VERSION = 1  # Requires API v1 or compatible
    # ...
```

The core will skip plugins requiring a higher API version than supported.

## Environment Variables

- `YTDL_PLUGIN_DIRS`: Colon-separated list of plugin directories
- `YTDL_NO_BUILTIN_EXTRACTORS`: Set to `1` to disable built-in extractors

## Migration Path

### For Users

During the transition period, both architectures work:

```bash
# Install core only (requires extractor plugins)
pip install youtube-dl

# Install with all extractors (traditional behavior)
pip install youtube-dl youtube-dl-extractors

# Install specific extractors only
pip install youtube-dl youtube-dl-youtube youtube-dl-vimeo
```

### For Developers

1. Extractors in `youtube_dl/extractor/` continue to work
2. New extractors should be developed as plugins
3. Existing extractors will be gradually migrated to `youtube_dl_extractors/`

## GenericIE

`GenericIE` is a special fallback extractor that:
- Matches any URL (`_VALID_URL = r'.*'`)
- Handles direct media links, embeds, RSS feeds, etc.
- Always runs last in the extractor chain

Because it enables downloading from arbitrary sites, GenericIE is distributed as a separate plugin (`youtube-dl-generic`) rather than bundled with core.

## Testing

Run tests with:

```bash
# Test plugin system
python -m pytest test/test_plugins.py

# Test with plugins disabled
YTDL_NO_BUILTIN_EXTRACTORS=1 python -m youtube_dl --list-extractors
```
