"""Offline client-layout conversion; never reinterpret an addon's catalog recipe.

Contracts and compatibility limits are documented in docs/FUSION.md.
"""
from __future__ import annotations

import copy
import re
import uuid
from collections import Counter
from urllib.parse import urlsplit, urlunsplit


SHAPES = {'POSTER': 'poster', 'LANDSCAPE': 'wide', 'SQUARE': 'square'}
CLASSIC_TYPES = {'row.classic', 'row.classic.numbered'}
# These are the verified widget-payload types, not every type an addon manifest
# can advertise. Fusion can discard a whole folder's sources if one uses `all`.
FUSION_MEDIA_TYPES = {'movie', 'series'}
TYPE_ALIASES = {'movies': 'movie', 'tv': 'series', 'show': 'series', 'shows': 'series'}


def string(value):
    return value.strip() if isinstance(value, str) else ''


def manifest_url(value, *, base=False):
    """Validate without fetching. Preserve private path/query bytes in the export."""
    value = string(value)
    if value.startswith('stremio://'):
        value = 'https://' + value[10:]
    if not value or re.search(r'\s', value):
        raise ValueError('A full HTTP(S) addon URL is required.')
    parts = urlsplit(value)
    if (parts.scheme not in {'http', 'https'} or not parts.hostname or
            parts.username or parts.password or parts.fragment):
        raise ValueError('Invalid addon URL.')
    parts.port  # Also validate malformed ports without exposing the value.
    path = parts.path.rstrip('/')
    if not path.endswith('/manifest.json'):
        if not base:
            raise ValueError('Use the full install URL ending in /manifest.json.')
        path += '/manifest.json'
    return urlunsplit(parts._replace(path=path))


def is_web_url(value):
    try:
        parts = urlsplit(string(value))
        return parts.scheme in {'http', 'https'} and bool(parts.hostname) and not (parts.username or parts.password)
    except ValueError:
        return False


