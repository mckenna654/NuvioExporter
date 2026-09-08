<p align="center">
  <img src="app/static/brand/logo.svg" alt="NuvioExporter — move your collection setup" width="760">
</p>

<p align="center">
  <strong>Your Nuvio collections. A new home.</strong><br>
  A small, self-hosted tool for moving Nuvio collection setups to Fusion or Remux.
</p>

<p align="center">
  <a href="https://github.com/mckenna654/NuvioExporter/actions/workflows/docker-publish.yml"><img src="https://github.com/mckenna654/NuvioExporter/actions/workflows/docker-publish.yml/badge.svg" alt="Build status"></a>
  <a href="https://github.com/mckenna654/NuvioExporter/releases/latest"><img src="https://img.shields.io/github/v/release/mckenna654/NuvioExporter?display_name=tag&sort=semver" alt="Latest release"></a>
  <a href="https://github.com/mckenna654/NuvioExporter/pkgs/container/nuvioexporter"><img src="https://img.shields.io/badge/container-ghcr.io-2496ED?logo=docker&logoColor=white" alt="Container image on GitHub Container Registry"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-b5eed2" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-a7a0ef" alt="Python 3.11 or later">
  <img src="https://img.shields.io/badge/platform-linux%2Famd64%20%7C%20arm64-8bd5ca" alt="Linux amd64 and arm64">
  <img src="https://img.shields.io/badge/built%20with-OpenAI%20Codex-111111" alt="Built with OpenAI Codex">
</p>

## What it does

Export your configured collections from Nuvio, open the JSON in NuvioExporter, then choose Fusion or Remux. Fusion exports a widget file. Remux imports the catalog-backed setup directly through its administrator API and can update the same setup on later runs.

The application, repository, container, configuration variables, and install files all use the **NuvioExporter** name.

NuvioExporter preserves the layout and references to your original catalog sources. Ordinary catalogs stay connected directly to their addons. The optional compatibility addon serves mixed catalogs as separate movie and series feeds and protects separate genre selections that Fusion's importer otherwise drops. It keeps the original provider and query. Keep NuvioExporter running when using that addon, and keep your original addons installed for metadata. Accounts and provider configurations are not migrated.

- Preserve collection and folder order, titles, covers, tile shapes and hidden folder titles.
- Keep multiple catalog sources in each folder, including their genre selections.
- Restore mixed-only folders and genre-filtered sources through persistent compatibility profiles.
- Resolve addon IDs to their full manifest URLs without guessing another provider.
- Preserve supported classic rows and native sources when the input is already a Fusion export.
- Review every omitted source, missing URL and unmapped visual setting before importing.
- Download the widget JSON and a separate compatibility report.
- Preview a Remux transfer before changing the server, install or reuse its Stremio catalog addons, and request a library refresh after import.
- Update previously imported Remux groups and collections using private import markers, or explicitly wipe and rebuild the complete Remux collections library.
- Run locally with Python or Docker; conversion makes no outbound catalog or artwork requests.

**This is a collections converter, not a full Nuvio backup converter.** Player settings, credentials, watch history, libraries and home rows absent from the export are not transferred.

## Quick start

