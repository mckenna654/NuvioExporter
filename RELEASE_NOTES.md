# NuvioExporter release notes

## 3.0.0 · 7 September 2026

Add Remux as a first-class destination for Nuvio collection setups. Fusion conversion remains available as the default path.

The product is presented as **NuvioExporter** now that it supports both destinations. Existing repository, container and compatibility identifiers stay unchanged so current links and saved profiles continue to work.

- Add a destination selector and Remux connection form to the GUI. Remux imports require an administrator API key, server address and stable setup name; the key is held only in the browser request flow.
- Preview Remux changes before applying them. The preview validates the administrator session, matching Stremio addons, advertised catalog IDs and the collections that will be created or updated.
- Create manual Remux group containers for Nuvio collections and smart collections for folders. Folder sources become Remux catalog membership filters, so Remux refreshes current catalog content instead of receiving a one-time title snapshot.
- Install missing Stremio catalog addons from the exact configured manifest URL, reuse matching enabled addons, and enable only the catalogs used by the imported setup. Existing unrelated addon settings are preserved.
- Add stable private import markers so rerunning the same setup updates its collections without duplicates. Interrupted creates are recoverable; omitted or removed Nuvio folders are never deleted from Remux.
- Request a Remux library refresh after the import and show the result, warnings and source coverage in the browser. Export a sanitized import report for review.
- Preserve mixed and genre-filtered sources through the existing persistent compatibility addon. Unsupported native Nuvio providers, visual-only settings and exact cross-source interleaving remain explicit warnings.
- Add bounded Remux transport checks, TLS verification, DNS destination checks, API-key header handling, redirect rejection and response limits. API keys and configured addon URLs are excluded from plans, reports and logs.
- Document the Remux API workflow, Unraid upgrade path and direct preview/import requests. Update the image, template and health version to `3.0.0`.
- Add 15 Remux-focused tests covering repeat imports, interrupted creation, catalog filtering, mixed/genre bridge behavior, privacy, validation and HTTP transport.

**Upgrade:** use `ghcr.io/mckenna654/nuvio2fusion:3.0.0` and preserve the existing `/data` mapping. Fusion users should reconvert the original Nuvio export as before. Remux users should preview the setup, review the planned creates/updates, then import; keep the NuvioExporter service running when compatibility feeds are required.

**Validation:** 84 Python tests pass, including the original Fusion/bridge suite and the Remux integration contract tests. Browser smoke inspection confirms the Fusion/Remux destination selector, connection fields and transfer review panel render from the self-hosted app.

## 2.1.1 · 1 September 2026

Fix compatibility-backed collections that imported with sources but opened blank in native Fusion. A neutral diagnostic addon confirmed that Fusion adds `limit` and `extra` to its initial catalog request. Version 2.1.0 rejected those parameters before it queried the original addon.

- Accept Fusion's bounded `limit` and empty/default `extra` request shape, while continuing to reject arbitrary upstream query fields. Path and query `skip` pagination remain supported.
- Honor requested page sizes from 1 through 100 and keep the existing item, byte, scan and timeout limits.
- Protect meaningful standalone genre selections with a fixed movie or series compatibility feed. Native Fusion re-export showed that widget import drops `payload.genre`; the `None` sentinel remains an ordinary unfiltered direct source.
- Keep existing 2.1.0 mixed-feed profiles compatible after the container update. New conversions add constrained output metadata only when a fixed-type genre query needs it.
- Warn that Fusion appends widget imports instead of updating matching IDs. Back up and remove earlier Nuvio-imported rows before importing the regenerated file once, so stale and corrected copies do not coexist.
- Add regression coverage for the exact native request shape, bounded query rejection, fixed-type profiles, genre preservation and the `None` sentinel. The full suite now contains 69 passing tests.

**Upgrade:** set the Unraid Repository to `ghcr.io/mckenna654/nuvio2fusion:2.1.1`, keep the existing `/data` mapping, and apply. Existing compatibility links benefit from the catalog-request fix immediately. Reconvert the **original Nuvio export** to protect standalone genre filters, using the same reachable server address. Back up Fusion, remove the previous Nuvio-imported collection rows, then import the new file once. Keep the NuvioExporter container and original metadata addon available.

**Validation:** the native diagnosis used a local neutral addon and one disposable test widget; both movie and series items rendered in Fusion when the generic request parameters were accepted. A clean native re-export also proved that source arrays survive the corrected movie/series layout while standalone genre fields do not. The private original export produces 12 rows, 153 nonempty folders and all 341 connected references; 24 references use 45 compatibility catalogs, while six optional-addon references remain explicitly omitted. Private collection files, addon URLs and profile tokens remain outside the repository.

