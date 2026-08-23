#!/bin/sh
# Start the application under the requested user id.
#
# On Unraid the movies belong to nobody (99:100). If the container ran as root,
# files written afterwards would belong to root and Emby could no longer touch
# them. So user and group are switched to PUID/PGID and the application is
# handed over with gosu.
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

    # Only touch /config - /movies can hold hundreds of thousands of files.
    chown -R app:app /config 2>/dev/null || \
        echo "Note: /config could not be taken over - check the permissions."

    echo "Starting as UID ${PUID}, GID ${PGID}."
    exec gosu app "$@"
fi

echo "Starting as UID $(id -u), GID $(id -g) (PUID/PGID are not applied)."
exec "$@"
