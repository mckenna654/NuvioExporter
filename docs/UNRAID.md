# Install NuvioExporter on Unraid

Release: **v3.1.0** · Image: **`ghcr.io/mckenna654/nuvioexporter:3.1.0`**

The public image supports Linux `amd64` and `arm64`. It runs as UID/GID 10001 after its entrypoint prepares `/data`. NuvioExporter needs no media mount, Docker socket, privileged mode, account, or registry login.

Keep the management page on a trusted network. It has no built-in authentication, uploaded exports can contain private addon URLs, and compatibility profiles retain the source connection data needed to serve Fusion. Do not forward port 7088 through your router. Use authenticated HTTPS or a VPN for remote access.

## Upgrade an existing installation

1. Back up the host folder currently mapped to `/data` while the container is stopped.
2. Change the image to `ghcr.io/mckenna654/nuvioexporter:3.1.0` and the container name to `NuvioExporter`.
3. Keep the existing host appdata folder mapped to `/data`, or rename it to `/mnt/user/appdata/nuvioexporter` while stopped and update the mapping.
4. Apply the change and open `http://YOUR-UNRAID-IP:7088/api/health`. It should report `NuvioExporter` version `3.1.0` with status `ok`.

Keeping the database preserves compatibility profile tokens. Remux imports made by earlier releases are recognized and migrated to the NuvioExporter marker when the same setup name is imported again. Back up Fusion or Remux before importing any regenerated layout.

## Install using the XML template

1. Download [`unraid-template.xml`](https://github.com/mckenna654/NuvioExporter/releases/download/v3.1.0/unraid-template.xml).
2. Save it as `/boot/config/plugins/dockerMan/templates-user/my-nuvioexporter.xml`.
3. Open **Docker → Add Container** and choose **NuvioExporter** from the user templates.
4. Keep **Network Type** set to **Bridge**, privileged mode off, and container port `7088`. Change only the host port if it conflicts.
5. Apply the template and enable Auto-Start if desired.

The template pins 3.1.0 and includes the WebUI, icon, support link, port, and appdata mapping.

## Add Container fields

| Field | Value |
| --- | --- |
| Name | `NuvioExporter` |
| Repository | `ghcr.io/mckenna654/nuvioexporter:3.1.0` |
| Network Type | `Bridge` |
| Privileged | `Off` |
| Port | Host `7088` → Container `7088`, TCP |
| WebUI | `http://[IP]:[PORT:7088]/` |
| Appdata | Host `/mnt/user/appdata/nuvioexporter` → Container `/data`, Read/Write |
| Environment variables | None required |

The image sets `HOST=0.0.0.0` and `PORT=7088`. `PUID` and `PGID` are not supported or required.

## Docker Compose

Download [`docker-compose.release.yml`](https://github.com/mckenna654/NuvioExporter/releases/download/v3.1.0/docker-compose.release.yml). It binds to localhost by default. Set a trusted LAN address before starting it when another device must reach NuvioExporter:

```sh
export NUVIOEXPORTER_BIND_IP=192.168.1.10
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

`NUVIOEXPORTER_PORT` changes the host port. Keep these values in a local `.env` file when recreating the service.

## Convert or import a setup

1. Keep the original Nuvio collections export and back up the destination.
2. Upload the export to NuvioExporter and choose Fusion or Remux.
3. Connect only the catalog addons used by the setup. For AIOMetadata, supply its complete configured URL ending in `/manifest.json`.
4. Review omitted sources and warnings. Optional addons can remain disconnected; their dependent sources are omitted without blocking unrelated collections.
5. For Fusion compatibility feeds, use `http://YOUR-UNRAID-IP:7088`, preserve `/data`, and keep NuvioExporter running. Import the widget JSON, not the separate report.
6. For Remux, enter its server address, an administrator API key, and a stable setup name. Preview before import. Reusing the name updates the marked setup without deleting unrelated collections.

Never post widget exports, configured addon URLs, Remux API keys, the appdata database, or unsanitized screenshots publicly. Share the [project](https://github.com/mckenna654/NuvioExporter) or [release](https://github.com/mckenna654/NuvioExporter/releases/tag/v3.1.0).

## Updates and troubleshooting

- **Updates:** select a newer release, or use `ghcr.io/mckenna654/nuvioexporter:latest` to follow successful main builds.
- **Page unreachable:** check the port mapping, bridge network, container logs, and LAN firewall. Change only the host port for conflicts.
- **Pull denied:** use the exact lowercase public image name shown above and check access to GitHub Container Registry.
- **Compatibility link fails:** keep the original appdata database and server address reachable from Fusion. Do not use localhost for another device.
- **LAN addon blocked:** set `NUVIOEXPORTER_ALLOW_PRIVATE_UPSTREAM=1` only for a trusted RFC1918/ULA addon host. Loopback, link-local, cloud metadata, and reserved addresses remain blocked.
- **Addon missing:** connect its configured manifest URL only if you want its sources. Other connected collections remain exportable.
- **Rollback:** restore the appdata backup and select a previous release. Save original exports outside the container.

CI tests Python 3.11 and 3.14, builds both architectures, starts the published image, checks conversion as the non-root user, and confirms compatibility profiles survive container replacement.
