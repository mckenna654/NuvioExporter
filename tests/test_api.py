import unittest
from fastapi.testclient import TestClient

from app.main import MAX_REQUEST_BYTES, app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_and_local_assets(self):
        self.assertEqual(self.client.get('/api/health').json(), {'status': 'ok', 'app': 'NuvioExporter', 'version': '3.3.0'})
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn("script-src 'self'", page.headers['Content-Security-Policy'])
        self.assertEqual(page.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get('/static/js/fusion.js').status_code, 200)

    def test_invalid_input_does_not_claim_success(self):
        response = self.client.post('/api/fusion/convert', json={'export_data': {'oops': []}})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('fusionConfig', response.json())

    def test_options_validated_without_echoing_secrets(self):
        response = self.client.post('/api/fusion/convert', json={'export_data': {}, 'addon_urls': {'example': {'value': 'PRIVATE_SECRET'}}})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('PRIVATE_SECRET', response.text)

    def test_cross_origin_write_rejected(self):
        response = self.client.post('/api/fusion/convert', headers={'Origin': 'https://attacker.example'}, json={'export_data': []})
        self.assertEqual(response.status_code, 403)

    def test_same_origin_allowed(self):
        response = self.client.post('/api/fusion/convert', headers={'Origin': 'http://testserver'}, json={'export_data': []})
        self.assertEqual(response.status_code, 200)

    def test_body_limit(self):
        response = self.client.post('/api/fusion/convert', content=b'x' * (MAX_REQUEST_BYTES + 1), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)

    def test_layout_conversion_and_fixed_compatibility_routes_are_exposed(self):
        paths = set(self.client.get('/openapi.json').json()['paths'])
        self.assertEqual(paths, {'/', '/api/health', '/api/presets/{name}', '/api/fusion/convert',
                                '/api/remux/preview', '/api/remux/import',
                                '/api/bridge/settings', '/bridge/{token}/manifest.json',
                                '/bridge/{token}/catalog/{typ}/{cid}.json',
                                '/bridge/{token}/catalog/{typ}/{cid}/{path_extra}.json'})

    def test_examples_are_data_not_an_alternate_conversion_pipeline(self):
        response = self.client.get('/api/presets/fusion')
        self.assertIn('rawData', response.json())
        self.assertNotIn('fusionConfig', response.json())
