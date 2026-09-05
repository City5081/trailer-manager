"""Talking to Emby (or Jellyfin).

Two jobs. Asking what was added recently, which is how new films reach us, and
telling the server that an NFO changed.

Emby only notices an edited NFO when it scans, which by default happens every
twelve hours. A trailer written now would sit there unseen until then, so the
server is asked to refresh exactly the one item instead.

Items are found by their TMDB id, not by path: the server sees the library
under its own mount (/mnt/user/Movies), while this container sees /movies, and
those two never match. The provider id is the same on both sides.
"""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from version import USER_AGENT

# One index of the whole library is far cheaper than a lookup per movie, and it
# stays usable for a while. A miss rebuilds it once, so a brand new item is
# still found.
INDEX_TTL = 600
# A film this container knows but the server does not - Emby has not scanned it
# yet, or it lives outside the server's libraries - would otherwise refetch the
# whole library on every single lookup. One rebuild per minute is enough to pick
# up something genuinely new.
MISS_REBUILD_AFTER = 60
TIMEOUT = 20

# What to ask for when telling the server to re-read an item, most specific
# first. Emby and Jellyfin disagree about some of these and answer 400 instead
# of ignoring what they do not know, so each is tried in turn.
REFRESH_PARAMS = (
    {"MetadataRefreshMode": "FullRefresh", "ImageRefreshMode": "None",
     "ReplaceAllMetadata": "false", "ReplaceAllImages": "false"},
    {"MetadataRefreshMode": "FullRefresh", "ReplaceAllMetadata": "false"},
    {"MetadataRefreshMode": "FullRefresh"},
    {},
)


def _explanation(error):
    """Whatever the server said about the failure.

    A 400 usually carries the actual reason in the body, and throwing that away
    turns a specific complaint into a shrug.
    """
    try:
        body = error.read().decode("utf-8", "replace").strip()
    except Exception:                                      # noqa: BLE001
        return ""
    body = " ".join(body.split())
    return ". {}".format(body[:300]) if body else ""


class EmbyError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def normalise(url):
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = "http://" + url
    return url


class Emby:
    def __init__(self, base_url, api_key):
        self.base_url = normalise(base_url)
        self.api_key = (api_key or "").strip()
        self._index = {}
        self._index_time = 0.0
        self._accepted = None          # which parameter set this server took

    def configured(self):
        return bool(self.base_url and self.api_key)

    # ------------------------------------------------------------- transport
    def _call(self, method, path, **params):
        if not self.configured():
            raise EmbyError("No Emby address or API key configured.")
        url = "{}{}".format(self.base_url, path)
        if params:
            url += "?" + urlencode(params)
        # An empty body, not no body: urllib leaves out Content-Length when
        # data is None, and a POST without it is answered with 400 by plenty of
        # servers and proxies.
        request = Request(url, data=b"" if method == "POST" else None, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", USER_AGENT)
        # Emby uses the first header, Jellyfin the second. Sending both keeps
        # one client working against either server.
        request.add_header("X-Emby-Token", self.api_key)
        request.add_header("Authorization",
                           'MediaBrowser Token="{}"'.format(self.api_key))
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                body = response.read()
                if not body:
                    return None
                return json.loads(body.decode("utf-8"))
        except HTTPError as e:
            if e.code in (401, 403):
                raise EmbyError("Emby rejects the API key (HTTP {}).".format(e.code),
                                e.code) from e
            if e.code == 404:
                raise EmbyError("Emby answered 404 for {} - is the address "
                                "correct?".format(path), e.code) from e
            raise EmbyError("Emby answered with HTTP {} - {}{}"
                            .format(e.code, e.reason, _explanation(e)), e.code) from e
        except URLError as e:
            raise EmbyError("Cannot reach {} ({})".format(self.base_url, e.reason)) from e
        except ValueError as e:
            raise EmbyError("Unreadable answer from Emby: {}".format(e)) from e

    # ------------------------------------------------------------------ calls
    def info(self):
        """Server name and version - used by the test button."""
        data = self._call("GET", "/System/Info") or {}
        return {"name": data.get("ServerName") or "?",
                "version": data.get("Version") or "?"}

    def recent_items(self, limit=50):
        """The most recently added movies and series, newest first.

        Filtering by date is done by the caller rather than by the server: the
        parameter for it differs between Emby versions and Jellyfin, while
        sorting by DateCreated works everywhere.
        """
        data = self._call("GET", "/Items", Recursive="true",
                          IncludeItemTypes="Movie,Series",
                          SortBy="DateCreated", SortOrder="Descending",
                          Limit=str(int(limit)), EnableImages="false",
                          Fields="ProviderIds,Path,DateCreated") or {}
        return data.get("Items") or []

    def _build_index(self):
        data = self._call("GET", "/Items", Recursive="true",
                          IncludeItemTypes="Movie,Series",
                          Fields="ProviderIds", EnableImages="false") or {}
        index = {}
        for item in data.get("Items") or []:
            item_id = item.get("Id")
            if not item_id:
                continue
            for name, value in (item.get("ProviderIds") or {}).items():
                if value:
                    index[(name.lower(), str(value))] = item_id
        self._index = index
        self._index_time = time.time()
        return index

    def item_id(self, tmdb_id):
        """Emby's internal id for a TMDB id, or None."""
        if not tmdb_id:
            return None
        key = ("tmdb", str(tmdb_id))

        age = time.time() - self._index_time
        if not self._index or age >= INDEX_TTL:
            self._build_index()
            age = 0.0

        found = self._index.get(key)
        if found is None and age >= MISS_REBUILD_AFTER:
            # The item may have been added since the index was built - but only
            # look again if the index has had time to go out of date.
            self._build_index()
            found = self._index.get(key)
        return found

    def refresh(self, tmdb_id):
        """Ask the server to re-read one item. True when it was told to.

        The NFO is local metadata, so a plain refresh picks the trailer up.
        Nothing is replaced from the internet, so this cannot undo anything set
        by hand.

        Servers differ in which parameters they accept, and one that dislikes a
        parameter answers 400 rather than ignoring it. So the full request is
        tried first and quietly narrowed - a refresh that works is worth more
        than insisting on the exact flags.
        """
        item_id = self.item_id(tmdb_id)
        if not item_id:
            return False

        path = "/Items/{}/Refresh".format(item_id)
        last = None
        for attempt, params in enumerate(REFRESH_PARAMS):
            try:
                self._call("POST", path, **params)
                if attempt:
                    self._accepted = params
                return True
            except EmbyError as e:
                if e.status != 400:
                    raise
                last = e
        raise last

    def forget_index(self):
        self._index = {}
        self._index_time = 0.0
