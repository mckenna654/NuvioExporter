import io
import json
import unittest
from unittest.mock import patch

from scripts.smoke_container import check


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class ContainerSmokeTests(unittest.TestCase):
    def test_startup_connection_reset_is_retried_before_conversion(self):
        replies = [ConnectionResetError('container is still starting'),
                   response({'status': 'ok', 'app': 'NuvioExporter', 'version': 'test'}),
                   response({'rawData': []}),
                   response({'report': {'canExport': True, 'counts': {'preserved': 1, 'unsupported': 0}},
                             'fusionConfig': {'requiredAddons': ['https://example.invalid/manifest.json']}}),
                   io.BytesIO(b'<title>NuvioExporter</title>')]
        with patch('scripts.smoke_container.urllib.request.urlopen', side_effect=replies) as fetch, \
                patch('scripts.smoke_container.time.sleep') as pause, patch('builtins.print'):
            check('http://127.0.0.1:7088')
        pause.assert_called_once_with(1)
        self.assertEqual(fetch.call_count, 5)

    def test_startup_retry_has_a_deadline(self):
        with patch('scripts.smoke_container.urllib.request.urlopen', side_effect=ConnectionResetError), \
                patch('scripts.smoke_container.time.monotonic', side_effect=[0, 46]), \
                patch('scripts.smoke_container.time.sleep') as pause:
            with self.assertRaisesRegex(RuntimeError, 'within 45 seconds'):
                check('http://127.0.0.1:7088')
        pause.assert_not_called()