**Installing on Unraid?** Use the [Unraid installation guide](docs/UNRAID.md) and the [v3.3.0 release downloads](https://github.com/mckenna654/NuvioExporter/releases/tag/v3.3.0). The public image is `ghcr.io/mckenna654/nuvioexporter:3.3.0`; no registry login is needed. **Compatibility mode requires an appdata path mapped to `/data`.**

### Run with Python

Requires Python 3.11 or later. Node.js is only needed for development checks, not to run the app.

```sh
git clone https://github.com/mckenna654/NuvioExporter.git
cd NuvioExporter
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Open **[http://localhost:7088](http://localhost:7088)**. On Windows, use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

The application binds to `127.0.0.1` by default. It does not require an account or API key.

### Build locally with Docker Compose

From the repository directory:

```sh
docker compose up --build -d
```

Then open [http://localhost:7088](http://localhost:7088). The supplied Compose file builds your checkout and binds the published port to localhost.

```sh
docker compose logs --tail=100
docker compose down
```

To update a local build, pull the repository changes and run `docker compose up --build -d` again. Compose stores compatibility profiles in `./data`, mounted at `/data`. Preserve this directory across updates.

### Use the published container

Published images are available from [GitHub Container Registry](https://github.com/mckenna654/NuvioExporter/pkgs/container/nuvioexporter). For the pinned release:

```sh
docker run -d \
  --name nuvioexporter \
  --restart unless-stopped \
  -p 127.0.0.1:7088:7088 \
  -v nuvioexporter-data:/data \
  ghcr.io/mckenna654/nuvioexporter:3.3.0
```

`latest` follows successful builds of `main`; `sha-<commit>` identifies a particular build. Version tags are generated when a matching `v<version>` Git tag is published. Builds target Linux `amd64` and `arm64`. Check [Actions](https://github.com/mckenna654/NuvioExporter/actions) before assuming a particular image tag exists.

For Unraid, the [installation guide](docs/UNRAID.md) covers the [versioned XML template](unraid-template.xml), manual Add Container setup and updates. One private appdata volume is needed for compatibility profiles; no media or Docker socket mounts are needed. [docker-compose.release.yml](docker-compose.release.yml) runs the prebuilt release without cloning or building the application. Both Compose examples bind to localhost by default; set the release file's `NUVIOEXPORTER_BIND_IP` to your server's LAN address for trusted network access. The management UI/API has no authentication layer.

## Send a setup to Remux

Choose **Remux · Import through the API** in the destination menu. Enter the Remux server address, an administrator API key, and a stable setup name. The key is sent only for the preview/import requests and is not written to the NuvioExporter profile store.

NuvioExporter checks the Remux administrator session, installed Stremio addons and advertised catalog IDs before it offers the import button. A preview lists groups and collections that will be created or updated. Import then:

1. Installs a missing Stremio catalog addon from the exact manifest URL you supplied, or reuses the matching enabled addon already in Remux.
2. Enables only the source catalogs used by this setup. Existing addon catalog settings are left alone.
3. Creates a manual group for each Nuvio collection and a smart Remux collection for each folder. Folder sources become a catalog membership filter, so Remux refreshes current catalog contents instead of receiving a one-time list of titles.
4. Promotes each Nuvio collection as a Jellyfin group and nests its folder collections underneath it in the original group and folder order.
5. Copies folder cover, backdrop, and logo artwork into Jellyfin's Primary, Backdrop, and Logo image slots. Unchanged images are skipped on later imports.
6. Applies a private `nuvioexporter:<setup>:<entry>` marker. Reusing the same setup name updates those entries instead of creating duplicates. Version 3.1.0 also recognizes and migrates markers created by earlier releases.
7. Requests `POST /library/refresh` so Remux can populate the collections.

If a Nuvio export contains a catalog that its configured addon no longer advertises, the preview reports and omits that source without choosing a substitute. Other sources in the folder remain active. A folder is omitted when none of its sources remain, so the importer does not create an empty smart collection.

Jellyfin displays the promoted Nuvio groups as library views and their smart collections as ordered children. Its client controls the final grid/row presentation, so Nuvio's `ROWS`, `TABBED_GRID`, tile shape, hidden-title, glow, and focus-animation settings cannot be forced through the Jellyfin API.

Mixed and genre-filtered sources use the optional compatibility addon. Native Nuvio TMDB/Trakt recipes and exact cross-source interleaving are reported as unsupported or approximate; they are never silently rewritten. Existing collections are not deleted, including folders omitted because their addon URL was not supplied or its catalogs are no longer advertised.

Normal imports keep unrelated and omitted collections. To replace the complete Remux collections library, select **Wipe the existing Remux collections library before import** before previewing. The preview reports the exact deletion count and marks every incoming entry as a rebuild. Import stays disabled until you type `WIPE COLLECTIONS`. NuvioExporter checks that the collection IDs are unchanged since preview, deletes child collections before their groups, and then recreates the selected Nuvio setup. This mode deletes collection and group objects only; it does not delete media items, addons, API keys, or other Remux settings. Back up Remux before using it.

For a direct API integration, the app exposes the same two endpoints used by the GUI:

```sh
curl --fail-with-body http://127.0.0.1:7088/api/remux/preview \
  -H 'Content-Type: application/json' \
  --data-binary @remux-preview.json

curl --fail-with-body http://127.0.0.1:7088/api/remux/import \
  -H 'Content-Type: application/json' \
  --data-binary @remux-import.json
```

The preview body contains `export_data`, `addon_urls`, `server_url`, `api_key`, `setup_name`, optionally `bridge_url`, and optionally `wipe_collections: true`. A wipe preview returns its exact count and confirmation phrase. Its import body must contain the returned `previewToken`, `api_key`, and `wipe_confirmation: "WIPE COLLECTIONS"`. A preview expires after 15 minutes and is single-use after an authorized import starts. Do not put API keys or configured manifest URLs in a repository, issue, gist or support screenshot.

## Convert a setup to Fusion

1. **Back up your existing Fusion widgets.** Keep the original Nuvio export as well.
2. **Export collections from Nuvio.** Use its collection-management export. The usual result is a JSON array of collections, not a manifest URL or account backup.
3. **Upload or paste the JSON** into NuvioExporter. The **Addon to connect** menu lists addon IDs found in your file, with their catalog counts.
4. **Connect only the addons you use.** Choose an addon, paste its normal URL in **Addon manifest URL**, and click **Connect addon**, then select **Convert to Fusion**. For `aio-metadata`, use your own configuration's full install URL, not its homepage. Leave optional addons such as Bingecat blank: their sources are omitted with a warning, while connected sources remain exportable. You can also convert first and fill the optional missing-URL fields. No JSON formatting is needed.
5. **Keep catalog compatibility enabled.** Set **NuvioExporter address reachable from Fusion** to your server's LAN URL, such as `http://192.168.1.10:7088`. Do not use localhost for another device. This preserves mixed feeds and separate genre filters. Leave **Hide folders with no usable sources** enabled to omit optional-addon-only tiles. Convert and review the results.
6. **Download Fusion widgets.** The compatibility report is a separate download for your review; it is not a Fusion import file.
7. **Replace the earlier converted rows, then import once.** Fusion appends imports instead of updating matching widget IDs. After making a backup, remove your earlier Nuvio-imported collection rows before importing the corrected file; otherwise old and corrected copies coexist. Install the listed compatibility addon if prompted, keep both NuvioExporter and the original metadata addons available, and test a few folders after import.

If your Fusion device only offers URL import, use a Fusion client that accepts the file/text or a private hosting method you control. Widget files can contain account-specific install URLs: **do not publish them to a public gist or repository**.

The two bundled examples use deliberately nonfunctional addon/artwork URLs. They demonstrate structure and reporting, not working catalog feeds.

## Addon URL mapping

Nuvio often stores a logical addon ID, such as `my.addon`. Fusion stores the full manifest URL. NuvioExporter resolves each source in this order:

1. An explicit URL mapping for that addon ID.
2. The source's `manifestUrl`.
3. The source's `addonBaseUrl`, with `/manifest.json` appended when needed.
4. An HTTP(S) or `stremio://` URL already stored in `addonId`.

Normally, choose **Addon to connect**, paste the full URL in **Addon manifest URL**, and click **Connect addon**. The saved URL remains editable in a labelled field. A URL entered before clicking **Convert to Fusion** is also saved when an addon is selected. One URL is never guessed to apply to every addon.

For bulk entry only, enter an object under **Advanced: JSON URL mappings**:

```json
{
  "my.movie.addon": "https://movies.example/config/manifest.json",
  "my.series.addon": "https://series.example/profile/manifest.json"
}
```

Use the **exact original addon ID** as the key. Do not bind an unrelated provider simply because it has a similar name: the original catalog IDs must exist at that URL. One mapping is never silently applied to every addon.

Mappings may override an obsolete embedded URL. Configuration path segments and query parameters are preserved. `stremio://` install URLs are normalized to HTTPS. URLs are validated but never fetched during conversion.

## Compatibility

| Input feature | Output behavior |
| --- | --- |
| Collections and folders | Collection widgets and folder items, in original order |
| Titles and hidden folder titles | Preserved |
| Cover image URLs | Preserved as remote HTTP(S) artwork references |
| Poster / landscape / square tiles | Mapped to Fusion poster / wide / square |
| Multiple addon sources per folder | Compatible sources preserved in order |
| Catalog IDs | Preserved with Fusion's `type::catalogId` representation |
| Separate genre selection | Compatibility addon keeps the original query because native Fusion import drops `payload.genre`; without compatibility, the field is emitted but may be lost on import |
| Mixed `all` or custom catalog media type in a folder | Compatibility addon fetches the original feed and separates actual movie/series items; omitted with a warning if disabled |
| Both `sources` and `catalogSources` | `sources` is authoritative; the legacy mirror is not duplicated |
| Missing addon URL | Its sources are omitted with a warning; connected addons remain exportable |
| Nuvio-native TMDB or Trakt query | Reported as unsupported; no speculative Fusion payload is invented |
| Focus GIF, emoji, hero backdrop/video, title logo | Reported as unmapped; no equivalent is claimed |
| Nuvio collection view, background or pinning settings | Listed for review when present |
| Existing Fusion classic rows | Supported presentation, numbering, limit and cache TTL retained |
| Existing Fusion-native source | Payload retained; account/library contents are not copied |
| Unknown widget type | Omitted and reported |

Fusion widget payloads use `movie` and `series`. A raw `all` source can make Fusion discard a folder's source list. Native import also removes a separate `payload.genre` value. The compatibility addon keeps both query forms on the server: it filters a mixed result into movie and series feeds, while a fixed-type genre query remains one feed of its original type. It never substitutes a new upstream catalog ID. Original ordering is preserved within each mixed type, but movie/series interleaving becomes two feeds. Mixed classic rows still need to be placed in collection folders. Unsupported item types cannot be guessed. A file with no usable sources cannot be downloaded.

See [the format contract and implementation notes](docs/FUSION.md) for field mappings and evidence.

### Understanding the report

- **Sources kept:** source references represented in the output. Several folders may refer to the same catalog.
- **Sources omitted:** references that need a URL, a compatible source, or another repair.
- **Compatibility addon:** mixed references become two filtered feeds; fixed-type genre references remain one feed. `bridgedSourceReferences` counts original references, not expanded payloads.
- **Incompatible catalog types:** references excluded when compatibility is disabled, or when a classic row cannot hold them.
- **Layout issues:** settings without a verified mapping, repaired IDs/titles, or empty folders.
- **Complete:** no detected omission, repair, empty folder or unmapped setting. It is not a guarantee of live catalog access or pixel-identical rendering.

A partial conversion downloads as `fusion-widgets-partial.json`. A complete conversion downloads as `fusion-widgets.json`. The separate `fusion-compatibility-report.json` explains the result. Missing addon URLs, omitted sources and empty folders produce warnings without an acknowledgement checkbox. You can download as long as usable sources and supported widgets remain. The browser hides empty folders by default; switch this off to retain their tiles. API callers retain empty tiles unless `omit_empty_folders` is true.

**Empty mixed-only folders from 2.0.x:** start from the original Nuvio export in 2.1.1 with compatibility enabled. Version 2.0.5 removed mixed sources to protect valid siblings, but could not restore mixed-only folders. An already-partial export no longer contains those references. A converter export from before removal can also be repaired; an export from Fusion after it discarded sources cannot recover them.

**Updating an imported layout:** Fusion's widget import appends rows, even when IDs match. Back up the current widget export, remove the earlier Nuvio-imported collection rows, then import the newly generated file once. Repeated imports can leave an old row selected while a corrected duplicate exists.

### Keeping compatibility links working

- Preserve the server address and `data/bridge.sqlite3` (Docker: `/data/bridge.sqlite3`) across container recreation. The same profile generates the same link while its database exists.
- Back up appdata privately with the container stopped. It contains plaintext configured addon URLs; profile links are bearer credentials. Do not upload either to Discord, issues or a public repository.
- If the database is lost, regenerate from the original Nuvio export and re-import the new links. If the server address changes, reconvert using the new address. Old files are not rewritten automatically.
- Upstream catalogs are fetched on demand and cached in memory for five minutes. The adapter scans upstream pages until it can fill the requested filtered page. It returns an error on outages or safety limits rather than claiming the catalog is empty.
- The service caches at most eight catalogs, each up to 10,000 items/8 MiB. Large or sparse lists may need a retry while scanning continues. There are at most 200 stored profiles; identical conversions reuse a profile. Unknown item types are reported in the catalog response rather than guessed.
- Conversion itself does not probe providers. A populated widget file does not prove every live catalog is available. You can disable compatibility to keep the original stateless, direct-catalog workflow.

**Recovering an empty file from version 2.0.0:** start again with the original Nuvio export. That version allowed downloads containing folders but no catalog links. Installing AIOMetadata in Fusion afterward cannot reconnect them, and re-importing the empty Fusion file cannot recover the missing IDs. Supply the original addon URLs during conversion, confirm the source counts, then import the corrected widgets. Back up your Fusion layout before replacing the empty copies.

The import file has this envelope:

```json
{
  "exportType": "fusionWidgets",
  "exportVersion": 1,
  "requiredAddons": [],
  "widgets": []
}
```

Only the widget file goes into Fusion. Do not import the report or the entire API response.

## Configuration and privacy

| Setting | Default | Purpose |
| --- | --- | --- |
| `HOST` | `127.0.0.1` with Python; `0.0.0.0` inside Docker | Listening address |
| `PORT` | `7088` | Listening port |
| `NUVIOEXPORTER_DATA_DIR` | `./data` with Python; `/data` in Docker | Private persistent compatibility profiles |
| `NUVIOEXPORTER_PUBLIC_URL` | Browser's current origin | Optional default public/LAN address placed into exports |
| `NUVIOEXPORTER_ALLOW_PRIVATE_UPSTREAM` | Off | Set `1` only for trusted RFC1918/ULA LAN addon servers |
| Browser upload limit | 5 MiB | Maximum individual source file |
| API request limit | 10 MiB | Maximum request body |
| Conversion limits | 1,000 widgets/collections; 10,000 source references | Bound large inputs |

For example, `PORT=8080 .venv/bin/python run.py` changes the local port. If you change the container's internal `PORT`, update its published port mapping too.

- Uploaded layouts and results stay in server memory. Compatibility mode persists only the original source connection/query information needed to serve its feeds.
- The addon makes bounded catalog GET requests. It does not fetch artwork, proxy streams, copy accounts, accept arbitrary destination URLs in catalog requests or serve filesystem paths.
- TLS certificates are verified. DNS destinations are checked and pinned; redirects to other origins, loopback, link-local and reserved addresses are blocked. LAN upstreams require the explicit environment setting above.
- The Docker entrypoint prepares the dedicated data directory as root, then runs the application as UID/GID 10001. No privileged mode is needed. Request access logging is disabled to avoid logging bearer profile URLs.
- The UI loads its own local scripts, styles and logo. It does not use analytics, remote fonts or external preview images.
- Downloads can contain private addon URLs and tokens. Keep them private and inspect exports before sharing.
- Reports omit addon URL fields but retain titles, catalog IDs and setting names; those may still be personal.
- Requests have body limits and same-origin checks. Responses use a restrictive content-security policy, no-store caching and no-referrer policy. Validation errors avoid reflecting submitted values.
- **There is no management authentication.** Keep the UI/API on your trusted LAN or VPN. If using a reverse proxy, protect management routes and avoid logging `/bridge/` token paths. Fusion needs access to its private bearer addon URL without an interactive login. Do not expose the entire service publicly.

## API

The machine-readable API schema is available at `/openapi.json` on your local instance. The interactive CDN-based documentation pages are disabled so the app stays self-contained.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | App name, version and health |
| `GET` | `/api/presets/nuvio` | Neutral Nuvio example in `rawData` |
| `GET` | `/api/presets/fusion` | Neutral Fusion example in `rawData` |
| `POST` | `/api/fusion/convert` | Convert JSON and return `fusionConfig` plus `report` |
| `POST` | `/api/remux/preview` | Validate a Remux connection and return a reviewable import plan |
| `POST` | `/api/remux/import` | Apply a preview plan to Remux and request a library refresh |
| `GET` | `/api/bridge/settings` | Default server address and LAN-upstream policy |
| `GET` | `/bridge/{token}/manifest.json` | Registered compatibility profile manifest |
| `GET` | `/bridge/{token}/catalog/{type}/{id}/skip={offset}.json` | Filtered page; bounded `limit` and empty/default `extra` options used by Fusion are accepted |

Example request:

```json
{
  "export_data": [
    {
      "id": "weekend",
      "title": "Weekend",
      "folders": [
        {
          "id": "movies",
          "title": "Movies",
          "tileShape": "POSTER",
          "catalogSources": [
            {"addonId": "my.addon", "type": "movie", "catalogId": "popular"}
          ]
        }
      ]
    }
  ],
  "addon_urls": {
    "my.addon": "https://addon.example/config/manifest.json"
  }
}
```

Save that body as `request.json`, then:

```sh
curl --fail-with-body http://127.0.0.1:7088/api/fusion/convert \
  -H 'Content-Type: application/json' \
  --data-binary @request.json > response.json
```

`export_data` accepts a Nuvio collection array, a single collection, `{ "collections": [...] }`, a Fusion widget array, or a Fusion widget v1 envelope. Full-backup fields outside `collections` are not transferred and are reported. Manifests and unrecognized structures are rejected.

To enable compatibility, add `"bridge_url": "http://YOUR-UNRAID-IP:7088"` and optionally `"omit_empty_folders": true` to the request. Omitting `bridge_url` keeps stateless direct behavior. The response's separate `bridge` object contains the private manifest URL and feed counts; only `fusionConfig` should be imported into Fusion. Storage failures return 503. Catalog upstream failures return 502, unknown profiles 404, and invalid pagination 400.

Responses contain `success`, `fusionConfig`, `previewWidgets` and `report`. `success` means the input was analyzed; check **`report.canExport`** before saving an import. Missing addons are warnings and do not block connected sources. If no usable sources or supported widgets remain, `fusionConfig` is `null`, `previewWidgets` contains the diagnostic layout, and `report.exportBlockReason` explains the repair. Once exportable, save **only `fusionConfig`**. `report.requiresPartialApproval` is retained for compatibility and is always `false`; omissions are listed in `report.missingAddons`, source records and warnings. Invalid structures/mappings return HTTP 400, invalid request fields 422, cross-origin posts 403, and oversized requests 413.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Missing manifest URL | Supply the URL only if you use that addon. Otherwise leave it blank and download the partial export. |
| Advanced mappings JSON error | Use **Addon manifest URL** for a normal URL. If a plain URL was pasted into the advanced field, converting moves it into the normal field; choose its addon and convert again. |
| Empty folders from a 2.0.0 download | Reconvert the original Nuvio JSON with URLs for the addons you want to keep. Manually installing an addon cannot restore omitted catalog references. |
| Download blocked | No usable sources or supported widgets remain. Connect at least one addon you use, or review the source report for unsupported queries. |
| Tiles appear, but catalogs fail | Confirm the referenced addon is installed, accessible and still serves those catalog IDs. Conversion does not test the service. |
| Compatibility tile opens blank on 2.1.0 | Update the container to 2.1.1. Fusion sends `limit` and `extra` on its initial catalog request; 2.1.0 rejected that valid request. Existing persistent profile links continue to work after the update. |
| Old and corrected rows both appear | Fusion appends widget imports. Back up, remove the previous Nuvio-imported rows, then import the corrected file once. |
| Artwork is missing | The original URL must remain reachable. Example URLs intentionally do not resolve. |
| File is marked partial with all sources kept | Review unmapped visual settings or repaired layout IDs. Source coverage and layout fidelity are separate. |
| Invalid JSON | Export collections again and avoid copying Markdown code fences into the input. |
| Fusion rejects the import | Confirm widget export v1 support, import the widget file rather than the report, and review unsupported row types. |
| Browser shows an earlier result | Editing input clears results; convert again after changing a URL or file. Refresh after updating the app. |

When reporting a problem, include app/Fusion/Nuvio versions, the report and a minimal **sanitized** example. Replace account URLs, tokens and private titles first.

## Development and verification

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
node --check app/static/js/fusion.js
git diff --check
```

The suite covers URL resolution, source mirrors, ordering, multiple providers, native-source limitations, partial reports, duplicate IDs, Fusion round-trips and API privacy/boundaries. A sanitized fixture exercises **13 widgets, 65 folders and 308 source references**. The browser-generated download has also been compared with the expected widget JSON.

CI tests Python 3.11 and 3.14 before publishing Linux container images, then checks the running application's UID, health, page and example conversion. It creates a compatibility profile, replaces the container using the same bind mount, and verifies the original manifest link still works. Pull requests run checks without publishing. Tests also cover filtering, pagination, error recovery, storage, unsafe network destinations and profile URL privacy.

Project layout: `app/fusion.py` and `app/remux.py` handle the two transfer paths; `app/main.py` serves the API; `app/static/js/fusion.js` handles the browser workflow; `app/presets/` contains neutral examples; `tests/` contains regression coverage.

## Contributors

- **Jake McKenna** — creator and maintainer.
- **OpenAI Codex** — implementation, debugging, testing and documentation contributor.

## Project identity and license

**NuvioExporter** — *move your collection setup.* The original vector mark represents two collection tiles and a forward transfer arrow. SVG and PNG assets are in [`app/static/brand/`](app/static/brand/); see [brand asset notes](docs/BRANDING.md).

[MIT licensed](LICENSE). Independent community software, not affiliated with or endorsed by Nuvio or Fusion. Their names belong to their respective owners. Read [release notes](RELEASE_NOTES.md) for changes and upgrade guidance.
