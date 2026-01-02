# coding: utf-8
from __future__ import unicode_literals

import os
import sys
import traceback

# Plugin API version - increment when making breaking changes to plugin interface
PLUGIN_API_VERSION = 1

# Environment variable to override plugin directories (for testing)
PLUGIN_DIRS_ENV_VAR = 'YTDL_PLUGIN_DIRS'


class PluginResult(object):
    """Result of loading a single plugin extractor class."""
    __slots__ = ('klass', 'name', 'source')

    def __init__(self, klass, source):
        self.klass = klass
        self.name = klass.__name__
        self.source = source


class PluginLoader(object):
    """Handles discovery and loading of extractor plugins."""

    def __init__(self):
        self._log_fn = None

    def set_logger(self, log_fn):
        """Set logging function. Signature: log_fn(message, level='debug')"""
        self._log_fn = log_fn

    def _log(self, message, level='debug'):
        if self._log_fn:
            self._log_fn(message, level)

    # -------------------------------------------------------------------------
    # Directory Discovery
    # -------------------------------------------------------------------------

    def get_plugin_dirs(self):
        """Return plugin directories in priority order."""
        # Allow override via environment variable (colon-separated)
        env_dirs = os.environ.get(PLUGIN_DIRS_ENV_VAR)
        if env_dirs:
            return [d.strip() for d in env_dirs.split(os.pathsep) if d.strip()]

        dirs = []
        if os.name == 'nt':
            appdata = os.environ.get('APPDATA')
            if appdata:
                dirs.append(os.path.join(appdata, 'youtube-dl', 'plugins', 'extractor'))
        else:
            dirs.append(os.path.join(os.path.expanduser('~'), '.config', 'youtube-dl', 'plugins', 'extractor'))
            dirs.append('/etc/youtube-dl/plugins/extractor')
        return dirs

    # -------------------------------------------------------------------------
    # Module Importing
    # -------------------------------------------------------------------------

    def _import_module(self, module_name, module_path):
        """Import a Python module from path. Returns module or None."""
        if sys.version_info[0] >= 3:
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        import imp
        return imp.load_source(module_name, module_path)

    # -------------------------------------------------------------------------
    # Class Validation
    # -------------------------------------------------------------------------

    def _is_valid_extractor(self, klass):
        """Check if class is a valid extractor."""
        return (isinstance(klass, type)
                and hasattr(klass, '_VALID_URL')
                and callable(getattr(klass, '_real_extract', None)))

    def _check_api_version(self, klass):
        """Check API version compatibility. Returns True if compatible."""
        version = getattr(klass, 'PLUGIN_API_VERSION', 1)
        return version <= PLUGIN_API_VERSION

    # -------------------------------------------------------------------------
    # Class Extraction
    # -------------------------------------------------------------------------

    def _extract_classes_from_module(self, module, source):
        """Extract valid extractor classes from module. Yields PluginResult."""
        for name in dir(module):
            if not name.endswith('IE') or name == 'InfoExtractor':
                continue

            klass = getattr(module, name)

            if not self._is_valid_extractor(klass):
                self._log('Skipping %s: missing _VALID_URL or _real_extract' % name, 'debug')
                continue

            if not self._check_api_version(klass):
                version = getattr(klass, 'PLUGIN_API_VERSION', 1)
                self._log('%s requires API version %d (have %d)' % (name, version, PLUGIN_API_VERSION), 'warning')
                continue

            self._log('Found %s in %s' % (name, source), 'debug')
            yield PluginResult(klass, source)

    # -------------------------------------------------------------------------
    # Loading from Directory
    # -------------------------------------------------------------------------

    def _load_from_file(self, filepath):
        """Load plugins from a single file. Yields PluginResult."""
        module_name = 'ytdl_plugin_' + os.path.basename(filepath)[:-3]
        try:
            module = self._import_module(module_name, filepath)
            if module:
                for result in self._extract_classes_from_module(module, filepath):
                    yield result
        except Exception as e:
            self._log('Failed to load %s: %s' % (filepath, e), 'warning')
            self._log(traceback.format_exc(), 'debug')

    def _load_from_directory(self, directory):
        """Load plugins from a directory. Yields PluginResult."""
        if not os.path.isdir(directory):
            self._log('Directory not found: %s' % directory, 'debug')
            return

        self._log('Scanning: %s' % directory, 'debug')

        for filename in sorted(os.listdir(directory)):
            if not filename.endswith('.py') or filename.startswith('_'):
                continue
            filepath = os.path.join(directory, filename)
            for result in self._load_from_file(filepath):
                yield result

    # -------------------------------------------------------------------------
    # Loading from Entry Points
    # -------------------------------------------------------------------------

    def _get_entry_points(self):
        """Get entry points for plugin group. Returns list."""
        try:
            from pkg_resources import iter_entry_points
            return list(iter_entry_points('youtube_dl.plugins.extractor'))
        except ImportError:
            pass

        try:
            from importlib.metadata import entry_points
            eps = entry_points()
            if hasattr(eps, 'select'):
                return list(eps.select(group='youtube_dl.plugins.extractor'))
            if isinstance(eps, dict):
                return list(eps.get('youtube_dl.plugins.extractor', []))
        except ImportError:
            pass

        return []

    def _load_from_entry_points(self):
        """Load plugins from entry points. Yields PluginResult."""
        try:
            entry_points = self._get_entry_points()
        except Exception as e:
            self._log('Entry points error: %s' % e, 'debug')
            return

        for ep in entry_points:
            ep_name = getattr(ep, 'name', str(ep))
            try:
                module = ep.load()
                for result in self._extract_classes_from_module(module, 'entrypoint:%s' % ep_name):
                    yield result
            except Exception as e:
                self._log('Failed to load entry point %s: %s' % (ep_name, e), 'warning')

    # -------------------------------------------------------------------------
    # Main Interface
    # -------------------------------------------------------------------------

    def load_plugins(self):
        """
        Load all plugins from all sources.

        Returns:
            list of PluginResult (deduplicated by class name, preserving order)
        """
        results = []
        seen = set()

        # Entry points first (pip-installed packages)
        for result in self._load_from_entry_points():
            if result.name not in seen:
                results.append(result)
                seen.add(result.name)

        # Then directories (user before system)
        for directory in self.get_plugin_dirs():
            for result in self._load_from_directory(directory):
                if result.name in seen:
                    self._log('Duplicate %s from %s (skipped)' % (result.name, result.source), 'debug')
                    continue
                results.append(result)
                seen.add(result.name)

        if results:
            self._log('Loaded %d plugin(s)' % len(results), 'debug')

        return results


def load_plugins(log_fn=None):
    """
    Load all extractor plugins.

    Args:
        log_fn: Optional logging function with signature (message, level)

    Returns:
        tuple: (list of extractor classes, set of class names)
    """
    loader = PluginLoader()
    if log_fn:
        loader.set_logger(log_fn)

    results = loader.load_plugins()
    classes = [r.klass for r in results]
    names = set(r.name for r in results)

    return classes, names
