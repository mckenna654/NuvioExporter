# Nuvio → Fusion conversion and compatibility addon

Reviewed 2026-09-01. NuvioExporter transfers a client layout and retains catalog references. Ordinary unfiltered movie/series references remain direct; the optional persistent addon serves mixed catalogs and separate genre queries in forms that survive Fusion's widget importer.

## Evidence

- User-supplied `fusion.json`: `fusionWidgets` export version 1, 13 widgets (5 collection rows, 8 classic rows), 65 folder items, 308 source references (307 addon catalogs and 1 Fusion `localWatchlist`). The original was inspected locally, not fetched or placed in the repository. `app/presets/fusion_example.json` replaces its private addon URL with `https://addon.example.invalid/profile/manifest.json`; artwork URLs also use neutral placeholders.
- [Nuvio Collection model](https://github.com/NuvioMedia/NuvioTV/blob/9c5d82b1bc30995b27c6deaa3ce147ba6caf8e88/app/src/main/java/com/nuvio/tv/domain/model/Collection.kt) and [CollectionsDataStore serializer](https://github.com/NuvioMedia/NuvioTV/blob/9c5d82b1bc30995b27c6deaa3ce147ba6caf8e88/app/src/main/java/com/nuvio/tv/data/local/CollectionsDataStore.kt): exported collections are an array. `sources` is authoritative when present; `catalogSources` is its legacy addon-only mirror. Native TMDB/Trakt sources are distinct providers. A native Android export can omit addon base URLs, making explicit URL mapping necessary.
- [AIOMetadata's Fusion exporter](https://github.com/cedya77/aiometadata/blob/b4dd42e199db66c5d1fe3aa39c6e2b2c3f8a6190/addon/lib/collectionBuilder/fusionExport.ts) and [format types](https://github.com/cedya77/aiometadata/blob/b4dd42e199db66c5d1fe3aa39c6e2b2c3f8a6190/addon/lib/collectionBuilder/types.ts): corroborating producer contract for folder shapes, composite catalog IDs, widget envelope and classic-row restrictions. These are not Fusion's own importer implementation.
- [Fusion's official addon protocol](https://fusionapp.dev/docs): manifest URLs identify addon services. Its public protocol docs do not establish every widget setting or native-source payload.
- Native Fusion inspection on 2026-08-31: of 12 imported Streaming Platforms folders, every folder containing an `all` source showed **No source**, while Apple TV, Prime Video, Peacock and Hulu retained all their movie/series sources. The converter's downloaded file still held the complete arrays. This points to the native widget importer rejecting an entire source array when a type is incompatible. Addon protocol support for custom catalog types is not evidence that widget payloads accept them. Version 2.0.5 omitted incompatible references. Version 2.1.0 instead offers a compatibility addon that emits valid movie/series payloads for those original feeds.
- Native Fusion inspection on 2026-09-01: a clean 12-row import retained 153 nonempty folders and every corrected source list, but its native re-export removed all standalone `payload.genre` fields. A neutral local addon showed that Fusion requests an initial catalog as `.json?limit=...&extra=...`; it rendered one movie and one series. Version 2.1.0 rejected those generic query parameters before reaching the upstream source, which made its compatibility-backed tiles open blank. Version 2.1.1 accepts the bounded native request shape and routes meaningful genre selections through one fixed-type compatibility feed.
- Native imports append rows instead of replacing an existing row with the same ID. A corrected file imported over an earlier one can therefore coexist with stale rows. Back up and remove previous Nuvio-imported rows before importing a regenerated file once.

No upstream implementation is vendored. Native source conversion is intentionally conservative because the supplied Fusion example does not prove equivalent TMDB/Trakt payloads.

## Field mapping

| Nuvio | Fusion widget v1 |
| --- | --- |
| Collection | `type: collection.row`, `dataSource.kind: collection` |
| Collection `id` | Widget ID, prefixed with `collection.` once |
| Collection `title` / optional `hideTitle` | Same fields |
| `folders` | `dataSource.payload.items` in original order |
| Folder `id`, `title`, `hideTitle` | Same fields |
| `coverImageUrl` | `imageURL` (HTTP/S only) |
| `tileShape` POSTER / LANDSCAPE / SQUARE | `imageAspect` poster / wide / square |
| `sources` or legacy `catalogSources` | Ordered `dataSources`; no duplicate mirror import |
| Addon source | `kind: addonCatalog` |
| `addonBaseUrl` or addon URL mapping | `payload.addonId`, full manifest URL |
| `type` + `catalogId` | Movie/series payloads use `payload.type` + `payload.catalogId: type::id`; mixed/custom types use the compatibility addon when enabled, otherwise are omitted with a warning |
| `genre` | A meaningful separate value uses one fixed-type compatibility feed when enabled because Fusion drops `payload.genre` on import. The `None` sentinel is treated as unfiltered. Existing encoded genre suffixes remain part of their catalog ID. |

All addon URLs required by exported sources are collected once in `requiredAddons`, in first-use order. URLs are not contacted during conversion. Query strings and private configuration path segments stay intact. URL mappings are explicit per addon ID; a single supplied URL never implicitly binds all addons. A mapping can override an embedded obsolete URL.

Missing URLs produce optional fields and warnings; their source references are omitted without blocking connected addons. Only instances used by retained sources appear in `requiredAddons`, together with the original metadata addons needed by adapted sources. Each direct source's `payload.addonId` contains its configured manifest URL; adapted sources contain the private compatibility manifest URL. Installing an addon in Fusion does not restore sources omitted from a previous file. Missing/duplicate layout IDs receive deterministic IDs and a report entry. Unknown settings are reported; malformed container structures are rejected.

## Limitations

- This converts collections, not an entire Nuvio installation. Accounts, player settings, installed stream addons, watch history, local library contents and home catalog preferences outside the collection export are not transferred. Envelope fields outside collections are reported as unconverted.
- A Nuvio collections export does not contain ordinary home rows outside its collections. Existing Fusion classic rows can be preserved when a Fusion export is the input; the converter does not invent absent rows.
- Nuvio-native TMDB and Trakt sources are omitted with source-level reasons. Recreate these in Fusion or first serve their recipes from a compatible addon. The converter never silently substitutes another provider or query.
- Focus GIFs, emoji tiles, hero backdrops/video, title logos, pinning, collection backgrounds and Nuvio view settings have no verified mapping in this v1 adapter. Explicit fields are listed as issues. Folder covers remain remote URLs, not embedded assets.
- Already-Fusion native sources such as `localWatchlist` retain their payloads. Their actual content comes from the target Fusion account/device; copying the widget does not copy a watchlist. Unknown native Fusion kinds are retained from Fusion input without asserting semantic validation.
- Widget payloads must use movie/series types. With compatibility enabled, a mixed collection source becomes two payloads pointing to this server. A meaningful genre filter on a known movie/series source becomes one payload of that original type. The adapter queries the original catalog recipe and filters mixed results without guessing replacement upstream IDs. The original mixed movie/series interleaving becomes two ordered feeds. Classic mixed rows are still omitted because automatically creating a different row layout has no verified mapping.
- `report.complete` means no omitted source/widget, empty folder, repair or unmapped setting was detected. `sourceCoverageComplete` refers only to source references. Neither proves live addon access or native client import.
- The neutral Fusion example round-trips exactly. A private full Nuvio configuration contains 12 collections, 154 folders and 347 references. With AIOMetadata connected, compatibility enabled and empty folders hidden, the converter preserves all 341 AIOMetadata references, omits six optional-addon references and their one dependent folder, and exports 153 nonempty folders. Version 2.1.1 adapts 23 mixed references plus one meaningful fixed-type genre reference. Private source files and credentials are not committed. Automated/API checks do not by themselves prove native client behavior on every Fusion version.

## Persistent compatibility protocol

`BridgePlan` registers only the source identities needed by an export. SHA-256-derived catalog IDs deduplicate identical upstream URL/type/catalog/genre combinations; a cryptographically random profile token identifies the manifest. Profiles use a versioned SQLite schema and survive replacement of the process or container. Equivalent configurations reuse the same token. Keep `/data` and the exported server address stable.

`GET /bridge/{token}/manifest.json` advertises two catalogs per original mixed feed and one catalog per protected fixed-type genre query. Its resources use `movie` and/or `series` with optional `skip`; the manifest contains no original credentials. Each catalog is served at `/bridge/{token}/catalog/{type}/{id}.json` or `/bridge/{token}/catalog/{type}/{id}/skip={offset}.json`. The endpoint also accepts Fusion's bounded initial `limit` and empty/default `extra` query parameters. Other fields remain rejected. The upstream addon remains required for metadata; IDs in returned items stay unchanged. Re-exporting this server's existing compatibility feeds with compatibility enabled also retains their original metadata dependencies.

Upstream requests preserve the configured manifest path/query, original catalog type/ID and selected genre. Returned pages use the requested bounded page size, defaulting to 40 and allowing at most 100. Pagination tracks the upstream offset independently of the requested movie/series offset and continues past nonmatching pages. Addons returning the same page repeatedly are treated as non-paginating. Unknown item types/IDs are excluded with a response warning instead of guessing their meaning.

A five-minute in-memory cache holds up to eight source feeds, each bounded to 10,000 original items and 8 MiB. Network reads have a 15-second deadline and 8 MiB limit. A request scans at most 12 upstream pages, with a 25-second scan budget checked between pages. Reaching a limit or an upstream error yields an explicit error; it is not treated as an empty catalog. Retrying a bounded scan continues its cached progress. Smaller upstream lists are required if the per-source cache limit is reached.

TLS validation stays enabled. DNS answers are validated and the socket connects directly to a checked address, retaining the original hostname for TLS and HTTP. Cross-origin redirects, loopback, link-local and reserved destinations are blocked. Set `NUVIOEXPORTER_ALLOW_PRIVATE_UPSTREAM=1` only for trusted RFC1918/ULA addon hosts. Public catalog requests select a registered profile and source; they cannot supply arbitrary fetch URLs.

The database supports 200 distinct profiles, up to 2 MiB each. Changed source configurations receive new profiles without invalidating old exports. Back up appdata while stopped; never publish it. This service has no management authentication. Keep management routes on a trusted LAN/VPN; protect them if using a reverse proxy, while allowing Fusion to read its private bearer addon paths. Reverse proxies should not log those paths.

## API

`POST /api/fusion/convert`:

```json
{
  "export_data": [
    {
      "id": "home",
      "title": "Movies",
      "folders": [
        {
          "id": "popular",
          "title": "Popular",
          "tileShape": "POSTER",
          "catalogSources": [
            {"addonId": "my.addon", "type": "movie", "catalogId": "popular"}
          ]
        }
      ]
    }
  ],
  "addon_urls": {"my.addon": "https://addon.example/config/manifest.json"},
  "bridge_url": "http://YOUR-UNRAID-IP:7088",
  "omit_empty_folders": true
}
```

Response: `success` indicates analysis completed, not that a file is ready. Check `report.canExport`. Missing addons are warnings; connected sources remain exportable without an acknowledgement step. If no usable sources or supported widgets remain, `fusionConfig` is `null`; `previewWidgets` provides the diagnostic layout and `report.exportBlockReason` explains what to repair. Otherwise `fusionConfig` is the importable file and `previewWidgets` is empty. `report.requiresPartialApproval` remains for compatibility and is always `false`. Send only a non-null `fusionConfig` to Fusion, never the preview or whole response. `export_data` also accepts a single Nuvio collection, `{collections: [...]}`, Fusion `{widgets: [...]}`/v1 envelope, or a Fusion widget array. Manifests and arbitrary full-backup schemas are rejected.

Omitting `bridge_url` keeps stateless direct-only conversion. `omit_empty_folders` defaults to false at the API for compatibility; the browser enables it by default. A separate response `bridge` object supplies the private manifest URL and registration counts. `report.bridgedSourceReferences` counts original adapted references; a mixed reference produces two catalogs while a fixed-type genre reference produces one. `report.omittedEmptyFolders` distinguishes hidden empty tiles from retained ones. `/api/bridge/settings` supplies the optional configured public URL. Profile storage errors return 503, upstream failures 502, unknown profiles/catalogs 404, and invalid pagination 400.

`report.incompatibleCatalogs` counts connected catalog references omitted because their media type is outside the verified movie/series widget format. Each also appears in `report.items` with its reason and in the unsupported count. This warning does not block the remaining compatible sources.

Privacy: layouts are held in application memory; compatibility mode persists the original connection/query information required to serve its registered feeds. The report does not include addon URL fields, but still includes user-provided titles, IDs and setting field names. The Fusion file contains the actual URLs and must be kept private. The app is unauthenticated and intended for local use.
