<p align="center">
  <img src="app/static/logo.svg" width="72" alt="">
</p>

<h1 align="center">Trailer Manager</h1>

<p align="center">
  Writes trailers from <a href="https://www.themoviedb.org">themoviedb.org</a>
  in the language you want into the <code>.nfo</code> files of an Emby library —
  on a schedule, at the push of a button, or the moment Emby or Jellyseerr
  reports a new item.
</p>

---

Emby fetches trailers from TMDB by itself and almost always ends up with the
English one. When a `<trailer>` entry is present in the NFO, Emby uses that
instead. This tool fills in that entry.

Any number of libraries can be configured, each pointing at its own folder and
holding either movies or TV shows — a German movie library, a separate one for
anime films looking for Japanese trailers, and one for series, side by side.

## Features

- **Setup wizard** on first start: account, library folder, TMDB API key,
  language and schedule are asked for in the browser. No environment variables
  needed.
- **Several libraries**, each with its own folder, its own kind (movies or TV
  shows) and its own overrides for language, link format and recheck interval.
  Anything left empty follows the global setting.
- **Persistent database** (SQLite): an automatic run only looks at entries that
  are new, whose NFO changed, or that came back empty last time. With 1600
  movies the second run takes seconds instead of hours.
- **TV shows**: the `tvshow.nfo` of each series gets the trailer; episode NFOs
  are never even opened, so a library with thousands of episodes still scans
  quickly.
- **Schedule** at a configurable interval, plus a run at startup.
- **Webhook** for Emby, Jellyfin and Jellyseerr: new movie → trailer set at once.
- **Web interface** with a movie list, search, filters, per-movie lookup and
  manual editing of the link; every trailer can be previewed on YouTube first.
- **Login** with username and password, webhook secured separately by a token.
- **Bilingual** German/English, switchable in the header.
- **Robust TMDB queries**: the `language` filter of the videos endpoint returns
  nothing for some language and region combinations even though the video
  exists. So the query is repeated and sorted by the language field on the video
  itself. As soon as something in the wanted language shows up, it stops.
- **Both link formats**: `plugin://plugin.video.youtube/play/?video_id=…` (what
  Emby writes), the older Kodi form, and plain YouTube URLs.
- **Safe writing**: the NFO is written to a sibling file and then renamed. If
  the write is cut short, the old file stays intact.

## Quick start

```bash
mkdir trailer-manager && cd trailer-manager
curl -O https://raw.githubusercontent.com/City5081/trailer-manager/main/docker-compose.yml
# adjust the paths under volumes:, then
docker compose up -d
```

Then open `http://SERVER:8099` and follow the setup wizard.

`docker-compose.yml` is the only file to edit, and usually only its `volumes:`
section. There is no `.env`: nothing in the compose file is secret, because the
account and the TMDB API key are asked for in the browser and stored in
`/config`.

The image is `ghcr.io/city5081/trailer-manager:latest` — built for `linux/amd64` and
`linux/arm64`. The name is lowercase throughout because Docker does not allow
capitals in image names.

### Unraid

Use *Docker → Add Container*, or the Compose Manager: paste the contents of
`docker-compose.yml` into *Edit Stack*. No `.env` file is involved — every value
is written out in the compose file itself.

| Path / variable | Value |
|---|---|
| `/movies` | share holding the movies, **read/write** |
| `/config` | e.g. `/mnt/user/appdata/trailer-manager` |
| Port | `8099` → `8081` |
| `PUID` / `PGID` | `99` / `100` |

The container starts as root, switches the `app` user to `PUID`/`PGID` and then
drops privileges. NFOs written afterwards belong to the same user as the rest of
the share.

If the NFOs belong to Emby or another container, *Tools → New Permissions*
helps; otherwise writing fails with "Permission denied". A failed write writes
the full diagnosis to the log by itself: owner, permissions and an actual write
test on the folder.

## Libraries

The wizard sets up the first one. More are added under *Settings → Libraries*:
a name, the folder **as seen inside the container**, and whether it holds movies
or TV shows.

Every extra folder needs a volume in `docker-compose.yml` first, otherwise the
container cannot see it. Volumes live there and nowhere else — adding a library
always means adding a line:

```yaml
    volumes:
      - "/mnt/user/appdata/trailer-manager:/config"
      - "/mnt/user/Movies:/movies"
      - "/mnt/user/Anime:/anime"
      - "/mnt/user/Shows:/shows"
```

The left side is the folder on your server, the right side is the path you enter
under *Settings → Libraries*. After changing volumes the container has to be
recreated (`docker compose up -d`), not just restarted.

Then add `/anime` and `/shows` as libraries. Each may override the global
language, link format, backup, lockdata and recheck interval — leave a field
empty to keep the global value. A library can also be disabled temporarily
without losing what has been scanned.

Deleting a library removes its entries from the database only. The NFO files
are never touched.

## Configuration

Everything is configured in the browser: the wizard on first start, and
*Settings* afterwards. The environment variables below are optional and only
useful for unattended deployments — they act as the starting value, and the
interface takes precedence. Add them under `environment:` in the compose file if
you need them.

