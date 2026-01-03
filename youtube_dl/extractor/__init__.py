from __future__ import unicode_literals

import os

from ..plugins import load_plugins, PLUGIN_API_VERSION  # noqa: F401

# Environment variable to control extractor loading mode
# Set YTDL_NO_BUILTIN_EXTRACTORS=1 to run in plugin-only mode
_NO_BUILTIN_EXTRACTORS = os.environ.get(
    'YTDL_NO_BUILTIN_EXTRACTORS', '').lower() in ('1', 'true', 'yes')

# Load plugins and register in module globals for get_info_extractor()
_PLUGIN_CLASSES, _PLUGIN_CLASS_NAMES = load_plugins()
for _klass in _PLUGIN_CLASSES:
    globals()[_klass.__name__] = _klass

# Track whether we have any extractors available
_HAS_BUILTIN_EXTRACTORS = False
_LAZY_LOADER = False
_ALL_CLASSES = []

if not _NO_BUILTIN_EXTRACTORS:
    try:
        from .lazy_extractors import *  # noqa: F401,F403
        from .lazy_extractors import _ALL_CLASSES as _LAZY_ALL_CLASSES
        _LAZY_LOADER = True
        _HAS_BUILTIN_EXTRACTORS = True
        _ALL_CLASSES = [
            k for k in _LAZY_ALL_CLASSES
            if k.__name__ not in _PLUGIN_CLASS_NAMES
        ]
    except ImportError:
        try:
            from .extractors import *  # noqa: F401,F403
            _HAS_BUILTIN_EXTRACTORS = True
            _ALL_CLASSES = [
                klass for name, klass in globals().items()
                if name.endswith('IE') and name != 'GenericIE'
                and name not in _PLUGIN_CLASS_NAMES
            ]
            # Add GenericIE last if it exists (may be loaded as plugin instead)
            if 'GenericIE' in globals() and 'GenericIE' not in _PLUGIN_CLASS_NAMES:
                _ALL_CLASSES.append(globals()['GenericIE'])
        except ImportError:
            # No built-in extractors available - running in plugin-only mode
            _HAS_BUILTIN_EXTRACTORS = False
            _ALL_CLASSES = []


def gen_extractor_classes():
    """
    Return list of all extractor classes.

    Order: Plugins first, then built-ins. GenericIE (if present) is always last
    regardless of whether it comes from plugins or built-ins.

    In plugin-only mode (YTDL_NO_BUILTIN_EXTRACTORS=1 or when built-in
    extractors are not installed), only plugin extractors are returned.
    """
    # Separate GenericIE from other classes (it should always be last)
    result = []
    generic_ie = None

    # Add plugins first (excluding GenericIE)
    for klass in _PLUGIN_CLASSES:
        if klass.__name__ == 'GenericIE':
            generic_ie = klass
        else:
            result.append(klass)

    # Add built-ins (excluding GenericIE)
    for klass in _ALL_CLASSES:
        if klass.__name__ == 'GenericIE':
            if generic_ie is None:  # Plugin GenericIE takes precedence
                generic_ie = klass
        else:
            result.append(klass)

    # GenericIE always last
    if generic_ie is not None:
        result.append(generic_ie)

    return result


def gen_extractors():
    """Return instances of all extractors."""
    return [klass() for klass in gen_extractor_classes()]


def list_extractors(age_limit):
    """Return extractors suitable for age, sorted by name."""
    return sorted(
        filter(lambda ie: ie.is_suitable(age_limit), gen_extractors()),
        key=lambda ie: ie.IE_NAME.lower())


def get_info_extractor(ie_name):
    """
    Get extractor class by name (without 'IE' suffix).

    Raises KeyError if extractor not found.
    """
    ie_class_name = ie_name + 'IE'
    if ie_class_name in globals():
        return globals()[ie_class_name]
    raise KeyError(
        'Extractor %s not found. Is the plugin installed?' % ie_class_name)


def has_extractors():
    """
    Check if any extractors are available.

    Returns True if either built-in extractors or plugins are loaded.
    Useful for CLI to provide helpful error messages when no extractors
    are installed.
    """
    return bool(_PLUGIN_CLASSES) or _HAS_BUILTIN_EXTRACTORS


def is_plugin_only_mode():
    """
    Check if running in plugin-only mode.

    Returns True if built-in extractors are disabled or not installed.
    """
    return _NO_BUILTIN_EXTRACTORS or not _HAS_BUILTIN_EXTRACTORS