## 2.1.0 · 31 August 2026

Restore mixed-only collection folders with a persistent compatibility addon. The 2.0.5 safeguard removed `all` references to prevent Fusion rejecting entire folders, but left folders with no movie/series alternative empty. This release serves the original mixed feed as separate, correctly filtered movie and series catalogs.

- Preserve original upstream URLs, catalog IDs and genre selections. Fetch the original catalog type and filter the returned item types; do not invent movie/series upstream catalog IDs.
- Keep ordinary movie/series catalogs direct. Include both the compatibility addon and the original metadata addon in the exported requirements.
- Preserve pagination after filtering, scan past pages without the requested type, and recognize repeated pages from addons that ignore pagination. Upstream failures are reported as errors, not cached as empty lists.
- Enable compatibility and Hide empty folders by default in the browser. Missing optional addons remain warnings; no Bingecat connection is required.
- Store private source profiles in `/data/bridge.sqlite3`. Random bearer links survive restarts and container replacement when appdata is preserved. Identical profiles reuse their links.
- Add DNS-pinned destination checks, verified TLS, same-origin-only redirects, bounded network/cache usage and sanitized errors. Disable request access logs to protect private profile paths.
- Add a persistent appdata mapping to the Unraid template and Compose files. The entrypoint prepares that dedicated directory, then runs the application as UID/GID 10001.
- Expand automated coverage for filtering, pagination, retry behavior, profile persistence, re-export metadata dependencies and network safety. CI also replaces the published container and checks that the same profile URL still works.

**Upgrade:** use `ghcr.io/mckenna654/nuvio2fusion:2.1.0` and add a Read/Write path from `/mnt/user/appdata/nuvio2fusion` to `/data`. Reconvert the **original Nuvio export**, enable compatibility and enter an address reachable from every Fusion device. Back up Fusion, import the new widget JSON and install its listed compatibility addon alongside your metadata addon. Keep the container running. Earlier partial exports have already lost the mixed sources and cannot reconstruct them.

**Privacy and lifetime:** compatibility mode saves private upstream configuration URLs on your server. Keep appdata, addon links and generated widget files private. Back up appdata while the container is stopped. Losing the database or changing the server address requires restoring it or regenerating/re-importing the layout. The management UI has no authentication; use a trusted LAN or VPN. Existing direct-only API behavior remains available by omitting `bridge_url`.

**Validation:** a private full-layout check preserved all 341 connected AIOMetadata references, including 23 adapted mixed references, across 12 rows and 153 nonempty folders. Six unconnected optional-addon references and their sole dependent folder were omitted with warnings. Live catalog checks recovered content for all ten formerly empty mixed-only folders; no user configuration or credentials are included in this release. The adapter preserves movie/series order separately, not their original interleaving. Unsupported native Nuvio providers and unmapped visual settings remain reported limitations. See the [Unraid guide](docs/UNRAID.md) and [format notes](docs/FUSION.md).

## 2.0.5 · 31 August 2026

Protect collection folders from mixed-type catalog sources. Native Fusion inspection showed folders containing an `all` catalog importing as **No source**, while folders containing only movie/series catalogs retained their source lists.

- Export only verified movie/series addon payloads in collection folders as well as classic rows. Omit incompatible references individually so the folder's other catalogs survive.
- Report incompatible media types, omitted references and folders left empty. Optional addons and these omissions remain warnings, with no approval checkbox.
- Do not relabel mixed catalogs as movie/series or invent replacement catalog requests.
- Repair converter-produced Fusion JSON that still contains the original sources, as well as native Nuvio input. JSON exported from Fusion after it discarded sources cannot recover them.
- Add regression tests for mixed valid/invalid sources, incompatible-only folders, existing-export repair and unused addon requirements.

Update Unraid's Repository field to `ghcr.io/mckenna654/nuvio2fusion:2.0.5` and apply, or re-pull `latest` after its build succeeds. Re-pulling the pinned `2.0.4` image will not install this fix. Back up Fusion before testing a corrected import; catalog playback and the corrected native import still need verification. All 46 automated tests pass locally; CI also checks Python 3.11/3.14 and the published container.

## 2.0.4 · 31 August 2026

Public Unraid release with the complete Nuvio-to-Fusion workflow and optional-addon support from 2.0.3.

- Publish versioned Linux `amd64` and `arm64` images, a pinned Unraid template, Compose file, install guide and checksummed install bundle.
- Fix the new container smoke test to retry connection resets and early HTTP disconnects during startup, with a bounded deadline. Conversion behavior is unchanged.
- Add startup-retry regression tests; 43 automated tests run on Python 3.11 and 3.14 before image publication.
- Verify the published container's non-root user, health endpoint, page and example conversion on the CI runner.

