# Install NuvioExporter on Unraid

Release: **v3.0.1** · Image: **`ghcr.io/mckenna654/nuvio2fusion:3.0.1`**

The image is public; no GitHub account or registry login is needed to pull it. Linux `amd64` and `arm64` images are published. The application runs as UID/GID 10001. The entrypoint briefly prepares its data directory as root, then drops privileges. One persistent appdata mount is required for compatibility profiles; no media mounts, privileged mode or Docker socket access is needed.

**Keep it on a trusted network.** There is no app authentication. Do not forward port 7088 through your router. A remote user's browser sends uploaded JSON to your Unraid server; converted files can contain private addon tokens. Use authenticated HTTPS or a VPN if access beyond your trusted LAN is needed.

## Upgrade an existing container

1. Edit the existing container and set Repository to `ghcr.io/mckenna654/nuvio2fusion:3.0.1`.
2. Add a **Path**: host `/mnt/user/appdata/nuvio2fusion`, container `/data`, access **Read/Write**. Existing 2.0.x containers did not have this mapping. Do not use a media folder.
3. Apply, open the WebUI, and confirm `/api/health` reports `3.0.1`.
4. Reconvert the **original Nuvio export** with compatibility enabled. A 2.0.5 partial file cannot recover its removed mixed-source references. Reconvert for 3.0.1 if you use separate genre filters; existing 2.1.x profile links themselves remain valid after the container update.
5. Use your Unraid LAN URL in the compatibility address field. Back up your Fusion widgets, remove the earlier Nuvio-imported collection rows, then import the new JSON once and connect the listed compatibility addon. Fusion appends imports instead of updating matching IDs.

Keep the container running and preserve appdata across updates. Stop the container before copying appdata for backup. The database stores private upstream URLs; do not share it. Losing it invalidates old profile links until you restore the backup or regenerate and re-import.

## Install using the Unraid template

This is a direct template install; a Community Applications listing is not required and is not currently claimed.

