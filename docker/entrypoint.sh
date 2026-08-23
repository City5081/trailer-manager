#!/bin/sh
# Startet die Anwendung unter der gewuenschten Benutzerkennung.
#
# Auf Unraid gehoeren die Filme dem Benutzer nobody (99:100). Laeuft der
# Container als root, gehoeren neu geschriebene Dateien danach root - Emby kommt
# dann nicht mehr heran. Deshalb werden Benutzer und Gruppe auf PUID/PGID
# umgestellt und die Anwendung mit gosu abgegeben.
set -e

PUID="${PUID:-99}"
PGID="${PGID:-100}"

if [ "$(id -u)" = "0" ]; then
    if [ "$(id -g app)" != "$PGID" ]; then
        groupmod -o -g "$PGID" app
    fi
    if [ "$(id -u app)" != "$PUID" ]; then
        usermod -o -u "$PUID" app
    fi

    # Nur /config anfassen - /movies kann Hunderttausende Dateien enthalten.
    chown -R app:app /config 2>/dev/null || \
        echo "Hinweis: /config liess sich nicht uebereignen - Rechte pruefen."

    echo "Starte als UID ${PUID}, GID ${PGID}."
    exec gosu app "$@"
fi

echo "Starte als UID $(id -u), GID $(id -g) (PUID/PGID werden nicht angewandt)."
exec "$@"