The 2.0.3 image built, but its initial startup-check workflow failed before readiness. This release corrects that validation issue without moving the earlier tag. Use `ghcr.io/mckenna654/nuvio2fusion:2.0.4` and the [Unraid guide](docs/UNRAID.md).

## 2.0.3 · 31 August 2026

Optional addons no longer block exports. Connect only the addons you use; missing instances such as Bingecat are reported without preventing export of connected AIOMetadata catalogs.

- Publish the tagged NuvioExporter release with a public versioned container, pinned Unraid XML template, prebuilt-image Compose file and Unraid install guide.
- Start the published container in CI and check its non-root user, health endpoint, page and example conversion, in addition to the Python test matrix and multi-architecture build.
- Allow partial downloads when at least one usable source remains, even if other addons have no URL.
- Omit unconnected addon references and include only connected, used instances in `requiredAddons`.
- Keep warnings, omitted-source counts and empty-folder reports. Optional addon fields are no longer marked required or invalid.
- Remove the partial-export confirmation checkbox. Warnings do not require acknowledgement.
- Keep the guard against files containing no usable sources or supported widgets.
- Preserve `report.requiresPartialApproval` for API compatibility, always `false`; `report.canExport` now permits missing addons when usable content remains.

Refresh the updated app and convert again. An AIOMetadata-only conversion can now be downloaded without connecting optional addons.

## 2.0.2 · 31 August 2026

Removes the need to write JSON when connecting an addon. Pasting a normal AIOMetadata installation URL into the previous advanced mapping box produced a JSON error before conversion could run.

- Add an **Addon to connect** selector populated from the input's actual addon IDs and catalog-reference counts.
- Add a normal **Addon manifest URL** field and **Connect addon** button; saved URLs remain editable per addon.
- Accept the selected addon's pending URL when converting, even if Connect addon was not clicked separately.
- Clearly label bulk JSON mappings as advanced. Recover a plain URL pasted there into the normal URL field and ask which addon it belongs to, keeping the entered URL intact.
- Keep independent addon mappings and missing-URL export blocking. Connecting AIOMetadata does not silently assign its URL to another addon.

Refresh the updated app to load the new form. API conversion behavior is unchanged from 2.0.1.

## 2.0.1 · 31 August 2026

Fixes an export workflow that allowed collection tiles to be downloaded without their catalog sources. Native Nuvio collection exports can contain logical addon IDs such as `aio-metadata` without the configured installation URLs Fusion needs. Version 2.0.0 reported those omissions but still allowed an empty widget file to be downloaded.

- Block widget exports until every missing addon URL is supplied, and block files with no usable sources.
- Highlight each missing instance URL, show the number of affected catalog references, focus the first repair field and provide a **Connect addons & convert** action.
- Keep each addon mapped separately; write its configured manifest URL into both `requiredAddons` and every matching catalog source.
- Offer repair fields for malformed embedded URLs when an addon ID is available.
- Require deliberate acknowledgement before downloading other partial layouts with omitted sources/widgets or empty folders.
- Keep the compatibility report and diagnostic preview available while export is blocked.
- Add regression coverage for missing instances, independent addon mappings, empty-file recovery, API readiness and partial-export decisions. A locally supplied 12-collection, 154-folder Nuvio export retained all 347 sources with two test URL mappings; live addon availability and native Fusion import were not verified.

**Upgrade and repair:** refresh the updated app, load the **original Nuvio export**, enter every configured addon manifest URL, then convert again. Do not reconvert the empty Fusion file: it no longer contains the source references. Installing an addon manually in Fusion cannot restore those links. Back up your Fusion widgets before replacing any empty imports.

**API behavior change:** `fusionConfig` is now `null` while an export is blocked. Check `report.canExport` and `report.exportBlockReason`; diagnostic widgets are in `previewWidgets`. `success` means the input was analyzed. Respect `report.requiresPartialApproval` before saving a partial file.

## 2.0.0 · 31 August 2026

NuvioExporter is now a focused Nuvio collections → Fusion widgets converter. This major release replaces the earlier provider-migration direction with a direct layout transfer, a new identity and explicit compatibility reporting. Existing repository history is preserved.

### New identity and scope

- Introduced the NuvioExporter name and the tagline **“Move your collection setup.”**
- Added an original collection-transfer logo, SVG favicon, PNG app icon and documentation wordmark.
- Updated the UI, API metadata, startup message, container service/user, image references and Unraid template.
- Removed the unrelated catalog-rebuilding workflow, its page/API, remote manifest fetcher and provider-specific examples.
- Kept one user-facing task: convert a Nuvio collection export or check/re-export existing Fusion widgets.

