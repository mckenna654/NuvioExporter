#!/bin/sh
set -eu

# Docker/Unraid can create a new bind mount owned by root. Prepare only this
# service's data directory, then run the application without root privileges.
if [ "$(id -u)" = 0 ]; then
    mkdir -p "$NUVIOEXPORTER_DATA_DIR"
    chown nuvioexporter:nuvioexporter "$NUVIOEXPORTER_DATA_DIR"
    chmod 700 "$NUVIOEXPORTER_DATA_DIR"
    for file in "$NUVIOEXPORTER_DATA_DIR"/bridge.sqlite3*; do
        if [ -f "$file" ] && [ ! -L "$file" ]; then
            chown nuvioexporter:nuvioexporter "$file"
            chmod 600 "$file"
        fi
    done
    exec gosu nuvioexporter "$@"
fi
exec "$@"