1. Download [`unraid-template.xml`](https://github.com/mckenna654/NuvioExporter/releases/download/v3.0.1/unraid-template.xml) from the release.
2. Save it on your Unraid boot device as `/boot/config/plugins/dockerMan/templates-user/my-nuvio2fusion.xml`. If that file already exists, back it up before replacing it. Unraid stores user Docker templates in this directory. [Unraid application documentation](https://docs.unraid.net/unraid-os/manual/applications/)
3. Open **Docker → Add Container** and choose **NuvioExporter** from the user templates.
4. Leave **Network Type** as **Bridge** and privileged mode off. Keep the container port at **7088**. If the host port is taken, choose another host port, such as **7089**.
5. Apply/create the container. Once the image has downloaded, open its **WebUI**, or visit `http://YOUR-UNRAID-IP:7088` using your chosen host port. Enable **Auto-Start** if desired.

The template pins version `3.0.1` for a repeatable install. Its WebUI, icon, support link and port mapping are included. Unraid's official guide covers [bridge networking, port mappings and container management](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/).

## Install through Add Container without the XML

Open **Docker → Add Container** and configure:

| Field | Value |
| --- | --- |
| Name | `NuvioExporter` |
| Repository | `ghcr.io/mckenna654/nuvio2fusion:3.0.1` |
| Network Type | `Bridge` |
| Privileged | `Off` |
| Port mapping | Host `7088` → Container `7088`, TCP |
| WebUI, if shown in Advanced View | `http://[IP]:[PORT:7088]/` |
| Appdata path | Host `/mnt/user/appdata/nuvio2fusion` → Container `/data`, Read/Write |
| Additional environment variables | None |

The image already sets `HOST=0.0.0.0` and `PORT=7088` internally. Do not set the container's `HOST` to `127.0.0.1`, as that would prevent access through its published port. `PUID` and `PGID` are not supported or needed.

## Use Docker Compose instead

Download [`docker-compose.release.yml`](https://github.com/mckenna654/NuvioExporter/releases/download/v3.0.1/docker-compose.release.yml). The default host binding is localhost. For a trusted LAN, set `NUVIO2FUSION_BIND_IP` to your server's LAN IP before starting, replacing the example address below:

```sh
export NUVIO2FUSION_BIND_IP=192.168.1.10
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

Keep this setting in your shell or a local `.env` file whenever you recreate the service. `NUVIO2FUSION_PORT` can change the host port. Do not launch both this service and the Unraid template on the same port.

## Convert your collections

1. Back up your current Fusion widgets and retain the original Nuvio collections export.
2. Upload the Nuvio collections JSON into NuvioExporter.
3. Connect only the addons you use. For AIOMetadata, select `aio-metadata` and paste your configured URL ending in `/manifest.json`.
4. Convert and review the report. Optional addons such as Bingecat can stay blank: their sources are omitted with a warning. With Hide empty folders enabled, a folder relying entirely on a skipped addon is omitted with a warning.
5. Leave compatibility enabled and set its address to `http://YOUR-UNRAID-IP:7088`, using your actual host port. It protects both mixed catalogs and separate genre filters. Keep the `/data` mapping and container running.
6. Download the Fusion widget JSON. Back up Fusion and remove previous Nuvio-imported collection rows before importing the new file once; imports append rather than update matching IDs. Install the required NuvioExporter compatibility addon when prompted. Its private URL is also shown in the converter. Keep the same configured catalog addons available to Fusion. Do not import the separate compatibility report.

To send the setup to Remux instead, choose **Remux · import through the API**, enter the Remux server address and an administrator API key, then use a stable setup name. NuvioExporter previews the planned addon and collection changes before import. Reuse the same name for later updates; existing Remux collections are never deleted. The Remux server must be reachable from the NuvioExporter container.

Do not share generated widget files, private addon URLs or unsanitized screenshots in public Discord channels. Share the [project](https://github.com/mckenna654/NuvioExporter) or [release](https://github.com/mckenna654/NuvioExporter/releases/tag/v3.0.1) instead. The included examples deliberately use nonfunctional placeholder URLs.

## Updates, verification and troubleshooting

- **Pinned version:** edit the Repository field to a newer published version and apply. To follow successful builds of `main`, use `ghcr.io/mckenna654/nuvio2fusion:latest` and Unraid's update controls instead. `latest` may include changes newer than a tagged release.
- **Verify:** open `http://YOUR-UNRAID-IP:7088/api/health`; this release reports `NuvioExporter`, version `3.0.1`, status `ok`. The image also includes a Docker health check.
- **Page unreachable:** check the host/container port mapping, bridge network, container logs and LAN firewall. Change only the host port when resolving a port conflict.
- **Permission denied when pulling:** the package is public; use the exact `ghcr.io/mckenna654/nuvio2fusion:3.0.1` image name and check GitHub/registry connectivity.
- **Compatibility link fails:** keep the same appdata mount and server address, and check that Fusion can reach your Unraid host. Never put localhost in exports for other devices. Version 3.0.1 retains the bounded `limit`/`extra` compatibility fix from 2.1.1.
- **LAN upstream blocked:** set `NUVIO2FUSION_ALLOW_PRIVATE_UPSTREAM=1` only if your original addon is on a trusted LAN address. Loopback and cloud metadata addresses remain blocked.
- **Addon missing:** supply its configured manifest URL only if you want its sources. Downloads are blocked only when no usable sources or supported widgets remain.
- **Rollback:** choose a previously published image tag. Keep a private backup of appdata. Versions before 2.1.0 cannot serve compatibility profiles; rolling back that far requires returning to direct-only exports. Save downloads and original Nuvio exports outside the container.

CI runs the conversion/API tests on Python 3.11 and 3.14, builds both Linux architectures, and starts the published image on an `amd64` runner to check health, conversion, and compatibility-profile persistence across container replacement. This does not replace verifying your own addon availability or your Unraid server's network configuration.
