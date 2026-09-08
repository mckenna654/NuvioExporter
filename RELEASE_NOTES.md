# NuvioExporter release notes

## 3.1.1 · 8 September 2026

Make Remux imports resilient when a Nuvio export refers to catalogs that have since been removed from an addon's manifest.

- Keep every source catalog that the configured Remux addon still advertises instead of aborting the whole preview at the first stale reference.
- Report unavailable catalog references without substituting a different catalog or provider.
- Omit a folder when all of its sources are unavailable, preventing empty Remux smart collections.
- Preserve valid sources in partially affected folders and continue to use Remux's catalog collection UUIDs.
- Validate the change against the supplied Nuvio export and its current AIOMetadata manifest: 12 groups, 138 usable folders, 293 catalog links, and no empty smart collections.

**Upgrade:** pull `ghcr.io/mckenna654/nuvioexporter:3.1.1`, recreate the container with the existing `/data` mapping, and confirm `/api/health` reports version `3.1.1`. Preview the Remux import again before applying it.

**Validation:** 87 automated tests pass on the complete application and transport suite. A full simulated Remux import of the supplied export creates 150 grouped collection objects and queues a library refresh without creating any source-less smart collection.

## 3.1.0 · 8 September 2026

Complete the NuvioExporter identity across the application and its install path. The public container is now `ghcr.io/mckenna654/nuvioexporter`, matching the repository, interface, documentation, Compose service, Unraid template, runtime user, and configuration variables.

- Publish `latest`, `3.1.0`, `3.1`, and commit-specific images under the NuvioExporter package.
- Rename Docker and Compose resources, the entrypoint, application user/group, appdata defaults, and all `NUVIOEXPORTER_*` settings.
- Give new Fusion compatibility manifests the `dev.nuvioexporter.*` identity and use `nuvioexporter:*` markers for Remux collections.
- Recognize earlier Remux markers during preview and migrate them on the next import, preventing duplicate collections.
- Centralize the application version and user agent so the API, manifest, and outbound requests remain consistent in later releases.
- Refresh the README, Unraid instructions, XML template, release Compose file, package badge, and interface version.
- Continue treating missing optional addons as warnings while preserving every usable connected source.
- Continue the security boundaries for private URLs, API keys, outbound requests, request size, same-origin writes, and non-root containers.

**Upgrade:** stop the existing container and back up its appdata. Use `ghcr.io/mckenna654/nuvioexporter:3.1.0`. Keep the existing host folder mapped to `/data`, or rename it to `/mnt/user/appdata/nuvioexporter` while stopped. Reusing the same Remux setup name updates and migrates earlier marked collections.

**Validation:** 85 automated tests cover Fusion conversion, persistent compatibility feeds, privacy boundaries, Remux preview/import and old-marker migration. CI tests Python 3.11 and 3.14, builds Linux `amd64` and `arm64`, starts the published image as UID/GID 10001, runs a real conversion, and verifies compatibility-profile persistence after container replacement.

## 3.0.1 · 7 September 2026

Correct the 3.0.0 source packaging failure and deliver the first working NuvioExporter release with both Fusion export and review-first Remux import. It added stable update markers, addon/catalog validation, smart collection creation, persistent compatibility feeds, refreshed branding, and complete Unraid documentation.

## 2.1.1 · 1 September 2026

Accept Fusion's bounded catalog request fields and protect separate genre queries. This fixed compatibility-backed collections that imported with sources but displayed no content.

## 2.1.0 · 31 August 2026

Add persistent mixed-catalog compatibility feeds, bounded upstream requests, profile storage, and appdata persistence.

## Earlier versions

Versions 2.0.0–2.0.5 established direct Nuvio-to-Fusion widget conversion, source URL mapping, partial-addon warnings, deterministic layout repair, public containers, and Unraid packaging. Version 1.0.0 belongs to the retired provider-migration prototype and is unsupported.
