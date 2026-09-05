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
- **Watches Emby** for newly added items and gives them a trailer within
  minutes, without anything to configure on the Emby side.
- **Web interface** with a movie list, search, filters, sortable columns —
  including *trailer set*, so the newest additions come first — per-movie lookup
  and manual editing of the link; every trailer can be previewed on YouTube.
- **Login** with username and password.
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
| `NFO_WAIT` | seconds to keep looking for a late NFO (default 60) |
| `EMBY_URL`, `EMBY_API_KEY` | media server to watch and notify |
| `EMBY_POLL_MINUTES` | how often to ask for new items (`0` = off) |
| `NOTIFY_SERVICE` | first target's service: `gotify`, `ntfy`, `discord`, `webhook` |
| `NOTIFY_URL`, `NOTIFY_TOKEN` | first target's address and token; more are added in the interface |
| `NOTIFY_ON_NEW`, `NOTIFY_ON_RUN`, `NOTIFY_ON_ERROR` | which events to announce |
| `UI_LANGUAGE` | `de` or `en` |
| `AUTH_DISABLED` | `true` only when an auth proxy handles the login |
| `PUID` / `PGID` | ownership of files written by the container |
| `PORT` | port inside the container (default 8081) |

The published port and the mounted folders are plain values in
`docker-compose.yml`. `MOVIES_DIR` only seeds the very first library; after that
the folders come from the database.

## Emby

Address and API key, under *Settings → Emby*, cover two jobs. The key is created
in Emby under *Settings → Advanced → API keys*; *Test Emby* reports the server
name, version and how many items were found. Jellyfin speaks the same interface.

**New items.** Every few minutes the server is asked what has been added since
last time — one request, and whatever is new gets its trailer right away instead
of waiting for the next scheduled run. Nothing has to be configured inside Emby,
and no connection has to reach this container from outside. The first ask only
notes where to start, so connecting a server does not look up the whole library
at once.

Emby reports its own paths (`/mnt/user/Movies/Film (2024)/…`) while this
container sees `/movies`, so items are matched by folder name inside the
configured libraries, and by TMDB id where one is known. Emby creates a library entry as soon as it sees the video file and writes the
NFO once the metadata is in, so an item can be reported a moment before its NFO
exists. When nothing is there yet the folder is checked again over the next
minute. Asking every few minutes usually lands well after the NFO is written, so
this is a safety net rather than something to tune — `NFO_WAIT` sets the seconds
or turns it off with `0`.

**Written trailers.** Emby only reads a changed NFO on its next library scan,
every twelve hours by default, so each written trailer is announced as it is
written, for that one item. This always happens when a server is configured —
writing a trailer and then leaving the server unaware of it has no upside. The
refresh replaces
nothing — images are left alone and no internet provider is asked — so it cannot
undo anything set by hand. If the server is down or the key is wrong, the trailer
is still written and a warning goes to the log.

There is no webhook. Asking the server is simpler to set up, needs no inbound
connection, and gives better data than parsing notification payloads.

## Notifications

*Settings → Notifications* chooses what gets reported; *Targets* is where the
services go. Several targets can be active at once — Gotify on the phone and a
Discord channel, say — and each can be switched off on its own without losing
its settings. Add one by picking the service, an address and, where the service
wants one, a token:

| Service | Address | Token |
|---|---|---|
| Gotify | `https://gotify.example.com` | application token |
| ntfy | `https://ntfy.sh/my-topic` | only for protected topics |
| Discord | the full webhook URL | — |
| webhook | any URL, receives JSON | optional, sent as a bearer |

Four things can be announced, each on its own: a newly added item getting its
trailer, a summary after each automatic run, errors, and warnings.

Warnings are picked up from the log itself rather than from a handful of chosen
places, so anything worth a warning reaches you — a refresh Emby refused, an NFO
that never appeared, a run skipped for want of an API key. Repeats are held back
for ten minutes and there is a ceiling per hour, because a share that goes away
warns once per movie. Individual messages are
only sent for items the media server reported as new, so a run across a whole
library reports once rather than several hundred times.

One unreachable target never costs the message on the others, and never affects
the trailer — it is already written by then.

**Adding another service** is one function in `app/notify.py`: it turns a message
into a URL, headers and a body, and gets listed in `SERVICES`. Nothing else in
the application changes. All four supported services are between three and eight
lines each.

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
logins, and `X-Frame-Options`/`nosniff`. Nothing is exposed to the outside: the
media server is contacted by this container, never the other way round.

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
  main.py      Flask application: login, setup wizard, libraries, pages
  scanner.py   scanning, automatic runs, schedule, new items from Emby
  db.py        SQLite: libraries, entries, log, settings, runs
  tmdb.py      TMDB client with robust language handling
  emby.py      tells Emby or Jellyfin to re-read a changed NFO
  notify.py    Gotify, ntfy, Discord or a plain webhook
  nfo.py       reading and writing NFOs, link formats
  i18n.py      German/English translations
docker/
  entrypoint.sh  applies PUID/PGID and drops privileges
tests/         pytest suite (no network access)
tools/
  hash_password.py  creates WEB_PASSWORD_HASH
  render_logo.py    regenerates the PNG logos from logo.svg
```

## License

MIT — see [LICENSE](LICENSE).
