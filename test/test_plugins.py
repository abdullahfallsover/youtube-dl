#!/usr/bin/env python
# coding: utf-8
from __future__ import unicode_literals

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_dl.plugins import (
    PLUGIN_API_VERSION,
    PLUGIN_DIRS_ENV_VAR,
    PluginLoader,
    PluginResult,
    load_plugins,
)


class PluginTestCase(unittest.TestCase):
    """Base class for plugin tests with temp directory support."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.plugin_dir = os.path.join(self.temp_dir, 'extractor')
        os.makedirs(self.plugin_dir)
        self.log_messages = []
        self._orig_env = os.environ.get(PLUGIN_DIRS_ENV_VAR)
        os.environ[PLUGIN_DIRS_ENV_VAR] = self.plugin_dir

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if self._orig_env is None:
            os.environ.pop(PLUGIN_DIRS_ENV_VAR, None)
        else:
            os.environ[PLUGIN_DIRS_ENV_VAR] = self._orig_env

    def _logger(self, message, level='debug'):
        self.log_messages.append((level, message))

    def _write_plugin(self, filename, content):
        path = os.path.join(self.plugin_dir, filename)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _create_valid_plugin(self, class_name='TestPluginIE', url_pattern='testplugin'):
        return self._write_plugin('%s.py' % class_name.lower(), '''
# coding: utf-8
from __future__ import unicode_literals
from youtube_dl.extractor.common import InfoExtractor

class %s(InfoExtractor):
    _VALID_URL = r'https?://%s\\.example/(?P<id>[0-9]+)'
    def _real_extract(self, url):
        return {'id': self._match_id(url), 'title': 'Test'}
''' % (class_name, url_pattern))


class TestPluginResult(PluginTestCase):
    """Tests for PluginResult class."""

    def test_plugin_result_attributes(self):
        class FakeIE(object):
            __name__ = 'FakeIE'
        result = PluginResult(FakeIE, '/path/to/plugin.py')
        self.assertEqual(result.name, 'FakeIE')
        self.assertEqual(result.source, '/path/to/plugin.py')
        self.assertIs(result.klass, FakeIE)


class TestPluginLoaderDirectoryDiscovery(PluginTestCase):
    """Tests for directory discovery."""

    def test_env_var_overrides_default_dirs(self):
        loader = PluginLoader()
        dirs = loader.get_plugin_dirs()
        self.assertEqual(dirs, [self.plugin_dir])

    def test_env_var_supports_multiple_dirs(self):
        dir2 = os.path.join(self.temp_dir, 'dir2')
        os.makedirs(dir2)
        os.environ[PLUGIN_DIRS_ENV_VAR] = self.plugin_dir + os.pathsep + dir2

        loader = PluginLoader()
        dirs = loader.get_plugin_dirs()
        self.assertEqual(dirs, [self.plugin_dir, dir2])

    def test_default_dirs_when_no_env_var(self):
        os.environ.pop(PLUGIN_DIRS_ENV_VAR, None)
        loader = PluginLoader()
        dirs = loader.get_plugin_dirs()
        self.assertTrue(len(dirs) > 0)
        self.assertTrue(all(isinstance(d, str) for d in dirs))


class TestPluginLoaderValidation(PluginTestCase):
    """Tests for class validation."""

    def test_valid_extractor_passes(self):
        class ValidIE(object):
            _VALID_URL = r'https?://example\.com'
            def _real_extract(self, url):
                pass

        loader = PluginLoader()
        self.assertTrue(loader._is_valid_extractor(ValidIE))

    def test_missing_valid_url_fails(self):
        class InvalidIE(object):
            def _real_extract(self, url):
                pass

        loader = PluginLoader()
        self.assertFalse(loader._is_valid_extractor(InvalidIE))

    def test_missing_real_extract_fails(self):
        class InvalidIE(object):
            _VALID_URL = r'https?://example\.com'

        loader = PluginLoader()
        self.assertFalse(loader._is_valid_extractor(InvalidIE))

    def test_non_class_fails(self):
        loader = PluginLoader()
        self.assertFalse(loader._is_valid_extractor("string"))
        self.assertFalse(loader._is_valid_extractor(42))
        self.assertFalse(loader._is_valid_extractor(None))

    def test_api_version_default_is_compatible(self):
        class NoVersionIE(object):
            pass

        loader = PluginLoader()
        self.assertTrue(loader._check_api_version(NoVersionIE))

    def test_api_version_current_is_compatible(self):
        class CurrentVersionIE(object):
            PLUGIN_API_VERSION = PLUGIN_API_VERSION

        loader = PluginLoader()
        self.assertTrue(loader._check_api_version(CurrentVersionIE))

    def test_api_version_future_is_incompatible(self):
        class FutureVersionIE(object):
            PLUGIN_API_VERSION = PLUGIN_API_VERSION + 1

        loader = PluginLoader()
        self.assertFalse(loader._check_api_version(FutureVersionIE))


class TestPluginLoaderLoading(PluginTestCase):
    """Tests for plugin loading."""

    def test_load_valid_plugin(self):
        self._create_valid_plugin()

        loader = PluginLoader()
        loader.set_logger(self._logger)
        results = loader.load_plugins()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, 'TestPluginIE')

    def test_load_multiple_plugins(self):
        self._create_valid_plugin('PluginOneIE', 'pluginone')
        self._create_valid_plugin('PluginTwoIE', 'plugintwo')

        loader = PluginLoader()
        results = loader.load_plugins()

        names = [r.name for r in results]
        self.assertEqual(len(results), 2)
        self.assertIn('PluginOneIE', names)
        self.assertIn('PluginTwoIE', names)

    def test_ignores_underscore_files(self):
        self._write_plugin('_ignored.py', '''
class IgnoredIE(object):
    _VALID_URL = r'ignored'
    def _real_extract(self, url): pass
''')
        loader = PluginLoader()
        results = loader.load_plugins()
        self.assertEqual(results, [])

    def test_ignores_non_py_files(self):
        with open(os.path.join(self.plugin_dir, 'readme.txt'), 'w') as f:
            f.write('not a plugin')

        loader = PluginLoader()
        results = loader.load_plugins()
        self.assertEqual(results, [])

    def test_skips_syntax_errors_with_warning(self):
        self._write_plugin('broken.py', 'this is not valid python !!!')

        loader = PluginLoader()
        loader.set_logger(self._logger)
        results = loader.load_plugins()

        self.assertEqual(results, [])
        warnings = [m for level, m in self.log_messages if level == 'warning']
        self.assertTrue(any('Failed to load' in w for w in warnings))

    def test_skips_future_api_version_with_warning(self):
        self._write_plugin('future.py', '''
from youtube_dl.extractor.common import InfoExtractor

class FuturePluginIE(InfoExtractor):
    PLUGIN_API_VERSION = 999
    _VALID_URL = r'https?://future\\.example'
    def _real_extract(self, url): pass
''')
        loader = PluginLoader()
        loader.set_logger(self._logger)
        results = loader.load_plugins()

        self.assertEqual(results, [])
        warnings = [m for level, m in self.log_messages if level == 'warning']
        self.assertTrue(any('API version' in w for w in warnings))

    def test_deduplicates_by_class_name(self):
        # Create two directories with same class name
        dir2 = os.path.join(self.temp_dir, 'dir2')
        os.makedirs(dir2)
        os.environ[PLUGIN_DIRS_ENV_VAR] = self.plugin_dir + os.pathsep + dir2

        self._create_valid_plugin('DuplicateIE', 'first')
        with open(os.path.join(dir2, 'dup.py'), 'w') as f:
            f.write('''
from youtube_dl.extractor.common import InfoExtractor
class DuplicateIE(InfoExtractor):
    _VALID_URL = r'https?://second\\.example'
    def _real_extract(self, url): pass
''')

        loader = PluginLoader()
        loader.set_logger(self._logger)
        results = loader.load_plugins()

        duplicates = [r for r in results if r.name == 'DuplicateIE']
        self.assertEqual(len(duplicates), 1)
        # First one wins
        self.assertIn('first', duplicates[0].klass._VALID_URL)

    def test_nonexistent_directory_handled(self):
        os.environ[PLUGIN_DIRS_ENV_VAR] = '/nonexistent/path'

        loader = PluginLoader()
        loader.set_logger(self._logger)
        results = loader.load_plugins()

        self.assertEqual(results, [])

    def test_empty_directory_handled(self):
        loader = PluginLoader()
        results = loader.load_plugins()
        self.assertEqual(results, [])


class TestPluginLoaderLogging(PluginTestCase):
    """Tests for logging behavior."""

    def test_logs_found_plugins(self):
        self._create_valid_plugin()

        loader = PluginLoader()
        loader.set_logger(self._logger)
        loader.load_plugins()

        debug_msgs = [m for level, m in self.log_messages if level == 'debug']
        self.assertTrue(any('TestPluginIE' in m for m in debug_msgs))

    def test_no_logger_does_not_crash(self):
        self._create_valid_plugin()

        loader = PluginLoader()
        # No logger set
        results = loader.load_plugins()

        self.assertEqual(len(results), 1)


class TestLoadPluginsFunction(PluginTestCase):
    """Tests for the load_plugins() convenience function."""

    def test_returns_classes_and_names(self):
        self._create_valid_plugin()

        classes, names = load_plugins(log_fn=self._logger)

        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].__name__, 'TestPluginIE')
        self.assertEqual(names, {'TestPluginIE'})

    def test_empty_when_no_plugins(self):
        classes, names = load_plugins()

        self.assertEqual(classes, [])
        self.assertEqual(names, set())


class TestPluginIntegration(PluginTestCase):
    """Integration tests with the extractor module."""

    def test_plugins_loaded_before_builtins(self):
        self._create_valid_plugin('IntegrationTestIE', 'integration')

        # Force reimport to pick up the test plugin
        import importlib
        from youtube_dl import extractor
        importlib.reload(extractor)

        classes = extractor.gen_extractor_classes()
        class_names = [c.__name__ for c in classes]

        # Plugin should be first
        self.assertEqual(class_names[0], 'IntegrationTestIE')
        # GenericIE should be last
        self.assertEqual(class_names[-1], 'GenericIE')
        # Builtins should be present
        self.assertIn('YoutubeIE', class_names)

    def test_get_info_extractor_finds_plugin(self):
        self._create_valid_plugin('LookupTestIE', 'lookup')

        import importlib
        from youtube_dl import extractor
        importlib.reload(extractor)

        ie = extractor.get_info_extractor('LookupTest')
        self.assertEqual(ie.__name__, 'LookupTestIE')

    def test_plugin_matches_url_before_builtin(self):
        self._create_valid_plugin('UrlMatchIE', 'urlmatch')

        import importlib
        from youtube_dl import extractor
        importlib.reload(extractor)

        classes = extractor.gen_extractor_classes()
        test_url = 'https://urlmatch.example/12345'

        for cls in classes:
            if cls.suitable(test_url):
                self.assertEqual(cls.__name__, 'UrlMatchIE')
                break
        else:
            self.fail('No extractor matched the URL')


class TestPluginAPIVersion(unittest.TestCase):
    """Tests for API versioning."""

    def test_api_version_is_positive_integer(self):
        self.assertIsInstance(PLUGIN_API_VERSION, int)
        self.assertGreater(PLUGIN_API_VERSION, 0)

    def test_api_version_is_one(self):
        # This is version 1 of the plugin API
        self.assertEqual(PLUGIN_API_VERSION, 1)


if __name__ == '__main__':
    unittest.main()
