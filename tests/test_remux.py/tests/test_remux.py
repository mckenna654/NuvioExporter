import copy
import json
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.bridge import BridgePlan, ProfileStore
from app.main import app
from app.remux import RemuxClient, RemuxError, RemuxService, plan_setup, marker, digest


URL = 'https://catalog.example/private-config/manifest.json?key=SECRET'


def setup_data():
    return [{'id': 'weekend', 'title': 'Weekend', 'folders': [
        {'id': 'picks', 'title': 'Picks', 'sources': [
            {'addonId': 'original', 'type': 'movie', 'catalogId': 'top'}]}]}]


class FakeRemux:
    """Stateful contract fixture: wire fields match Remux v0.29.0/source."""
    url = 'http://remux.example'

    def __init__(self):
        self.addons = []
        self.items = []
        self.calls = []
        self.enabled = {}
        self.fail_patch = False
        self.admin = True
        self.advertised = ['movie:top', 'series:top', 'movie:unrelated']

    def request(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path == '/users/me':
            return {'Id': 'admin1', 'Policy': {'IsAdministrator': self.admin}}
        if method == 'GET' and path.startswith('/items?'):
            return {'Items': copy.deepcopy(self.items), 'TotalRecordCount': len(self.items)}
        if path == '/addons':
            if method == 'GET':
                return copy.deepcopy(self.addons)
            addon = {'id': str(uuid.uuid4()), 'kind': body['preset']['kind'], 'config': body['preset']['config'],
                     'enabled': True, 'resources': body['resources'], 'types': body['types']}
            self.addons.append(addon)
            return copy.deepcopy(addon)
        if '/addons/' in path and path.endswith('/catalogs'):
            aid = path.split('/')[2]
            if method == 'GET':
                return [{'catalogId': f'addon:{aid}:{cid}', 'collectionId': str(uuid.uuid5(uuid.UUID(aid), cid)),
                         'enabled': self.enabled.get(f'addon:{aid}:{cid}', True), 'maxItems': 123}
                        for cid in self.advertised]
            for r in body:
                cid = r['catalogId'] if r['catalogId'].startswith('addon:') else f"addon:{aid}:{r['catalogId']}"
                self.enabled[cid] = r['enabled']
            return None
        if path == '/library/virtualfolders':
            item = {'Id': str(uuid.uuid4()), 'Name': body['Name'], 'Tags': [], 'Remux': {}}
            self.items.append(item)
            return {'ItemId': item['Id']}
        if method == 'PATCH':
            if self.fail_patch:
                self.fail_patch = False
                raise RemuxError('Simulated interrupted PATCH')
            item = next(i for i in self.items if i['Id'] == path.split('/')[-1])
            item.update(copy.deepcopy(body))
            return None
        if path.startswith('/collections/'):
            fid = path.split('ids=')[1]
            next(i for i in self.items if i['Id'] == fid)['ParentId'] = path.split('/')[2]
            return None
        if path == '/library/refresh':
            return None
        raise AssertionError((method, path, body))


class RemuxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ProfileStore(self.temp.name)
        self.remote = FakeRemux()
        self.service = RemuxService(self.store, lambda url, key: self.remote)

    def preview(self, raw=None):
        return self.service.preview(raw or setup_data(), {'original': URL}, None, self.remote.url, 'PRIVATE_API_KEY', 'Living room')

    def test_preview_is_read_only_and_never_leaks_connections(self):
        result = self.preview()
        self.assertTrue(result['canImport'])
        self.assertEqual(len(result['actions']), 2)
        self.assertTrue(all(method == 'GET' for method, _, _ in self.remote.calls))
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('PRIVATE_API_KEY', json.dumps(self.service.plans))

    def test_import_builds_dynamic_catalog_groups_and_repeat_updates(self):
        first = self.preview()
        result = self.service.apply(first['previewToken'], 'PRIVATE_API_KEY')
        self.assertTrue(result['success'], result)
        self.assertEqual(len(self.remote.items), 2)
        group, folder = self.remote.items
        self.assertEqual((group['CollectionType'], group['CollectionKind'], group['Promoted']), ('collections', 'manual', True))
        self.assertEqual(folder['ParentId'], group['Id'])
        self.assertFalse(folder['Promoted'])
        rule = folder['SmartFilter']['groups'][0]['rules'][0]
        self.assertEqual(rule['field'], 'catalog')
        uuid.UUID(rule['catalog_ids'][0])
        self.assertTrue(any(p == '/library/refresh' for _, p, _ in self.remote.calls))
        self.assertFalse(any('importcatalog' in p for _, p, _ in self.remote.calls))
        self.assertFalse(next(v for k, v in self.remote.enabled.items() if k.endswith('movie:unrelated')))
        raw = setup_data()
        raw[0]['title'] = 'Renamed'
        raw[0]['folders'][0]['title'] = 'New picks'
        second = self.preview(raw)
        self.assertTrue(all(a['action'] == 'update' for a in second['actions']))
        self.assertTrue(self.service.apply(second['previewToken'], 'key')['success'])
        self.assertEqual(len(self.remote.items), 2)
        self.assertEqual(len(self.remote.addons), 1)
        self.assertEqual(self.remote.items[0]['Name'], 'Renamed')

    def test_interrupted_creation_is_recovered_by_temporary_name(self):
        self.remote.fail_patch = True
        first = self.preview()
        self.assertFalse(self.service.apply(first['previewToken'], 'key')['success'])
        self.assertEqual(len(self.remote.items), 1)
        self.assertTrue(self.remote.items[0]['Name'].startswith('nuvio2fusion:'))
        # New process has no local ID database; matching survives restart.
        self.service = RemuxService(self.store, lambda url, key: self.remote)
        retry = self.preview()
        self.assertEqual(retry['actions'][0]['action'], 'update')
        self.assertTrue(self.service.apply(retry['previewToken'], 'key')['success'])
        self.assertEqual(len(self.remote.items), 2)

    def test_mixed_and_genre_queries_keep_original_provider(self):
        raw = setup_data()
        raw[0]['folders'][0]['sources'][0].update(type='all', genre='Drama')
        plan = plan_setup(raw, {'original': URL}, BridgePlan(self.store, 'http://192.168.1.10:7088'))
        feeds = plan['groups'][0]['folders'][0]['sources']
        self.assertEqual([f['type'] for f in feeds], ['movie', 'series'])
        token = plan['bridge']['manifestUrl'].split('/')[-2]
        saved = self.store.load(token)['sources'][0]
        self.assertEqual(saved['manifest'], URL)
        self.assertEqual(saved['type'], 'all')
        self.assertEqual(saved['extra'], {'genre': 'Drama'})
        self.assertNotIn('SECRET', json.dumps(plan['report']))

    def test_sources_authoritative_and_unsupported_folders_not_imported(self):
        raw = setup_data()
        f = raw[0]['folders'][0]
        f['catalogSources'] = f['sources']
        f['sources'] = []
        self.assertFalse(plan_setup(raw, {'original': URL})['groups'])
        f['sources'] = [{'provider': 'tmdb'}]
        plan = plan_setup(raw, {})
        self.assertEqual(plan['report']['omitted'], 1)
        self.assertFalse(plan['groups'])

    def test_missing_mapping_and_bad_structures(self):
        self.assertEqual(plan_setup(setup_data(), {})['report']['omitted'], 1)
        for value in ({'exportType': 'fusionWidgets', 'widgets': []}, [{'folders': 'bad'}]):
            with self.assertRaises(RemuxError):
                plan_setup(value, {})
        raw = setup_data()
        raw.append(copy.deepcopy(raw[0]))
        with self.assertRaisesRegex(RemuxError, 'Duplicate'):
            plan_setup(raw, {'original': URL})

    def test_multiple_catalogs_have_union_filter(self):
        raw = setup_data()
        raw[0]['folders'][0]['sources'].append({'addonId': 'original', 'type': 'series', 'catalogId': 'top'})
        first = self.preview(raw)
        self.assertTrue(self.service.apply(first['previewToken'], 'key')['success'])
        rule = self.remote.items[1]['SmartFilter']['groups'][0]['rules'][0]
        self.assertEqual(len(rule['catalog_ids']), 2)
        self.assertEqual(rule['op'], 'in')

    def test_matching_addon_disabled_or_missing_catalog_blocks_preview(self):
        self.remote.addons.append({'id': str(uuid.uuid4()), 'kind': 'stremio', 'config': {'manifest_url': URL}, 'enabled': False, 'resources': ['catalog']})
        with self.assertRaises(RemuxError):
            self.preview()
        self.remote.addons[0]['enabled'] = True
        self.remote.advertised = []
        with self.assertRaises(RemuxError):
            self.preview()

    def test_existing_addon_unrelated_catalogs_and_tags_are_preserved(self):
        first = self.preview()
        self.service.apply(first['previewToken'], 'key')
        self.remote.items[0]['Tags'].append('personal')
        self.remote.enabled = {k: True for k in self.remote.enabled}
        self.remote.calls.clear()
        second = self.preview()
        self.service.apply(second['previewToken'], 'key')
        self.assertIn('personal', self.remote.items[0]['Tags'])
        self.assertFalse(any(m == 'POST' and p.endswith('/catalogs') for m, p, b in self.remote.calls))
        self.assertFalse(any(m == 'DELETE' for m, p, b in self.remote.calls))

    def test_preview_expiry_replay_and_wrong_admin(self):
        first = self.preview()
        self.service.plans[first['previewToken']]['created'] -= 901
        self.assertFalse(self.service.apply(first['previewToken'], 'key')['success'])
        self.assertFalse(self.service.apply(first['previewToken'], 'key')['success'])
        second = self.preview()
        self.remote.admin = False
        self.assertFalse(self.service.apply(second['previewToken'], 'key')['success'])

    def test_no_duplicate_marker_can_silently_update(self):
        first = self.preview()
        self.service.apply(first['previewToken'], 'key')
        self.remote.items.append(copy.deepcopy(self.remote.items[0]))
        with self.assertRaisesRegex(RemuxError, 'Multiple'):
            self.preview()

    def test_api_preview_apply_and_validation_privacy(self):
        with patch.object(app.state, 'remux', self.service):
            client = TestClient(app)
            first = client.post('/api/remux/preview', json={'export_data': setup_data(), 'addon_urls': {'original': URL},
                'server_url': self.remote.url, 'api_key': 'PRIVATE_API_KEY', 'setup_name': 'Living room'})
            self.assertEqual(first.status_code, 200, first.text)
            response = client.post('/api/remux/import', json={'preview_token': first.json()['previewToken'], 'api_key': 'PRIVATE_API_KEY'})
            self.assertTrue(response.json()['success'], response.text)
            self.assertNotIn('PRIVATE_API_KEY', response.text)
            invalid = client.post('/api/remux/preview', json={'api_key': {'secret': 'PRIVATE_API_KEY'}})
            self.assertEqual(invalid.status_code, 422)
            self.assertNotIn('PRIVATE_API_KEY', invalid.text)
            denied = client.post('/api/remux/import', headers={'Origin': 'https://evil.example'}, json={})
            self.assertEqual(denied.status_code, 403)


class WireTests(unittest.TestCase):
    def setUp(self):
        self.received = []
        received = self.received
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                received.append((self.path, self.headers.get('X-Emby-Token')))
                if self.path.endswith('/redirect'):
                    self.send_response(302)
                    self.send_header('Location', '/stolen')
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.client = RemuxClient(f'http://127.0.0.1:{self.server.server_port}/base', 'PRIVATE_API_KEY')

    def test_header_and_basepath_on_real_http_transport(self):
        self.assertEqual(self.client.request('GET', '/users/me'), {'ok': True})
        self.assertEqual(self.received, [('/base/users/me', 'PRIVATE_API_KEY')])

    def test_redirect_never_forwards_api_key(self):
        with self.assertRaises(RemuxError):
            self.client.request('GET', '/redirect')
        self.assertEqual(len(self.received), 1)

    def test_metadata_address_and_invalid_key_rejected(self):
        with patch('app.remux.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('169.254.169.254', 80))]):
            with self.assertRaises(RemuxError):
                self.client.request('GET', '/users/me')
        with self.assertRaises(RemuxError):
            RemuxClient(self.client.url, 'key\r\nHeader: injected')


if __name__ == '__main__':
    unittest.main()
