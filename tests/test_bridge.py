import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.bridge import (BridgeError, BridgePlan, BridgeService, ProfileStore,
                        source_identity, public_base_url)
from app.fusion import convert_to_fusion
from app.main import app
from app.upstream import JsonFetcher, UpstreamError, permitted_ip


MANIFEST = 'https://addon.example.invalid/private-config/manifest.json?key=PRIVATE'


def raw_collection():
    return [{'id': 'franchises', 'title': 'Franchises', 'folders': [
        {'id': 'mixed-only', 'title': 'Mixed only', 'tileShape': 'LANDSCAPE',
         'coverImageUrl': 'https://art.example.invalid/a.jpg', 'sources': [
             {'provider': 'addon', 'addonId': 'aio-metadata', 'type': 'all', 'catalogId': 'mixed.list', 'genre': 'None'}]},
        {'id': 'mixed-and-normal', 'title': 'Both', 'sources': [
             {'addonId': 'aio-metadata', 'type': 'movie', 'catalogId': 'regular'},
             {'addonId': 'aio-metadata', 'type': 'all', 'catalogId': 'mixed.list', 'genre': 'None'}]},
        {'id': 'optional', 'title': 'Optional', 'sources': [
             {'addonId': 'optional.addon', 'type': 'movie', 'catalogId': 'unavailable'}]}]}]


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ProfileStore(self.temp.name)

    def plan(self):
        return BridgePlan(self.store, 'http://192.168.1.10:7088')

    def profile(self, fetch=None):
        plan = self.plan()
        sources = plan.add(MANIFEST, 'all', 'mixed.list', 'Science Fiction', 'Mixed')
        info = plan.finish()
        token = info['manifestUrl'].split('/')[-2]
        cid = sources[0]['payload']['catalogId'].split('::')[1]
        return BridgeService(self.store, fetch), token, cid

    def test_whole_mixed_folder_is_restored_without_changing_original_queries(self):
        raw = raw_collection()
        before = copy.deepcopy(raw)
        result = convert_to_fusion(raw, {'aio-metadata': MANIFEST}, self.plan(), True)
        folders = result['fusionConfig']['widgets'][0]['dataSource']['payload']['items']
        self.assertEqual([len(f['dataSources']) for f in folders], [2, 3])
        self.assertEqual([s['payload']['type'] for s in folders[0]['dataSources']], ['movie', 'series'])
        self.assertEqual(folders[0]['imageURL'], raw[0]['folders'][0]['coverImageUrl'])
        self.assertEqual(result['report']['counts'], {'preserved': 3, 'unsupported': 1})
        self.assertEqual(result['report']['bridgedSourceReferences'], 2)
        self.assertEqual(result['report']['omittedEmptyFolders'], 1)
        self.assertEqual(result['bridge']['catalogs'], 2)  # Reused list, not duplicate registrations.
        self.assertEqual(result['fusionConfig']['requiredAddons'], [MANIFEST, result['bridge']['manifestUrl']])
        self.assertNotIn('private-config', json.dumps(result['report']))
        self.assertNotIn('PRIVATE', json.dumps(result['report']))
        self.assertEqual(raw, before)
        self.assertTrue(result['report']['canExport'])
        self.assertFalse(result['report']['requiresPartialApproval'])

    def test_links_and_manifests_survive_fresh_store_and_process_state(self):
        service, token, cid = self.profile()
        original_manifest = service.manifest(token)
        self.assertTrue(original_manifest['id'].startswith('dev.nuvioexporter.'))
        self.assertEqual(original_manifest['version'], '3.1.0')
        reloaded = BridgeService(ProfileStore(self.temp.name), lambda _: {'metas': []})
        self.assertEqual(reloaded.manifest(token), original_manifest)
        self.assertEqual(reloaded.catalog(token, 'movie', cid), {'metas': []})
        self.assertNotIn('PRIVATE', json.dumps(original_manifest))
        self.assertNotIn('private-config', json.dumps(original_manifest))
        self.assertEqual(self.profile()[1], token)
        if os.name != 'nt':  # Windows permissions use ACLs rather than POSIX mode bits.
            self.assertEqual(os.stat(Path(self.temp.name) / 'bridge.sqlite3').st_mode & 0o777, 0o600)

    def test_fixed_type_profile_preserves_a_separate_genre_query(self):
        plan = self.plan()
        sources = plan.add(MANIFEST, 'series', 'anime', 'Action', 'Naruto', output_types=('series',))
        info = plan.finish()
        token = info['manifestUrl'].split('/')[-2]
        cid = sources[0]['payload']['catalogId'].split('::')[1]
        service = BridgeService(self.store, lambda _: {'metas': []})
        manifest = service.manifest(token)
        self.assertEqual([(c['type'], c['id']) for c in manifest['catalogs']], [('series', cid)])
        self.assertEqual(info['catalogs'], 1)
        self.assertEqual(service.catalog(token, 'series', cid, limit=100), {'metas': []})
        with self.assertRaises(KeyError):
            service.catalog(token, 'movie', cid)
        self.assertIn('genre=Action', service.upstream_url(self.store.load(token)['sources'][0], 0))

    def test_pagination_scans_past_pages_with_no_requested_type(self):
        calls = []
        pages = [
            [{'id': f'm{i}', 'type': 'movie'} for i in range(50)],
            [{'id': f's{i}', 'type': 'series'} for i in range(50)],
            [{'id': 'm50', 'type': 'movie'}, {'id': 's50', 'type': 'series'}], []]
        def fetch(url):
            calls.append(url)
            return {'metas': pages[len(calls) - 1]}
        service, token, cid = self.profile(fetch)
        first = service.catalog(token, 'series', cid)['metas']
        second = service.catalog(token, 'series', cid, 40)['metas']
        self.assertEqual([m['id'] for m in first + second], [f's{i}' for i in range(51)])
        movies = service.catalog(token, 'movie', cid)['metas'] + service.catalog(token, 'movie', cid, 40)['metas']
        self.assertEqual([m['id'] for m in movies], [f'm{i}' for i in range(51)])
        offsets = [parse_qs(urlsplit(u).path.rsplit('/', 1)[1][:-5])['skip'][0] for u in calls]
        self.assertEqual(offsets, ['0', '50', '100', '102'])
        self.assertTrue(all('/catalog/all/mixed.list/' in u for u in calls))
        self.assertTrue(all('genre=Science%20Fiction' in u for u in calls))
        self.assertTrue(all(urlsplit(u).query == 'key=PRIVATE' for u in calls))

    def test_repeated_non_paginated_page_does_not_duplicate_items(self):
        metas = [{'id': 'movie1', 'type': 'movie'}, {'id': 'series1', 'type': 'series'}]
        service, token, cid = self.profile(lambda _: {'metas': metas})
        self.assertEqual(service.catalog(token, 'movie', cid)['metas'], [metas[0]])
        self.assertEqual(service.catalog(token, 'series', cid)['metas'], [metas[1]])
        self.assertEqual(service.catalog(token, 'movie', cid, 40)['metas'], [])

    def test_failure_is_not_cached_as_an_empty_catalog(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if len(calls) == 1:
                raise UpstreamError('Original addon unavailable.')
            return {'metas': [{'id': 'movie1', 'type': 'movie'}]} if len(calls) == 2 else {'metas': []}
        service, token, cid = self.profile(fetch)
        with self.assertRaises(UpstreamError):
            service.catalog(token, 'movie', cid)
        self.assertEqual(service.catalog(token, 'movie', cid)['metas'][0]['id'], 'movie1')
        self.assertEqual(calls[0], calls[1])

    def test_bounded_scan_reports_retry_then_continues_without_losing_pages(self):
        calls = []
        def fetch(url):
            calls.append(url)
            i = len(calls)
            return {'metas': [{'id': str(i), 'type': 'movie' if i == 4 else 'series'}]} if i <= 4 else {'metas': []}
        service, token, cid = self.profile(fetch)
        with patch('app.bridge.MAX_SCAN_PAGES', 2):
            with self.assertRaisesRegex(UpstreamError, 'Retry'):
                service.catalog(token, 'movie', cid)
            with self.assertRaises(UpstreamError):
                service.catalog(token, 'movie', cid)
            self.assertEqual(service.catalog(token, 'movie', cid)['metas'], [{'id': '4', 'type': 'movie'}])
        self.assertEqual(len(calls), 5)

    def test_unknown_item_types_are_reported_without_guessing(self):
        pages = iter([{'metas': [{'id': 'x', 'type': 'all'}, {'id': 'y', 'type': 'anime.series'}]}, {'metas': []}])
        service, token, cid = self.profile(lambda _: next(pages))
        result = service.catalog(token, 'series', cid)
        self.assertEqual(result['metas'], [{'id': 'y', 'type': 'series'}])
        self.assertIn('1 items', result['nuvioexporterWarning'])

    def test_limits_fail_loudly_instead_of_truncating_a_catalog(self):
        service, token, cid = self.profile(lambda _: {'metas': [{'id': '1', 'type': 'movie'}]})
        with patch('app.bridge.MAX_CACHED_BYTES', 1), self.assertRaisesRegex(UpstreamError, 'limit'):
            service.catalog(token, 'movie', cid)

    def test_profile_path_and_query_cannot_be_used_as_an_open_proxy(self):
        for token in ('../bridge', 'a' * 31, 'a' * 33):
            with self.assertRaises(KeyError):
                self.store.load(token)
        for url in ('file:///tmp', 'https://user:pass@example.com', 'http://example.com/?url=x', 'https://example.com/#x'):
            with self.assertRaises(ValueError):
                public_base_url(url)
        for cid in ('../secret', 'list?url=x', 'list/skip=100', 'list/genre=a&genre=b'):
            with self.assertRaises(ValueError):
                source_identity(MANIFEST, 'all', cid, '')

    def test_encoded_original_genre_is_not_overwritten(self):
        identity = source_identity(MANIFEST, 'all', 'list/genre=Sci%20Fi', 'Drama')
        self.assertEqual(identity['extra'], {'genre': 'Sci Fi'})

    def test_plain_conversion_does_not_create_storage(self):
        convert_to_fusion(raw_collection(), {'aio-metadata': MANIFEST})
        self.assertFalse((Path(self.temp.name) / 'bridge.sqlite3').exists())

    def test_reexporting_bridge_only_layout_keeps_original_metadata_addon(self):
        raw = raw_collection()
        raw[0]['folders'] = raw[0]['folders'][:1]
        first = convert_to_fusion(raw, {'aio-metadata': MANIFEST}, self.plan())['fusionConfig']
        second = convert_to_fusion(first, bridge=self.plan())['fusionConfig']
        self.assertEqual(second, first)

    def test_api_can_create_persist_and_serve_a_fixed_profile(self):
        original_service = app.state.bridge
        self.addCleanup(setattr, app.state, 'bridge', original_service)
        app.state.bridge = BridgeService(self.store, lambda _: {'metas': []})
        client = TestClient(app)
        response = client.post('/api/fusion/convert', json={'export_data': raw_collection(),
            'addon_urls': {'aio-metadata': MANIFEST}, 'bridge_url': 'http://testserver', 'omit_empty_folders': True})
        self.assertEqual(response.status_code, 200)
        output = response.json()
        url = output['bridge']['manifestUrl']
        manifest = client.get(url)
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.headers['access-control-allow-origin'], '*')
        self.assertEqual({c['type'] for c in manifest.json()['catalogs']}, {'movie', 'series'})
        cat = manifest.json()['catalogs'][0]
        endpoint = url.removesuffix('/manifest.json') + f'/catalog/{cat["type"]}/{cat["id"]}'
        self.assertEqual(client.get(endpoint + '.json').json(), {'metas': []})
        self.assertEqual(client.get(endpoint + '/skip=0.json').status_code, 200)
        self.assertEqual(client.get(endpoint + '.json?skip=0').status_code, 200)
        # Fusion's native catalog client sends these generic query parameters
        # on its initial request. The fixed adapter must accept them without
        # allowing arbitrary upstream query options.
        self.assertEqual(client.get(endpoint + '.json?limit=100&extra=%7B%7D').status_code, 200)
        self.assertEqual(client.get(endpoint + '.json?limit=20&extra=%7B%22skip%22%3A0%7D').status_code, 200)
        for suffix in ('/skip=-1.json', '/url=https%3A%2F%2Fexample.com.json',
                       '.json?skip=0&skip=1', '.json?limit=0', '.json?limit=101',
                       '.json?extra=%7B%22genre%22%3A%22Action%22%7D'):
            self.assertIn(client.get(endpoint + suffix).status_code, (400, 404))
        self.assertEqual(client.get('/bridge/' + 'a' * 32 + '/manifest.json').status_code, 404)


