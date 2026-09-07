"""Persistent, catalog-only compatibility addon for imported catalog queries.

Profiles contain original URLs on disk. Public addon URLs carry random bearer
tokens, never the upstream configuration itself. Profiles survive restarts;
catalog cache is bounded, in memory, and expires after five minutes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import closing
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from app import VERSION
from app.upstream import JsonFetcher, UpstreamError


PAGE_SIZE = 40
MAX_SCAN_PAGES = 12
MAX_CACHED_ITEMS = 10000
MAX_CACHED_BYTES = 8 * 1024 * 1024
TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_-]{32}')
MEDIA_TYPES = ('movie', 'series')


class BridgeError(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def public_base_url(value):
    value = value.strip().rstrip('/')
    p = urlsplit(value)
    if (p.scheme not in {'http', 'https'} or not p.hostname or p.username or
            p.password or p.query or p.fragment or any(ord(c) < 33 for c in value)):
        raise ValueError('Use the HTTP(S) address of NuvioExporter reachable from your Fusion devices.')
    p.port
    return value


def source_identity(manifest, typ, catalog_id, genre):
    # A catalog id is one path component; older exports can append genre extras.
    cid, separator, extras = catalog_id.partition('/')
    if not cid or cid in {'.', '..'} or any(c in cid for c in '?#'):
        raise ValueError('Unsupported catalog path.')
    fixed = {}
    if separator:
        pairs = parse_qsl(extras, keep_blank_values=True, strict_parsing=True)
        if not pairs or any(k != 'genre' for k, _ in pairs) or len(pairs) != len(dict(pairs)):
            raise ValueError('Unsupported encoded catalog options.')
        fixed.update(pairs)
    if genre and 'genre' not in fixed:
        fixed['genre'] = genre
    return {'manifest': manifest, 'type': typ, 'catalog': unquote(cid), 'extra': fixed}


class ProfileStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.Lock()

    def _connect(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.directory / 'bridge.sqlite3'
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        db = sqlite3.connect(path, timeout=5)
        db.execute('CREATE TABLE IF NOT EXISTS profiles (token TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, config TEXT NOT NULL)')
        return db

    def save(self, sources):
        config = canonical({'version': 1, 'sources': sorted(sources, key=lambda s: s['id'])})
        if len(config) > 2 * 1024 * 1024:
            raise BridgeError('The compatibility profile is too large.')
        fingerprint = hashlib.sha256(config.encode()).hexdigest()
        try:
            with self.lock, closing(self._connect()) as db, db:
                row = db.execute('SELECT token FROM profiles WHERE fingerprint=?', (fingerprint,)).fetchone()
                if row:
                    return row[0]
                if db.execute('SELECT count(*) FROM profiles').fetchone()[0] >= 200:
                    raise BridgeError('The compatibility profile limit was reached. Back up and manage your appdata before adding more profiles.')
                token = secrets.token_urlsafe(24)
                db.execute('INSERT INTO profiles VALUES (?, ?, ?)', (token, fingerprint, config))
                return token
        except (OSError, sqlite3.Error):
            raise BridgeError('Cannot save compatibility profiles. Map a writable appdata directory to /data and keep it across updates.') from None

    def load(self, token):
        if not TOKEN_PATTERN.fullmatch(token) or not (self.directory / 'bridge.sqlite3').exists():
            raise KeyError('Unknown compatibility profile.')
        try:
            with self.lock, closing(self._connect()) as db, db:
                row = db.execute('SELECT config FROM profiles WHERE token=?', (token,)).fetchone()
            if not row:
                raise KeyError('Unknown compatibility profile.')
            config = json.loads(row[0])
            if config.get('version') != 1:
                raise BridgeError('This compatibility profile requires a newer application version.')
            return config
        except (OSError, sqlite3.Error, ValueError):
            raise BridgeError('The compatibility profile could not be read. Check your persistent appdata.') from None


class BridgePlan:
    def __init__(self, store, base_url):
        self.store = store
        self.base_url = public_base_url(base_url)
        self.sources = {}
        self.payloads = []
        self.references = 0
        self.existing_requirements = {}

    def upstream_addons(self, manifest):
        """Retain metadata dependencies when re-exporting our existing feeds."""
        prefix = self.base_url + '/bridge/'
        if not manifest.startswith(prefix) or not manifest.endswith('/manifest.json'):
            return []
        if manifest not in self.existing_requirements:
            token = manifest[len(prefix):-len('/manifest.json')]
            try:
                profile = self.store.load(token)
            except KeyError:
                return []  # Another server's profile remains an ordinary URL reference.
            self.existing_requirements[manifest] = list(dict.fromkeys(s['manifest'] for s in profile['sources']))
        return self.existing_requirements[manifest]

    def add(self, manifest, typ, catalog_id, genre, name, output_types=None):
        identity = source_identity(manifest, typ, catalog_id, genre)
        cid = 'nf.' + hashlib.sha256(canonical(identity).encode()).hexdigest()[:24]
        outputs = tuple(output_types or MEDIA_TYPES)
        if not outputs or any(t not in MEDIA_TYPES for t in outputs) or len(outputs) != len(set(outputs)):
            raise ValueError('Unsupported compatibility output type.')
        source = {'id': cid, 'name': name[:160], **identity}
        # Keep the original v2.1.0 profile identity for mixed sources. A
        # constrained output list is stored only when the bridge protects a
        # fixed movie/series query such as a separate genre selection.
        if output_types is not None:
            source['outputTypes'] = list(outputs)
        existing = self.sources.setdefault(cid, source)
        if tuple(existing.get('outputTypes', MEDIA_TYPES)) != outputs:
            raise ValueError('Conflicting compatibility output types.')
        output = []
        for media_type in outputs:
            payload = {'addonId': '', 'catalogId': f'{media_type}::{cid}', 'type': media_type}
            self.payloads.append(payload)
            output.append({'kind': 'addonCatalog', 'payload': payload})
        self.references += 1
        return output

    def finish(self):
        if not self.sources:
            return None
        token = self.store.save(list(self.sources.values()))
        manifest = f'{self.base_url}/bridge/{token}/manifest.json'
        for payload in self.payloads:
            payload['addonId'] = manifest
        return {'manifestUrl': manifest, 'sourceReferences': self.references,
                'catalogs': sum(len(s.get('outputTypes', MEDIA_TYPES)) for s in self.sources.values()),
                'persistent': True}


class CatalogState:
    def __init__(self):
        self.lock = threading.Lock()
        self.created = time.monotonic()
        self.offset = 0
        self.items = {typ: [] for typ in MEDIA_TYPES}
        self.complete = False
        self.seen_pages = set()
        self.bytes = 0
        self.unknown_items = 0


class BridgeService:
    def __init__(self, store, fetch=None):
        self.store = store
        self.fetch = fetch or JsonFetcher(allow_private=os.getenv('NUVIOEXPORTER_ALLOW_PRIVATE_UPSTREAM') == '1')
        self.states = OrderedDict()
        self.cache_lock = threading.Lock()

    def manifest(self, token):
        profile = self.store.load(token)
        catalogs = [{'id': s['id'], 'type': typ,
                     'name': s['name'] + (' · Movies' if typ == 'movie' else ' · Series'),
                     'extra': [{'name': 'skip', 'isRequired': False}]}
                    for s in profile['sources'] for typ in s.get('outputTypes', MEDIA_TYPES)]
        return {'id': 'dev.nuvioexporter.' + hashlib.sha256(token.encode()).hexdigest()[:12],
                'name': 'NuvioExporter compatibility', 'version': VERSION,
                'description': 'Original catalog queries adapted for Fusion. Keep NuvioExporter and the original addons available.',
                'resources': ['catalog'], 'types': list(MEDIA_TYPES), 'catalogs': catalogs}

    def _state(self, source):
        key = hashlib.sha256(canonical(source).encode()).hexdigest()
        with self.cache_lock:
            state = self.states.pop(key, None)
            if state is None or time.monotonic() - state.created > 300:
                state = CatalogState()
            self.states[key] = state
            while len(self.states) > 8:
                self.states.popitem(last=False)
            return state

    @staticmethod
    def upstream_url(source, offset):
        p = urlsplit(source['manifest'])
        base = p.path[:-len('/manifest.json')]
        extras = {**source['extra'], 'skip': str(offset)}
        path = (base + '/catalog/' + quote(source['type'], safe='') + '/' +
                quote(source['catalog'], safe='') + '/' + urlencode(extras, quote_via=quote) + '.json')
        return urlunsplit(p._replace(path=path))

    def catalog(self, token, typ, cid, skip=0, limit=PAGE_SIZE):
        if (typ not in MEDIA_TYPES or type(skip) is not int or type(limit) is not int or
                not 0 <= skip <= MAX_CACHED_ITEMS or not 1 <= limit <= 100 or
                skip + limit > MAX_CACHED_ITEMS):
            raise ValueError('Invalid catalog type, pagination offset or page size.')
        profile = self.store.load(token)
        source = next((s for s in profile['sources'] if s['id'] == cid), None)
        if source is None:
            raise KeyError('Unknown compatibility catalog.')
        if typ not in source.get('outputTypes', MEDIA_TYPES):
            raise KeyError('Unknown compatibility catalog.')
        state = self._state(source)
        if not state.lock.acquire(timeout=5):
            raise UpstreamError('This catalog is being refreshed. Retry shortly.')
        try:
            target = skip + limit
            deadline = time.monotonic() + 25
            for _ in range(MAX_SCAN_PAGES):
                if state.complete or len(state.items[typ]) >= target:
                    break
                if time.monotonic() >= deadline:
                    break
                data = self.fetch(self.upstream_url(source, state.offset))
                metas = data.get('metas')
                if not isinstance(metas, list) or any(not isinstance(m, dict) for m in metas):
                    raise UpstreamError('The original addon did not return a valid catalog page.')
                if not metas:
                    state.complete = True
                    break
                # Some addons ignore skip and return their complete list every time.
                signature = hashlib.sha256(canonical([(m.get('type'), m.get('id')) for m in metas]).encode()).hexdigest()
                if signature in state.seen_pages:
                    state.complete = True
                    break
                size = len(canonical(metas))
                if state.offset + len(metas) > MAX_CACHED_ITEMS or state.bytes + size > MAX_CACHED_BYTES:
                    raise UpstreamError('This catalog exceeds the compatibility cache limit. Use smaller upstream lists to preserve complete pagination.')
                accepted = {t: [] for t in MEDIA_TYPES}
                unknown = 0
                for meta in metas:
                    media_type = str(meta.get('type', '')).strip().lower()
                    media_type = {'movies': 'movie', 'tv': 'series', 'show': 'series', 'shows': 'series',
                                  'anime.movie': 'movie', 'anime.series': 'series'}.get(media_type, media_type)
                    if media_type in MEDIA_TYPES and isinstance(meta.get('id'), str) and meta['id']:
                        accepted[media_type].append({**meta, 'type': media_type})
                    else:
                        unknown += 1
                # Commit a page only after its complete validation; failures are retryable.
                for t in MEDIA_TYPES:
                    state.items[t].extend(accepted[t])
                state.unknown_items += unknown
                state.offset += len(metas)
                state.bytes += size
                state.seen_pages.add(signature)
            if not state.complete and len(state.items[typ]) < target:
                raise UpstreamError('More upstream pages are needed for this media type. Retry to continue scanning; the catalog was not treated as empty.')
            result = {'metas': copy.deepcopy(state.items[typ][skip:target])}
            if state.unknown_items:
                result['nuvioexporterWarning'] = f'{state.unknown_items} items have no supported movie/series type or ID.'
            return result
        finally:
            state.lock.release()
