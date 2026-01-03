# Migration Guide: Plugin-Based Extractors

This guide helps contributors and users understand how to migrate to the new plugin-based extractor architecture.

## For Users

### What's Changing

Previously, youtube-dl bundled all site extractors in a single package. Now:

- **Core package**: `youtube-dl` contains only the download engine
- **Extractor packages**: Site-specific code is in separate packages

### Installation

**Traditional (all extractors):**
```bash
pip install youtube-dl youtube-dl-extractors
```

**Minimal (specific sites only):**
```bash
pip install youtube-dl youtube-dl-youtube
```

**Core only (for custom plugins):**
```bash
pip install youtube-dl
# Then install your custom plugins
```

### Error: "No extractors are installed"

If you see this error, install an extractor package:
```bash
pip install youtube-dl-extractors
```

## For Extractor Contributors

### Current Extractors

Extractors in `youtube_dl/extractor/` continue to work during the transition. No immediate action required.

### Creating New Extractors

New extractors should be developed as plugins:

1. Create a package structure:
```
my_extractor/
├── my_extractor/
│   ├── __init__.py
│   └── extractor.py
└── setup.py
```

2. Implement the extractor:
```python
# my_extractor/extractor.py
from youtube_dl.extractor.common import InfoExtractor

class MyServiceIE(InfoExtractor):
    _VALID_URL = r'https?://myservice\.example/(?P<id>\w+)'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        # ... extraction logic ...
        return {
            'id': video_id,
            'title': self._og_search_title(webpage),
            'url': self._og_search_video_url(webpage),
        }
```

3. Register via entry point:
```python
# setup.py
from setuptools import setup

setup(
    name='youtube-dl-myservice',
    version='1.0.0',
    packages=['my_extractor'],
    install_requires=['youtube-dl'],
    entry_points={
        'youtube_dl.plugins.extractor': [
            'myservice = my_extractor.extractor',
        ],
    },
)
```

4. Install and test:
```bash
pip install -e .
youtube-dl https://myservice.example/video123
```

### Migrating Existing Extractors

To migrate an extractor from core to a plugin package:

1. Copy the extractor file(s) to your plugin package
2. Update imports:
   ```python
   # Before (in-tree)
   from .common import InfoExtractor

   # After (plugin)
   from youtube_dl.extractor.common import InfoExtractor
   ```
3. Remove any relative imports to other extractors (plugins should be self-contained)
4. Add entry point registration in setup.py
5. Submit PR to remove from core once plugin is stable

### GenericIE Considerations

If your extractor uses GenericIE imports for embed detection:

```python
# Before
from .generic import GenericIE

# After - avoid direct import, use url_result instead
return self.url_result(embed_url)
```

Or make GenericIE an optional dependency:
```python
try:
    from youtube_dl.extractor.generic import GenericIE
except ImportError:
    GenericIE = None

# Later...
if GenericIE and GenericIE.suitable(url):
    return self.url_result(url, GenericIE.ie_key())
```

## For Core Contributors

### Directory Structure

```
youtube_dl/
├── extractor/
│   ├── __init__.py      # Plugin-aware registry
│   ├── common.py        # InfoExtractor base (KEEP IN CORE)
│   ├── commonprotocols.py # RTMP/MMS (KEEP IN CORE)
│   ├── adobepass.py     # TV Provider auth (KEEP IN CORE)
│   └── *.py             # Site extractors (MIGRATE TO PLUGINS)

youtube_dl_extractors/   # Plugin package
├── __init__.py
├── extractors.py        # Re-exports all extractors
├── generic/             # GenericIE plugin
│   └── __init__.py
└── setup.py
```

### What Stays in Core

- `common.py` - InfoExtractor base class
- `commonprotocols.py` - RTMP/MMS handlers
- `adobepass.py` - TV Provider authentication
- Plugin loading infrastructure

### What Moves to Plugins

- All site-specific extractors (`youtube.py`, `vimeo.py`, etc.)
- `generic.py` - GenericIE fallback extractor
- `extractors.py` - Extractor index

### Testing

```bash
# Full test suite (with extractors)
python -m pytest test/

# Plugin system tests
python -m pytest test/test_plugins.py

# Core-only tests (no extractors)
YTDL_NO_BUILTIN_EXTRACTORS=1 python -m pytest test/test_YoutubeDL.py

# Verify plugin loading
python -c "from youtube_dl.extractor import gen_extractor_classes; print(len(gen_extractor_classes()))"
```

## Timeline

1. **Phase 1 (Current)**: Plugin infrastructure in place, built-in extractors still work
2. **Phase 2**: Extractors copied to `youtube_dl_extractors` package
3. **Phase 3**: Built-in extractors deprecated, plugins recommended
4. **Phase 4**: Built-in extractors removed from core

During Phases 1-3, both methods work to ensure backward compatibility.

## FAQ

**Q: Do I need to change my youtube-dl usage?**
A: Not immediately. Install `youtube-dl-extractors` alongside `youtube-dl` for the traditional experience.

**Q: Will my custom extractors break?**
A: No. The plugin system is additive. Existing extractors continue to work.

**Q: Can I still contribute extractors to the main repo?**
A: Yes, but new extractors should be in `youtube_dl_extractors/` rather than `youtube_dl/extractor/`.

**Q: Why is GenericIE in a separate plugin?**
A: GenericIE matches any URL and enables downloading from arbitrary sites. Separating it allows the core to be distributed via app stores with stricter policies.