class UpstreamTests(unittest.TestCase):
    def transport(self, responses, max_bytes=1000):
        fetch = JsonFetcher(max_bytes=max_bytes)
        sockets = patch('app.upstream.socket.socket').start()
        self.addCleanup(patch.stopall)
        dns = patch('app.upstream.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('1.1.1.1', 443))]).start()
        connection = MagicMock()
        connection.getresponse.side_effect = responses
        factory = patch('app.upstream.http.client.HTTPConnection', return_value=connection).start()
        fetch.context = MagicMock()
        return fetch, sockets, dns, connection, factory

    @staticmethod
    def response(body=b'{"metas":[]}', status=200, headers=None):
        response = MagicMock(status=status)
        response.getheader.side_effect = lambda name, default=None: (headers or {}).get(name, default)
        response.read1.side_effect = [body, b'']
        return response

    def test_tls_connects_only_to_checked_address_and_keeps_original_sni(self):
        fetch, sockets, dns, conn, factory = self.transport([self.response()])
        self.assertEqual(fetch(MANIFEST), {'metas': []})
        sockets.return_value.connect.assert_called_once_with(('1.1.1.1', 443))
        dns.assert_called_once()
        fetch.context.wrap_socket.assert_called_once_with(sockets.return_value, server_hostname='addon.example.invalid')
        factory.assert_called_once_with('addon.example.invalid', 443, timeout=15)
        self.assertEqual(conn.request.call_args.args, ('GET', '/private-config/manifest.json?key=PRIVATE'))
        self.assertTrue(JsonFetcher().context.check_hostname)

    def test_redirect_to_other_origin_is_rejected_before_second_connection(self):
        fetch, _, dns, conn, _ = self.transport([self.response(status=302, headers={'Location': 'https://other.example/collect'})])
        with self.assertRaisesRegex(UpstreamError, 'another origin'):
            fetch(MANIFEST)
        dns.assert_called_once()
        conn.close.assert_called_once()

    def test_same_origin_redirect_is_checked_again_and_can_succeed(self):
        fetch, _, dns, conn, _ = self.transport([
            self.response(status=302, headers={'Location': '/updated.json'}), self.response()])
        self.assertEqual(fetch(MANIFEST), {'metas': []})
        self.assertEqual(dns.call_count, 2)
        self.assertEqual(conn.request.call_args.args, ('GET', '/updated.json'))

    def test_oversized_stream_without_length_and_invalid_json_fail_safely(self):
        for response in (self.response(body=b'x' * 11), self.response(body=b'not json')):
            with self.subTest():
                fetch, _, _, conn, _ = self.transport([response], max_bytes=10)
                with self.assertRaises(UpstreamError):
                    fetch(MANIFEST)
                conn.close.assert_called_once()
                patch.stopall()

    def test_reserved_and_private_addresses_are_blocked_by_default(self):
        for address in ('127.0.0.1', '10.0.0.1', '192.168.1.1', '172.16.0.1', '169.254.169.254',
                        '::1', '::ffff:127.0.0.1', 'fe80::1', '0.0.0.0', '224.0.0.1', '100.64.0.1'):
            with self.subTest(address=address):
                self.assertFalse(permitted_ip(address))
        self.assertTrue(permitted_ip('1.1.1.1'))
        self.assertTrue(permitted_ip('192.168.1.1', True))
        self.assertFalse(permitted_ip('169.254.169.254', True))
        self.assertFalse(permitted_ip('127.0.0.1', True))

    def test_unsafe_dns_is_rejected_before_any_socket_connection(self):
        answer = [(2, 1, 6, '', ('169.254.169.254', 80))]
        fetch = JsonFetcher()
        with patch('app.upstream.socket.getaddrinfo', return_value=answer), patch('app.upstream.socket.socket') as sock:
            with self.assertRaisesRegex(UpstreamError, 'blocked'):
                fetch('http://public.example/private-config/manifest.json')
            sock.assert_not_called()

    def test_network_failure_does_not_echo_secret_url(self):
        with patch('app.upstream.socket.getaddrinfo', side_effect=OSError(MANIFEST)):
            with self.assertRaises(UpstreamError) as caught:
                JsonFetcher()(MANIFEST)
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertNotIn('private-config', str(caught.exception))