class FusionConversion:
    def __init__(self, addon_urls=None, bridge=None, omit_empty_folders=False):
        self.addon_urls = {}
        for key, value in (addon_urls or {}).items():
            if not string(key):
                raise ValueError('Addon mapping keys must not be empty.')
            self.addon_urls[key] = manifest_url(value)
        self.records = []
        self.issues = []
        self.missing = Counter()
        self.ids = set()
        self.required = {}
        self.empty_folders = 0
        self.skipped_widgets = 0
        self.incompatible_catalogs = 0
        self.bridge = bridge
        self.omit_empty_folders = omit_empty_folders
        self.omitted_empty_folders = 0

    def issue(self, path, code, message, fields=None):
        self.issues.append({'path': path, 'code': code, 'message': message,
                            **({'fields': fields} if fields else {})})

    def identifier(self, value, path, prefix=''):
        ident = string(value)
        if prefix and not ident.startswith(prefix):
            ident = prefix + ident if ident else ''
        if not ident or ident in self.ids:
            ident = prefix + str(uuid.uuid5(uuid.NAMESPACE_URL, 'nuvioexporter/fusion/' + path))
            self.issue(path, 'generated_id', 'A missing or duplicate ID was replaced with a stable unique ID.')
        self.ids.add(ident)
        return ident

    def title(self, value, path):
        if string(value):
            return value  # Preserve intentional spelling/spacing.
        self.issue(path, 'missing_title', 'A missing title was replaced with Untitled.')
        return 'Untitled'

    def unavailable_fields(self, raw, allowed, path):
        fields = sorted(k for k, v in raw.items() if k not in allowed and v not in (None, '', [], {}))
        if fields:
            self.issue(path, 'unmapped_settings', 'These Nuvio settings have no verified mapping in Fusion widget v1.', fields)

    def record(self, raw, path, title, status, reason, source=None):
        if len(self.records) >= 10000:
            raise ValueError('Too many source references.')
        # Do not put private addon URLs or native query contents in the report.
        cid = string(raw.get('catalogId'))
        if '://' in cid:
            cid = '[URL omitted]'
        record = {'path': path, 'name': string(raw.get('title')) or string(raw.get('catalogName')) or title,
                  'sourceId': cid, 'sourceType': string(raw.get('type') or raw.get('provider') or raw.get('kind')),
                  'status': status, 'reason': reason}
        self.records.append(record)
        return source

    def resolve_addon(self, raw):
        aid = string(raw.get('addonId'))
        # An explicit mapping can correct an obsolete install, but never falls
        # back to another addon's URL merely because there is only one mapping.
        if aid in self.addon_urls:
            return self.addon_urls[aid]
        for field, base in (('manifestUrl', False), ('addonBaseUrl', True)):
            if string(raw.get(field)):
                return manifest_url(raw[field], base=base)
        if aid.startswith(('https://', 'http://', 'stremio://')):
            return manifest_url(aid, base=True)
        if aid:
            self.missing[aid] += 1
        return None

    def addon_source(self, raw, path, title, *, fusion=False, allow_bridge=True):
        cid, typ = string(raw.get('catalogId')), string(raw.get('type'))
        if not cid or not typ:
            return self.record(raw, path, title, 'unsupported', 'Missing catalog ID or media type.')
        try:
            url = self.resolve_addon(raw)
        except ValueError:
            aid = string(raw.get('addonId'))
            if aid and '://' not in aid:
                self.missing[aid] += 1
            return self.record(raw, path, title, 'unsupported', 'Invalid addon URL. Supply a full manifest URL for this addon.')
        if not url:
            return self.record(raw, path, title, 'unsupported', 'Addon not connected; this source is omitted. Supply its manifest URL only if you want to include it.')
        if not fusion:
            allowed = {'provider', 'addonId', 'addonBaseUrl', 'manifestUrl', 'addonName',
                       'type', 'catalogId', 'genre', 'catalogName', 'title', 'name', 'aiometadata'}
            if any(k not in allowed and v not in (None, '', {}, []) for k, v in raw.items()):
                return self.record(raw, path, title, 'unsupported', 'Additional source options have no verified Fusion mapping; source omitted to avoid changing its query.')
        typ = TYPE_ALIASES.get(typ.lower(), typ.lower())
        if '::' in cid:
            prefix, cid = cid.split('::', 1)
            prefix = TYPE_ALIASES.get(prefix.lower(), prefix.lower())
            if prefix != typ:
                return self.record(raw, path, title, 'unsupported', 'Catalog prefix and media type disagree; resolve the type before exporting.')
        if not cid or not re.fullmatch(r'[a-z0-9_.-]+', typ):
            return self.record(raw, path, title, 'unsupported', 'Invalid catalog ID or media type.')
        if raw.get('genre') is not None and not isinstance(raw['genre'], str):
            return self.record(raw, path, title, 'unsupported', 'Genre must be text.')
        genre = string(raw.get('genre'))
        meaningful_genre = genre if genre.casefold() not in {'', 'none'} else ''
        if typ not in FUSION_MEDIA_TYPES:
            if self.bridge and allow_bridge:
                try:
                    sources = self.bridge.add(url, typ, cid, string(raw.get('genre')),
                                              string(raw.get('catalogName')) or title)
                except ValueError:
                    return self.record(raw, path, title, 'unsupported', 'This catalog has unsupported encoded options and cannot be adapted without changing its query.')
                self.required[url] = None  # Keep the original addon for metadata.
                return self.record(raw, path, title, 'preserved',
                    'Original mixed catalog retained through the compatibility addon as movie and series feeds. The upstream query is unchanged; each feed filters returned item types.', sources)
            self.incompatible_catalogs += 1
            return self.record(raw, path, title, 'unsupported',
                'Fusion widget import is verified only for movie and series. This source was omitted; its query was not rewritten. Enable the compatibility addon for mixed catalogs inside collection folders, or use a compatible upstream catalog.')
        if meaningful_genre and self.bridge and allow_bridge:
            try:
                sources = self.bridge.add(url, typ, cid, meaningful_genre,
                                          string(raw.get('catalogName')) or title,
                                          output_types=(typ,))
            except ValueError:
                return self.record(raw, path, title, 'unsupported', 'This genre-filtered catalog has unsupported encoded options and cannot be adapted without changing its query.')
            self.required[url] = None
            return self.record(raw, path, title, 'preserved',
                'Original genre-filtered catalog retained through the compatibility addon because Fusion drops separate genre fields during widget import.', sources)
        payload = copy.deepcopy(raw) if fusion else {}
        payload.update(addonId=url, catalogId=f'{typ}::{cid}', type=typ)
        if not fusion and meaningful_genre:
            payload['genre'] = meaningful_genre
        if self.bridge:
            for upstream in self.bridge.upstream_addons(url):
                self.required[upstream] = None
        self.required[url] = None
        return self.record(raw, path, title, 'preserved', 'Original addon and catalog retained; no catalog recipe was changed.',
                           {'kind': 'addonCatalog', 'payload': payload})

    def nuvio_source(self, raw, path, title):
        if not isinstance(raw, dict):
            return self.record({}, path, title, 'unsupported', 'Source must be an object.')
        provider = string(raw.get('provider') or 'addon').lower()
        if provider != 'addon':
            return self.record(raw, path, title, 'unsupported',
                'Nuvio-native source has no verified direct Fusion mapping. Recreate it in Fusion or expose it through an addon first.')
        return self.addon_source(raw, path, title)

    def fusion_source(self, raw, path, title, *, allow_bridge=True):
        if not isinstance(raw, dict) or not string(raw.get('kind')) or not isinstance(raw.get('payload'), dict):
            return self.record({}, path, title, 'unsupported', 'Malformed Fusion data source.')
        if raw['kind'] == 'addonCatalog':
            return self.addon_source(raw['payload'], path, title, fusion=True, allow_bridge=allow_bridge)
        if raw['kind'] == 'collection':
            return self.record(raw, path, title, 'unsupported', 'Nested collections are not supported in a folder source.')
        # This source already came from Fusion, so retain its native payload.
        # We deliberately do not manufacture one from a Nuvio TMDB/Trakt recipe.
        return self.record(raw, path, title, 'preserved', 'Existing Fusion-native source retained; its account data is not transferred.', copy.deepcopy(raw))

    def nuvio_collection(self, raw, path):
        if not isinstance(raw, dict) or not isinstance(raw.get('folders'), list):
            raise ValueError('Expected a Nuvio collection with folders.')
        title = self.title(raw.get('title'), path)
        widget = {'id': self.identifier(raw.get('id'), path, 'collection.'), 'title': title,
                  'type': 'collection.row', 'dataSource': {'kind': 'collection', 'payload': {'items': []}}}
        if isinstance(raw.get('hideTitle'), bool):
            widget['hideTitle'] = raw['hideTitle']
        self.unavailable_fields(raw, {'id', 'title', 'hideTitle', 'folders'}, path)
        for j, folder in enumerate(raw['folders']):
            fp = f'{path}.folders[{j}]'
            if not isinstance(folder, dict):
                raise ValueError('Expected a folder object.')
            ft = self.title(folder.get('title'), fp)
            shape = string(folder.get('tileShape') or 'SQUARE').upper()
            if shape not in SHAPES:
                self.issue(fp, 'unknown_shape', 'Unknown tile shape replaced with square.')
                shape = 'SQUARE'
            item = {'id': self.identifier(folder.get('id'), fp), 'title': ft,
                    'hideTitle': folder.get('hideTitle') is True,
                    'imageAspect': SHAPES[shape], 'dataSources': []}
            if string(folder.get('coverImageUrl')):
                if is_web_url(folder['coverImageUrl']):
                    item['imageURL'] = folder['coverImageUrl']
                else:
                    self.issue(fp, 'invalid_artwork', 'Non-HTTP(S) artwork URL omitted.')
            self.unavailable_fields(folder, {'id', 'title', 'hideTitle', 'tileShape', 'coverImageUrl',
                                             'sources', 'catalogSources'}, fp)
            # Nuvio writes catalogSources as a legacy mirror. A present sources
            # array is authoritative, even when it is deliberately empty.
            sources = folder.get('sources')
            if sources is None:
                sources = folder.get('catalogSources', [])
            if not isinstance(sources, list):
                raise ValueError('Expected a sources array.')
            for k, raw_source in enumerate(sources):
                source = self.nuvio_source(raw_source, f'{fp}.sources[{k}]', ft)
                if source:
                    item['dataSources'].extend(source if isinstance(source, list) else [source])
            if not item['dataSources']:
                self.empty_folders += 1
                self.issue(fp, 'empty_folder', 'Folder artwork and position retained, but it has no usable sources.')
                if self.omit_empty_folders:
                    self.omitted_empty_folders += 1
                    self.issues[-1]['message'] = 'Folder omitted because none of its sources are connected and compatible. Its original layout remains in the input file.'
                    continue
            widget['dataSource']['payload']['items'].append(item)
        return widget

    def fusion_widget(self, raw, path):
        if not isinstance(raw, dict):
            raise ValueError('Expected a widget object.')
        typ = raw.get('type')
        if typ not in CLASSIC_TYPES | {'collection.row'}:
            self.issue(path, 'unsupported_widget', 'Widget type is not covered by the verified Fusion widget v1 contract; omitted.')
            self.skipped_widgets += 1
            return None
        widget = copy.deepcopy(raw)
        widget['id'] = self.identifier(raw.get('id'), path)
        widget['title'] = self.title(raw.get('title'), path)
        ds = raw.get('dataSource')
        if typ == 'collection.row':
            if not isinstance(ds, dict) or ds.get('kind') != 'collection' or not isinstance(ds.get('payload', {}).get('items'), list):
                raise ValueError('Invalid collection widget.')
            for j, item in enumerate(widget['dataSource']['payload']['items']):
                fp = f'{path}.items[{j}]'
                if not isinstance(item, dict) or not isinstance(item.get('dataSources'), list):
                    raise ValueError('Invalid collection item.')
                item['id'] = self.identifier(item.get('id'), fp)
                item['title'] = self.title(item.get('title'), fp)
                if item.get('imageAspect') not in {'poster', 'wide', 'square'}:
                    item['imageAspect'] = 'square'
                    self.issue(fp, 'unknown_shape', 'Missing or invalid image aspect replaced with square.')
                sources = [self.fusion_source(s, f'{fp}.sources[{k}]', item['title']) for k, s in enumerate(item['dataSources'])]
                item['dataSources'] = [s for value in sources if value for s in (value if isinstance(value, list) else [value])]
                if not item['dataSources']:
                    self.empty_folders += 1
                    self.issue(fp, 'empty_folder', 'Folder omitted without usable sources.' if self.omit_empty_folders else 'Folder retained without usable sources.')
            if self.omit_empty_folders:
                before = widget['dataSource']['payload']['items']
                after = [item for item in before if item['dataSources']]
                self.omitted_empty_folders += len(before) - len(after)
                widget['dataSource']['payload']['items'] = after
        else:
            source = self.fusion_source(ds, path + '.source', widget['title'], allow_bridge=False)
            if not source:
                self.skipped_widgets += 1
                return None
            widget['dataSource'] = source
            for key, default in (('limit', 20), ('cacheTTL', 1800)):
                if key not in widget:
                    widget[key] = default
                elif type(widget[key]) is not int or widget[key] < 0:
                    raise ValueError('Invalid classic row limit/cacheTTL.')
            if 'presentation' not in widget:
                widget['presentation'] = {'aspectRatio': 'poster', 'cardStyle': 'medium',
                                          'badges': {'providers': False, 'ratings': True}}
            presentation = widget['presentation']
            if (not isinstance(presentation, dict) or presentation.get('aspectRatio') not in {'poster', 'wide', 'square'} or
                    presentation.get('cardStyle') not in {'small', 'medium', 'large'} or
                    not isinstance(presentation.get('badges'), dict)):
                raise ValueError('Invalid row presentation.')
        return widget

    def convert(self, data):
        fusion = False
        envelope_fields = []
        if isinstance(data, dict) and 'widgets' in data:
            if data.get('exportType', 'fusionWidgets') != 'fusionWidgets' or type(data.get('exportVersion', 1)) is not int or data.get('exportVersion', 1) != 1:
                raise ValueError('Unsupported Fusion export version.')
            rows, fusion = data['widgets'], True
        elif isinstance(data, dict) and 'collections' in data:
            rows = data['collections']
            envelope_fields = sorted(set(data) - {'collections', 'version', 'exportVersion', 'exportedAt', 'exportType'})
        elif isinstance(data, dict) and 'folders' in data:
            rows = [data]
        elif isinstance(data, list):
            rows = data
            fusion = bool(rows) and all(isinstance(r, dict) and 'dataSource' in r for r in rows)
        else:
            raise ValueError('Use a Nuvio collections export or Fusion widgets export.')
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ValueError('Expected at most 1000 collections/widgets.')
        if envelope_fields:
            self.issue('root', 'setup_settings', 'Only collections are converted. Other setup/account/player settings are not a Fusion widget layout.', envelope_fields)
        widgets = []
        for i, row in enumerate(rows):
            path = f'{"widgets" if fusion else "collections"}[{i}]'
            widget = self.fusion_widget(row, path) if fusion else self.nuvio_collection(row, path)
            if widget:
                widgets.append(widget)
        counts = Counter(r['status'] for r in self.records)
        folders = sum(len(w['dataSource']['payload']['items']) for w in widgets if w['type'] == 'collection.row')
        warnings = [
            'Referenced original addons must remain installed and accessible in Fusion. Their catalog definitions and accounts are not copied.',
            'Addon URLs can contain private tokens. Keep the exported file private; the report omits addon URLs.',
            'Artwork stays at its original URL. No artwork, catalogs, accounts, watch history or library contents are copied.',
            'Output targets Fusion widget export v1. Structural validation is not a live import or catalog-availability check.',
        ]
        if not fusion:
            warnings.append('Nuvio focus GIFs, hero artwork/video, title logos and collection view settings have no verified v1 mapping; see the per-entry issues.')
        if self.missing:
            warnings.append(f'{len(self.missing)} addons are not connected; {sum(self.missing.values())} catalog references are omitted. Connecting these addons is optional. Sources from connected addons remain exportable.')
        if self.incompatible_catalogs:
            warnings.append(f'{self.incompatible_catalogs} catalog references use media types outside the verified movie/series widget format. Enable the compatibility addon for collection sources; otherwise an incompatible source is omitted to protect the other catalogs in its folder.')
        if self.empty_folders:
            warnings.append(f'{self.empty_folders} folders have no usable sources. Review their omitted-source reasons: connect any wanted addons or replace incompatible catalogs in the original layout, then convert again. Installing an addon in Fusion alone cannot restore omitted references.')
        if self.omitted_empty_folders:
            warnings.append(f'{self.omitted_empty_folders} empty folders were left out of this export. Turn off Hide empty folders to retain their tiles.')
        block_reason = ''
        if not counts['preserved']:
            block_reason = 'No usable catalog sources remain. Use the original Nuvio collections export and resolve the source issues; a layout-only Fusion file cannot recover missing catalogs.'
        elif not widgets:
            block_reason = 'No supported widgets remain to export.'
        can_export = not block_reason
        bridge_info = self.bridge.finish() if can_export and self.bridge else None
        if bridge_info:
            self.required[bridge_info['manifestUrl']] = None
            warnings.append(f'{bridge_info["sourceReferences"]} catalog references use the NuvioExporter compatibility addon for mixed media or separate genre filters. Keep this service running at the exported address and preserve its appdata. Movie/series order is preserved within each mixed feed; their original interleaving is separated. Original addon URLs are saved privately on this server.')
        complete = can_export and counts['unsupported'] == 0 and not self.issues and self.skipped_widgets == 0
        return {'success': True, 'fusionConfig': {'exportType': 'fusionWidgets', 'exportVersion': 1,
                    'requiredAddons': list(self.required), 'widgets': widgets} if can_export else None,
                # Keep a diagnostic preview when no usable content remains.
                'previewWidgets': widgets if not can_export else [], 'bridge': bridge_info,
                'report': {'inputFormat': 'Fusion widgets' if fusion else 'Nuvio collections',
                    'complete': complete, 'sourceCoverageComplete': counts['unsupported'] == 0,
                    'canExport': can_export, 'exportBlockReason': block_reason,
                    'requiresPartialApproval': False,  # Compatibility field; omissions are warnings only.
                    'widgets': len(widgets), 'folders': folders, 'emptyFolders': self.empty_folders,
                    'omittedEmptyFolders': self.omitted_empty_folders,
                    'bridgedSourceReferences': bridge_info['sourceReferences'] if bridge_info else 0,
                    'skippedWidgets': self.skipped_widgets, 'sourceReferences': len(self.records),
                    'incompatibleCatalogs': self.incompatible_catalogs,
                    'counts': {k: counts[k] for k in ('preserved', 'unsupported')},
                    'requiredAddonCount': len(self.required),
                    'requiredAddonHosts': list(dict.fromkeys(urlsplit(u).hostname for u in self.required)),
                    'missingAddons': [{'addonId': aid, 'references': n} for aid, n in self.missing.items()],
                    'items': self.records, 'issues': self.issues, 'warnings': warnings}}


def convert_to_fusion(export_data, addon_urls=None, bridge=None, omit_empty_folders=False):
    return FusionConversion(addon_urls, bridge, omit_empty_folders).convert(export_data)
