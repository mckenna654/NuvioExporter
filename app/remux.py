"""Nuvio setup planning and Remux synchronization (never snapshot catalog items)."""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import secrets
import socket
import ssl
import threading
import time
import uuid
from collections import Counter
from urllib.parse import urlencode, urlsplit

from app import USER_AGENT
from app.bridge import BridgePlan, canonical, public_base_url
from app.fusion import FusionConversion, TYPE_ALIASES, is_web_url, manifest_url, string
from app.upstream import permitted_ip


class RemuxError(Exception):
    """Only safe, credential-free messages cross the API boundary."""


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()[:32]


def remux_url(value):
    try:
        value = public_base_url(value)
        p = urlsplit(value)
        if any(part in {'.', '..'} for part in p.path.split('/')) or '%' in p.path:
            raise ValueError
        return value
    except (ValueError, AttributeError):
        raise RemuxError('Use the Remux HTTP(S) server address, optionally with its base path; omit /admin, credentials and query strings.') from None


class RemuxClient:
    """Bounded, DNS-pinned requests. Never forward the API key on redirects."""
    def __init__(self, url, api_key):
        self.url = remux_url(url)
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096 or not api_key.isascii() or any(ord(c) < 33 for c in api_key):
            raise RemuxError('Enter a valid Remux API key.')
        self.api_key = api_key

    def request(self, method, path, body=None):
        if not path.startswith('/') or path.startswith('//'):
            raise RemuxError('Invalid Remux API path.')
        p = urlsplit(self.url)
        conn = None
        try:
            port = p.port or (443 if p.scheme == 'https' else 80)
            addresses = socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)
            # Remux is commonly self-hosted on LAN or localhost. Link-local,
            # multicast and reserved destinations remain blocked.
            if not addresses or any(not (permitted_ip(a[4][0], True) or ipaddress.ip_address(a[4][0]).is_loopback) for a in addresses):
                raise RemuxError('The Remux address must resolve to a public, LAN or loopback server.')
            deadline = time.monotonic() + 45
            conn = http.client.HTTPConnection(p.hostname, port, timeout=45)
            last_error = None
            for family, kind, protocol, _, address in addresses:
                sock = socket.socket(family, kind, protocol)
                try:
                    sock.settimeout(max(.1, deadline - time.monotonic()))
                    sock.connect(address)
                    if p.scheme == 'https':
                        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=p.hostname)
                    conn.sock = sock
                    break
                except OSError as exc:
                    sock.close()
                    last_error = exc
            if conn.sock is None:
                raise last_error or OSError()
            headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity',
                       'X-Emby-Token': self.api_key, 'User-Agent': USER_AGENT}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers['Content-Type'] = 'application/json'
            conn.request(method, p.path.rstrip('/') + path, body=data, headers=headers)
            response = conn.getresponse()
            if response.status in {401, 403}:
                raise RemuxError('Remux rejected authentication. Use an API key with administrator access.')
            if not 200 <= response.status < 300:
                raise RemuxError(f'Remux returned HTTP {response.status}. Check the server version and address. Redirects are not followed.')
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                raise RemuxError('Remux returned an unsupported compressed response.')
            content = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                if conn.sock:
                    conn.sock.settimeout(remaining)
                chunk = response.read1(min(65536, 8 * 1024 * 1024 + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > 8 * 1024 * 1024:
                    raise RemuxError('Remux response exceeds 8 MiB.')
            return json.loads(content) if content else None
        except RemuxError:
            raise
        except (OSError, ValueError, http.client.HTTPException, RecursionError):
            raise RemuxError('Could not complete the Remux request. Check connectivity and TLS certificates. If importing, preview again before retrying; some changes may already have applied.') from None
        finally:
            if conn:
                conn.close()


def plan_setup(export_data, addon_urls, bridge=None):
    """Read Nuvio directly; Fusion's layout/output restrictions do not apply."""
    if isinstance(export_data, dict):
        rows = export_data.get('collections', [export_data] if 'folders' in export_data else None)
    else:
        rows = export_data
    if not isinstance(rows, list) or len(rows) > 1000:
        raise RemuxError('Remux import needs a Nuvio collections export, not Fusion widget JSON or a manifest.')
    resolver = FusionConversion(addon_urls)
    groups, warnings, records = [], [], []
    seen = set()

    def ident(raw, path, parent=''):
        original = string(raw.get('id'))
        if not original:
            warnings.append(f'{path}: missing ID; position is used. Reordering this entry may create a new collection.')
        key = digest([parent, original or path])
        if key in seen:
            raise RemuxError('Duplicate collection/folder IDs need repair before import; matching by name could update the wrong collection.')
        seen.add(key)
        return key

    def visual(raw, path, supported=()):
        allowed = {'id', 'title', 'folders', 'sources', 'catalogSources', *supported}
        fields = [k for k, v in raw.items() if k not in allowed and v not in (None, '', False, [], {})]
        if fields:
            warnings.append(f'{path}: appearance/settings not transferred: ' + ', '.join(fields) + '.')

    for i, row in enumerate(rows):
        path = f'collections[{i}]'
        if not isinstance(row, dict) or not isinstance(row.get('folders'), list):
            raise RemuxError('Each Nuvio collection must contain a folders array.')
        group = {'key': ident(row, path), 'name': string(row.get('title')) or 'Untitled', 'order': i,
                 'promoted': row.get('pinToTop') is not False, 'folders': []}
        visual(row, path, {'pinToTop'})
        for j, folder in enumerate(row['folders']):
            fp = f'{path}.folders[{j}]'
            if not isinstance(folder, dict):
                raise RemuxError('Each folder must be an object.')
            if len(seen) >= 10000:
                raise RemuxError('The setup exceeds 10,000 collections/folders.')
            f = {'key': ident(folder, fp, group['key']), 'name': string(folder.get('title')) or 'Untitled',
                 'order': j, 'sources': [], 'images': {}}
            image_fields = {'coverImageUrl': 'Primary', 'heroBackdropUrl': 'Backdrop', 'titleLogoUrl': 'Logo'}
            for field, kind in image_fields.items():
                value = string(folder.get(field))
                if value:
                    if is_web_url(value):
                        f['images'][kind] = value
                    else:
                        warnings.append(f'{fp}: {field} is not a supported HTTP(S) image URL and was omitted.')
            visual(folder, fp, image_fields)
            sources = folder.get('sources')
            if sources is None:
                sources = folder.get('catalogSources', [])
            if not isinstance(sources, list):
                raise RemuxError('Folder sources must be an array.')
            for k, raw in enumerate(sources):
                if len(records) >= 10000:
                    raise RemuxError('The setup exceeds 10,000 source references.')
                record = {'path': f'{fp}.sources[{k}]', 'name': f['name'], 'status': 'omitted', 'reason': ''}
                records.append(record)
                try:
                    if not isinstance(raw, dict) or string(raw.get('provider') or 'addon').lower() != 'addon':
                        raise ValueError('Native TMDB/Trakt recipes are not supported; expose them through an addon first.')
                    allowed = {'provider', 'addonId', 'addonBaseUrl', 'manifestUrl', 'addonName', 'type', 'catalogId', 'genre', 'catalogName', 'title', 'name', 'aiometadata'}
                    if any(k not in allowed and v not in (None, '', {}, []) for k, v in raw.items()):
                        raise ValueError('Additional source query options are not supported.')
                    url = resolver.resolve_addon(raw)
                    if not url:
                        raise ValueError('Connect this source’s original addon URL before importing.')
                    typ = string(raw.get('type')).lower()
                    typ = TYPE_ALIASES.get(typ, typ)
                    cid = string(raw.get('catalogId'))
                    if '::' in cid:
                        prefix, cid = cid.split('::', 1)
                        if TYPE_ALIASES.get(prefix, prefix) != typ:
                            raise ValueError('The catalog prefix and media type disagree.')
                    if not cid or not typ or any(c in cid for c in '?#'):
                        raise ValueError('Missing or unsupported catalog ID/media type.')
                    genre = raw.get('genre')
                    if genre is not None and not isinstance(genre, str):
                        raise ValueError('Genre must be text.')
                    genre = string(genre)
                    if genre.lower() == 'none':
                        genre = ''
                    record_index = len(records) - 1
                    if typ not in {'movie', 'series'} or genre or '/' in cid:
                        if not bridge:
                            raise ValueError('Enable the compatibility addon to preserve this mixed or genre-filtered query.')
                        feeds = bridge.add(url, typ, cid, genre, string(raw.get('catalogName')) or f['name'],
                                           output_types=(typ,) if typ in {'movie', 'series'} else None)
                        # BridgePlan fills manifest URLs when finish() persists the profile.
                        for feed in feeds:
                            f['sources'].append({**feed['payload'], '_record': record_index})
                    else:
                        f['sources'].append({'addonId': url, 'catalogId': f'{typ}::{cid}', 'type': typ,
                                             '_record': record_index})
                    record.update(status='kept', reason='Catalog query preserved; Remux will refresh its contents through the addon.')
                except ValueError:
                    # URL validators may include input in exceptions; never reflect it.
                    record['reason'] = 'Unsupported source or missing addon URL. Check provider, catalog type, genre options and compatibility mode.'
            if f['sources']:
                group['folders'].append(f)
            else:
                warnings.append(f'{fp}: omitted because no usable catalog sources remain.')
        if group['folders']:
            groups.append(group)
    bridge_info = bridge.finish() if bridge else None
    counts = Counter(r['status'] for r in records)
    warnings += ['Folder covers, backdrops and logos are copied to Remux. Nuvio tile shapes, hidden titles, focus effects and view modes have no Jellyfin equivalent.',
                 'Items appear after Remux refreshes enabled catalogs, subject to its catalog limits and metadata support.',
                 'Removed or omitted folders from earlier imports are retained in Remux. This importer never deletes your collections.']
    return {'groups': groups, 'bridge': bridge_info, 'report': {'groups': len(groups),
            'folders': sum(len(g['folders']) for g in groups), 'kept': counts['kept'], 'omitted': counts['omitted'],
            'warnings': warnings, 'items': records}}


def get_collections(client):
    items = []
    for start in range(0, 20000, 500):
        page = client.request('GET', f'/items?includeItemTypes=BoxSet&recursive=true&includeChildless=true&fields=Tags&startIndex={start}&limit=500')
        if not isinstance(page, dict) or not isinstance(page.get('Items'), list):
            raise RemuxError('Remux did not return a supported collection listing.')
        batch = page['Items']
        items.extend(batch)
        if len(batch) < 500:
            return items
    raise RemuxError('Too many Remux collections to safely match this import.')


def marker(scope, key):
    return 'nuvioexporter:' + scope + ':' + key


def marker_aliases(scope, key):
    # Recognize the retired marker so an existing Remux setup is migrated
    # instead of duplicated when it is imported again.
    return marker(scope, key), 'nuvio' + '2fusion:' + scope + ':' + key


def image_marker(kind, url):
    return marker('image', kind.lower() + ':' + digest(url))


def match_collection(items, tags):
    # A temporary unique name recovers interrupted creation before PATCH sets tags.
    tags = set(tags)
    found = [i for i in items if tags.intersection(i.get('Tags') or []) or i.get('Name') in tags]
    if len(found) > 1:
        raise RemuxError('Multiple Remux collections have the same import marker. Resolve the duplicate before importing.')
    return found[0] if found else None


def uuid_text(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError):
        raise RemuxError('Remux returned an invalid resource identifier.') from None


class RemuxService:
    def __init__(self, store, client_factory=RemuxClient):
        self.store = store
        self.client_factory = client_factory
        self.plans = {}
        self.lock = threading.Lock()

    def preview(self, export_data, addon_urls, bridge_url, server_url, api_key, setup_name):
        if not string(setup_name) or len(setup_name) > 100:
            raise RemuxError('Give this setup a name of 1–100 characters. Reuse it for future updates.')
        bridge = BridgePlan(self.store, bridge_url) if bridge_url else None
        plan = plan_setup(export_data, addon_urls, bridge)
        client = self.client_factory(server_url, api_key)
        user = client.request('GET', '/users/me')
        if not isinstance(user, dict) or not user.get('Policy', {}).get('IsAdministrator'):
            raise RemuxError('Use a Remux administrator API key.')
        addons = client.request('GET', '/addons')
        if not isinstance(addons, list):
            raise RemuxError('The server does not expose Remux addon APIs.')
        items = get_collections(client)
        scope = digest(string(setup_name))
        sources = self.sources(plan)
        addon_actions = []
        for url in sources:
            addon = self.find_addon(addons, url)
            if addon:
                self.check_addon(addon)
                catalogs, missing = self.catalogs(client, addon, sources[url])
                self.prune_unavailable(plan, url, missing)
            remaining = self.sources(plan).get(url, set())
            if remaining:
                addon_actions.append({'action': 'reuse' if addon else 'install', 'catalogs': len(remaining)})
        actions = []
        for group in plan['groups']:
            for node in [group, *group['folders']]:
                existing = match_collection(items, marker_aliases(scope, node['key']))
                actions.append({'name': node['name'], 'kind': 'group' if node is group else 'collection',
                                'action': 'update' if existing else 'create'})
        public = {'report': plan['report'], 'actions': actions, 'addons': addon_actions,
                  'canImport': bool(plan['groups']), 'usesBridge': bool(plan['bridge']),
                  'setupName': setup_name, 'serverUrl': client.url}
        # API keys never enter the plan cache or persistent profile database.
        with self.lock:
            now = time.monotonic()
            self.plans = {k: v for k, v in self.plans.items() if now - v['created'] < 900}
            if len(self.plans) >= 8:
                raise RemuxError('Too many pending previews. Wait 15 minutes or restart the service.')
            token = secrets.token_urlsafe(24)
            self.plans[token] = {'plan': plan, 'scope': scope, 'url': client.url, 'created': now,
                                 'userId': user.get('Id'), 'public': public}
        return {**public, 'previewToken': token}

    @staticmethod
    def sources(plan):
        result = {}
        for g in plan['groups']:
            for f in g['folders']:
                for source in f['sources']:
                    typ, cid = source['catalogId'].split('::', 1)
                    result.setdefault(source['addonId'], set()).add(f'{typ}:{cid}')
        return result

    @staticmethod
    def find_addon(addons, url):
        found = []
        for a in addons:
            if a.get('kind') == 'stremio':
                try:
                    if manifest_url(a.get('config', {}).get('manifest_url')) == url:
                        found.append(a)
                except ValueError:
                    pass
        if len(found) > 1:
            raise RemuxError('Multiple installed Remux addons match a source URL. Resolve the duplicate before importing.')
        return found[0] if found else None

    @staticmethod
    def check_addon(addon):
        if not addon.get('enabled') or 'catalog' not in addon.get('resources', []):
            raise RemuxError('A matching addon is disabled or lacks the catalog resource. Enable it in Remux, then preview again.')

    @staticmethod
    def catalogs(client, addon, requested):
        aid = uuid_text(addon.get('id'))
        rows = client.request('GET', f'/addons/{aid}/catalogs')
        if not isinstance(rows, list):
            raise RemuxError('Remux did not return addon catalogs.')
        index = {r.get('catalogId'): r for r in rows}
        result = {}
        missing = set()
        for local_id in requested:
            if addon.get('types') and local_id.split(':', 1)[0] not in addon['types']:
                raise RemuxError('An installed addon excludes a required media type. Update its enabled types in Remux.')
            row = index.get(f'addon:{aid}:{local_id}')
            if not row or not row.get('collectionId'):
                missing.add(local_id)
                continue
            result[local_id] = {**row, 'collectionId': uuid_text(row['collectionId'])}
        return result, missing

    @staticmethod
    def prune_unavailable(plan, addon_url, missing):
        """Drop only catalogs an installed addon no longer advertises."""
        if not missing:
            return
        removed = 0
        removed_folders = []
        kept_groups = []
        for group in plan['groups']:
            kept_folders = []
            for folder in group['folders']:
                kept_sources = []
                for source in folder['sources']:
                    typ, cid = source['catalogId'].split('::', 1)
                    unavailable = source['addonId'] == addon_url and f'{typ}:{cid}' in missing
                    if unavailable:
                        removed += 1
                        record_index = source.get('_record')
                        if isinstance(record_index, int) and record_index < len(plan['report']['items']):
                            plan['report']['items'][record_index].update(
                                status='omitted',
                                reason='The configured addon no longer advertises this catalog; no substitute was used.')
                    else:
                        kept_sources.append(source)
                folder['sources'] = kept_sources
                if kept_sources:
                    kept_folders.append(folder)
                else:
                    removed_folders.append(folder['name'])
            group['folders'] = kept_folders
            if kept_folders:
                kept_groups.append(group)
        plan['groups'] = kept_groups
        plan['report']['groups'] = len(kept_groups)
        plan['report']['folders'] = sum(len(g['folders']) for g in kept_groups)
        counts = Counter(r['status'] for r in plan['report']['items'])
        plan['report']['kept'] = counts['kept']
        plan['report']['omitted'] = counts['omitted']
        plan['report']['warnings'].append(
            f'{removed} source catalog reference(s) are no longer advertised by the configured addon and were omitted; no substitute was used.')
        if removed_folders:
            plan['report']['warnings'].append(
                f'{len(removed_folders)} folder(s) were omitted because none of their source catalogs are currently advertised: '
                + ', '.join(removed_folders) + '.')

    def apply(self, token, api_key):
        if not self.lock.acquire(blocking=False):
            raise RemuxError('Another import is running. Wait for it to finish before previewing again.')
        completed = []
        image_failures = 0
        try:
            cached = self.plans.pop(token, None)
            if not cached or time.monotonic() - cached['created'] >= 900:
                raise RemuxError('This preview expired or was already used. Preview the setup again.')
            plan, scope = cached['plan'], cached['scope']
            if not plan['groups']:
                raise RemuxError('No usable collections to import.')
            client = self.client_factory(cached['url'], api_key)
            user = client.request('GET', '/users/me')
            if not user.get('Policy', {}).get('IsAdministrator') or user.get('Id') != cached['userId']:
                raise RemuxError('The Remux administrator changed. Preview with the new key first.')
            addons = client.request('GET', '/addons')
            items = get_collections(client)
            catalog_map = {}
            for url, requested in self.sources(plan).items():
                addon = self.find_addon(addons, url)
                installed = addon is None
                if addon is None:
                    addon = client.request('POST', '/addons', {'name': 'NuvioExporter catalogs',
                        'preset': {'kind': 'stremio', 'config': {'manifest_url': url}},
                        'resources': ['catalog'], 'types': [], 'isDefault': True})
                    addons.append(addon)
                    completed.append('Installed a catalog addon')
                self.check_addon(addon)
                catalogs, missing = self.catalogs(client, addon, requested)
                self.prune_unavailable(plan, url, missing)
                updates = [{'catalogId': k, 'enabled': True, 'maxItems': r.get('maxItems')}
                           for k, r in catalogs.items() if not r.get('enabled')]
                if installed:
                    # A new addon can advertise hundreds of unrelated catalogs.
                    # Disable those on this new instance; never alter unrelated
                    # catalog settings on an addon the user already installed.
                    aid = uuid_text(addon['id'])
                    all_rows = client.request('GET', f'/addons/{aid}/catalogs')
                    selected = {r['catalogId'] for r in catalogs.values()}
                    updates = [{'catalogId': r['catalogId'], 'enabled': r['catalogId'] in selected,
                                'maxItems': r.get('maxItems')} for r in all_rows]
                if updates:
                    client.request('POST', '/addons/' + uuid_text(addon['id']) + '/catalogs', updates)
                    completed.append('Enabled source catalogs')
                catalog_map[url] = catalogs

            if not plan['groups']:
                raise RemuxError('No source catalogs in this setup are currently advertised by their configured addons.')

            def upsert(node, group=False):
                nonlocal image_failures
                tag = marker(scope, node['key'])
                aliases = marker_aliases(scope, node['key'])
                existing = match_collection(items, aliases)
                action = 'Updated ' if existing else 'Created '
                if existing:
                    item_id = uuid_text(existing['Id'])
                else:
                    # Unique temporary name makes an uncertain POST recoverable on retry.
                    info = client.request('POST', '/library/virtualfolders', {'Name': tag,
                        'CollectionType': 'collections' if group else 'mixed',
                        'CollectionKind': 'manual' if group else 'smart', 'Promoted': True})
                    item_id = uuid_text(info.get('ItemId'))
                    existing = {'Id': item_id, 'Name': tag, 'Tags': []}
                    items.append(existing)
                patch = {'Name': node['name'], 'CollectionType': 'collections' if group else 'mixed',
                    'CollectionKind': 'manual' if group else 'smart', 'Promoted': node.get('promoted', False) if group else False,
                    'SortOrder': node['order'], 'Tags': list(dict.fromkeys([
                        *(t for t in (existing.get('Tags') or []) if t not in aliases), tag]))}
                if not group:
                    ids = []
                    for source in node['sources']:
                        typ, cid = source['catalogId'].split('::', 1)
                        ids.append(catalog_map[source['addonId']][f'{typ}:{cid}']['collectionId'])
                    patch['SmartFilter'] = {'match_mode': 'all', 'groups': [{'match_mode': 'any',
                        'rules': [{'field': 'catalog', 'op': 'in', 'catalog_ids': list(dict.fromkeys(ids))}]}]}
                client.request('PATCH', '/items/' + item_id, patch)
                existing.update(Name=node['name'], Tags=patch['Tags'])
                synced = 0
                if not group:
                    tags = list(patch['Tags'])
                    for kind, url in node.get('images', {}).items():
                        image_tag = image_marker(kind, url)
                        prefix = marker('image', kind.lower() + ':')
                        if image_tag in tags:
                            continue
                        try:
                            query = urlencode({'Type': kind, 'ImageUrl': url})
                            client.request('POST', f'/items/{item_id}/remoteimages/download?{query}')
                        except RemuxError:
                            image_failures += 1
                            continue
                        tags = [t for t in tags if not t.startswith(prefix)]
                        tags.append(image_tag)
                        synced += 1
                    if synced:
                        client.request('PATCH', '/items/' + item_id, {'Tags': tags})
                        existing['Tags'] = tags
                        completed.append(f'Synced {synced} artwork image(s) for {node["name"]}')
                completed.append(action + node['name'])
                return item_id

            for group in plan['groups']:
                gid = upsert(group, True)
                for folder in group['folders']:
                    fid = upsert(folder)
                    client.request('POST', f'/collections/{gid}/items?ids={fid}')
            client.request('POST', '/library/refresh')
            image_note = (f' {image_failures} artwork image(s) could not be copied; reimport later to retry.'
                          if image_failures else '')
            return {'success': True, 'completed': completed, 'refreshQueued': True,
                    'imageFailures': image_failures,
                    'message': 'Setup imported. Remux library refresh was requested; catalogs may take time to populate. Existing playback/metadata addons are still needed.' + image_note}
        except RemuxError as exc:
            return {'success': False, 'completed': completed, 'refreshQueued': False,
                    'message': str(exc) + ' Some changes may already have applied. Preview again to reconcile existing collections before retrying.'}
        finally:
            self.lock.release()
