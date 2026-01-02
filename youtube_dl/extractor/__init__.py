from __future__ import unicode_literals

from ..plugins import load_plugins, PLUGIN_API_VERSION

# Load plugins and register in module globals for get_info_extractor()
_PLUGIN_CLASSES, _PLUGIN_CLASS_NAMES = load_plugins()
for _klass in _PLUGIN_CLASSES:
    globals()[_klass.__name__] = _klass

try:
    from .lazy_extractors import *
    from .lazy_extractors import _ALL_CLASSES
    _LAZY_LOADER = True
    _ALL_CLASSES = [k for k in _ALL_CLASSES if k.__name__ not in _PLUGIN_CLASS_NAMES]
except ImportError:
    _LAZY_LOADER = False
    from .extractors import *
    _ALL_CLASSES = [
        klass for name, klass in globals().items()
        if name.endswith('IE') and name != 'GenericIE' and name not in _PLUGIN_CLASS_NAMES
    ]
    _ALL_CLASSES.append(GenericIE)


def gen_extractor_classes():
    """Return list of extractors. Plugins first, then built-ins, GenericIE last."""
    return _PLUGIN_CLASSES + _ALL_CLASSES


def gen_extractors():
    """Return instances of all extractors."""
    return [klass() for klass in gen_extractor_classes()]


def list_extractors(age_limit):
    """Return extractors suitable for age, sorted by name."""
    return sorted(
        filter(lambda ie: ie.is_suitable(age_limit), gen_extractors()),
        key=lambda ie: ie.IE_NAME.lower())


def get_info_extractor(ie_name):
    """Get extractor class by name (without 'IE' suffix)."""
    return globals()[ie_name + 'IE']