### Conversion behavior

- Export Fusion widget format v1 using `exportType`, `exportVersion`, `requiredAddons` and `widgets`.
- Preserve collections, folder order, titles, hidden folder titles, HTTP(S) cover URLs and poster/landscape/square shapes.
- Preserve multiple addon catalog sources per folder, source order, original catalog IDs and genre selections.
- Use `sources` as authoritative, with `catalogSources` as a legacy fallback. Mirrored sources are not duplicated.
- Resolve addon URLs from explicit mappings or embedded install/base URLs. Keep configuration paths and query strings intact.
- Provide editable missing-addon URL fields rather than guessing provider URLs.
- Retain supported Fusion classic-row presentation, numbering, cache TTL and limits, including explicit zero values.
- Retain native payloads already present in Fusion exports, such as a local-watchlist source, without claiming to copy the underlying library.
- Generate stable replacement IDs for missing/duplicate layout IDs and report each repair.

### Reports and downloads

- Show widget/folder counts and kept/omitted source references.
- Provide searchable source results, a widget layout preview and per-entry compatibility issues.
- Retain empty folder tiles for repair and report their missing sources.
- Mark downloads as partial when sources/widgets are omitted or layout settings need attention.
- Export a separate compatibility report without addon URL fields.
- Clear stale results when inputs change or become invalid.

### Privacy and deployment

- Conversion performs no outbound catalog, artwork or account requests.
- Uploads and results remain in application memory; no account/session database or persistent volume is required.
- Keep scripts, styles and logo assets local. No remote font, analytics or artwork previews are loaded by the UI.
- Limit browser files to 5 MiB, API bodies to 10 MiB, input collections/widgets to 1,000 and source references to 10,000.
- Reject cross-origin posts and avoid reflecting submitted values in request errors.
- Bind Python runs and the supplied Compose host port to localhost by default; run the container as an unprivileged user.
- Test Python 3.11 and 3.14 in CI before publishing `amd64` and `arm64` images to GitHub Container Registry.

### Breaking changes and upgrade steps

This is a major-version change. The previous generic conversion and remote-fetch APIs are removed. Client integrations should use `POST /api/fusion/convert` with `export_data` and optional `addon_urls`, and extract `fusionConfig` from its response.

1. Back up your original Nuvio export and current Fusion widgets.
2. Update the repository remote/image references to `mckenna654/nuvio2fusion`.
3. Rebuild with `docker compose up --build -d`, or recreate your container with the new image after its publish job succeeds. Stop any previous container already using port 7088.
4. Python users should reinstall `requirements.txt`; contributors should install `requirements-dev.txt`.
5. Export Nuvio collections, convert them, supply any missing addon URLs and review the compatibility report before importing into Fusion.

The container image path is `ghcr.io/mckenna654/nuvio2fusion`. `latest` follows successful main-branch builds. Versioned image tags appear only when the corresponding Git tag has been built; this document alone does not create a registry tag. No stored application data needs migrating.

### Known limitations

- Only collection layout and catalog references transfer. Accounts, player settings, watched history, local library data and absent home rows do not.
- Nuvio-native TMDB/Trakt sources have no verified direct mapping and are reported as unsupported. Recreate them in Fusion or supply an addon-backed equivalent.
- Nuvio focus GIFs, emoji, hero artwork/video, title logos, collection backgrounds, pinning and view settings have no verified widget-v1 mapping in this adapter.
- Referenced catalog services and remote artwork must remain accessible. Exporting a layout does not make them self-hosted.
- Classic addon rows require movie/series types. Other types belong in collection folders.
- Native Fusion payloads are retained from Fusion input without comprehensive semantic validation.
- A complete report indicates structural coverage, not identical rendering, live availability or guaranteed import into every Fusion version.
- Downloads can contain private addon tokens. Keep them private. Reports can still contain personal titles and catalog IDs.

### Validation

The remaining regression suite focuses on direct layout conversion and API boundaries. The neutral Fusion fixture round-trips exactly with 13 widgets, 65 folders and 308 source references. Browser checks cover successful conversion, missing-addon repair, invalid-input handling and the downloaded file's contents. Live import behavior remains dependent on the user's Fusion version and installed addons.

## Earlier versions

Earlier releases belong to the project's retired catalog-migration scope. Their source and tags remain in Git history; their endpoints, container references and documentation do not describe NuvioExporter 2.0.0.
