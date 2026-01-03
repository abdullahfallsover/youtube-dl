# youtube-dl-extractors

Site-specific extractors for [youtube-dl](https://github.com/ytdl-org/youtube-dl).

## Installation

```bash
pip install youtube-dl-extractors
```

This will install all site extractors. For the core youtube-dl package only:

```bash
pip install youtube-dl
```

## What's Included

This package includes extractors for hundreds of video sites including:

- YouTube
- Vimeo
- Dailymotion
- Facebook
- Twitter
- Instagram
- And many more...

## GenericIE

The `GenericIE` fallback extractor is included in this package. It handles:

- Direct video file URLs
- Embedded video players
- RSS/Atom feeds with media enclosures
- Open Graph video metadata
- HTML5 video tags

## Plugin System

youtube-dl now supports a plugin architecture. This package registers its
extractors via the `youtube_dl.plugins.extractor` entry point.

You can also create custom extractors. See the
[plugin documentation](https://github.com/ytdl-org/youtube-dl/blob/master/docs/ARCHITECTURE.md).

## Development

To install in development mode:

```bash
git clone https://github.com/ytdl-org/youtube-dl.git
cd youtube-dl
pip install -e .
pip install -e youtube_dl_extractors/
```

## License

Public Domain (same as youtube-dl core)