| Variable | Meaning |
|---|---|
| `WEB_USERNAME`, `WEB_PASSWORD` | skips the wizard's account step |
| `WEB_PASSWORD_HASH` | instead of the plain password; see `tools/hash_password.py` |
| `SECRET_KEY` | session key; empty = generated on first start |
| `COOKIE_SECURE` | `true` behind a reverse proxy with TLS |
| `SESSION_DAYS` | how long a login stays valid (default 30) |
| `TMDB_API_KEY` | **v3 API key**, not the read access token |
| `LANGUAGES` | `de` = German trailers only, `de,en` falls back to English |
| `LINK_FORMAT` | `emby`, `kodi` or `url` |
| `KEEP_FORMAT` | keep the spelling a movie already uses |
| `BACKUP` | write a `.nfo.bak` before the first change |
| `SCAN_INTERVAL_HOURS` | interval, `0` disables the schedule |
| `SCAN_ON_START` | run once when the container starts |
| `RECHECK_DAYS` | retry movies without a hit after this many days |
| `WEBHOOK_WAIT` | seconds to keep looking for a late NFO (default 60) |
| `UI_LANGUAGE` | `de` or `en` |
| `WEBHOOK_TOKEN` | empty = generated on first start |
| `AUTH_DISABLED` | `true` only when an auth proxy handles the login |
| `PUID` / `PGID` | ownership of files written by the container |
| `PORT` | port inside the container (default 8081) |

The published port and the mounted folders are plain values in
`docker-compose.yml`. `MOVIES_DIR` only seeds the very first library; after that
the folders come from the database.

## Webhook

Nothing needs preparing: if `WEBHOOK_TOKEN` is unset, the first start generates
one and stores it in `/config/webhook_token`. The finished address is shown
under *Settings → Webhook* — copy it from there:

```
http://SERVER:8099/webhook?token=YOUR_TOKEN
```

**Emby** — Settings → Notifications → Webhooks → Add:

| Field | Value |
|---|---|
| URL | the address above |
| Request content type | `application/json` |
| Events | *New media added* (under Library) only |
| Limit library events to | Movies |

`multipart/form-data` is understood as well, but JSON is less ambiguous. Labels
differ slightly between Emby versions.

**Jellyfin** — Dashboard → Plugins → Webhook → Add Generic Destination,
notification type *Item Added*, item type *Movies*.

**Jellyseerr** — Settings → Notifications → Webhook, trigger *Media Available*.

The item is matched by the file path from the notification first, then by TMDB
id. The path also says which library it belongs to, so only that one folder is
read — never the whole collection. For a series the notification points at an
episode file, so the path is walked upwards until the `tvshow.nfo` turns up.

Emby creates the video file first and writes the NFO shortly after, so a webhook
often arrives while there is still nothing to find. Instead of giving up, the
folder is checked again a few times over the next minute (*Settings → Wait for
the NFO after a webhook*, `0` turns it off).

### Did it arrive?

Emby has a test button on its webhook settings. Every request that gets past the
token check is logged, so after pressing it you see the arrival in two places:
*Settings → Webhook* shows the timestamp of the last one, and *Log* holds the
full line with the event name and the sending address. A test event is
deliberately not acted upon — it shows up as received and then ignored, which is
exactly the signal you want.

If nothing appears at all, the request never reached the container: check the
address, the port and whether the token in the URL is complete.

## What gets checked

An automatic run picks up:

- new entries, and entries whose NFO changed since last time
- entries without a trailer entry
- entries that came back empty, once the last check is older than the recheck
  interval of their library (TMDB gains trailers all the time)

Finished entries are left alone — unless *recheck movies that are already done*
is set, or you press *Recheck all*. A single library can be rechecked on its own
from *Settings → Libraries*.

## Security

The interface does not belong on the open internet unprotected. To reach it from
outside, put a reverse proxy with TLS in front (Nginx Proxy Manager, SWAG, …) and
set `COOKIE_SECURE=true`.

Built in: CSRF tokens on every form, a growing delay after repeated failed
logins, `X-Frame-Options`/`nosniff`, and a webhook that only answers with a valid
token — generated on first start, so there is no unprotected window.

The setup wizard is reachable without a login until an account exists, which is
the usual first run window. Complete it right after the first start; from then on
it sits behind the login like everything else.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/ruff check .
```

Run locally without a container:

```bash
DATA_DIR=./config MOVIES_DIR=/path/to/Movies .venv/bin/python app/main.py
```

The test suite needs no network: TMDB is stubbed out everywhere.

## Layout

```
app/
  main.py      Flask application: login, setup wizard, libraries, pages, webhook
  scanner.py   scanning, automatic runs, schedule, webhook handling
  db.py        SQLite: libraries, entries, log, settings, runs
  tmdb.py      TMDB client with robust language handling
  nfo.py       reading and writing NFOs, link formats
  i18n.py      German/English translations
docker/
  entrypoint.sh  applies PUID/PGID and drops privileges
tests/         pytest suite (no network access)
tools/
  hash_password.py  creates WEB_PASSWORD_HASH
```

## License

MIT — see [LICENSE](LICENSE).
