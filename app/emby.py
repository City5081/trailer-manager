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

# One index of the whole library is far cheaper than a lookup per movie, and it
# stays usable for a while. A miss rebuilds it once, so a brand new item is
# still found.
INDEX_TTL = 600
TIMEOUT = 20


class EmbyError(RuntimeError):
    pass


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

    def configured(self):
        return bool(self.base_url and self.api_key)

    # ------------------------------------------------------------- transport
    def _call(self, method, path, **params):
        if not self.configured():
            raise EmbyError("No Emby address or API key configured.")
        url = "{}{}".format(self.base_url, path)
        if params:
            url += "?" + urlencode(params)
        request = Request(url, method=method)
        request.add_header("Accept", "application/json")
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
                raise EmbyError("Emby rejects the API key (HTTP {}).".format(e.code)) from e
            if e.code == 404:
                raise EmbyError("Emby answered 404 for {} - is the address "
                                "correct?".format(path)) from e
            raise EmbyError("Emby answered with HTTP {} - {}".format(e.code, e.reason)) from e
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

        just_built = False
        if not self._index or time.time() - self._index_time >= INDEX_TTL:
            self._build_index()
            just_built = True

        found = self._index.get(key)
        if found is None and not just_built:
            # The item may have been added since the index was built. Only
            # worth another look if the index is not the one we just fetched.
            self._build_index()
            found = self._index.get(key)
        return found

    def refresh(self, tmdb_id):
        """Ask the server to re-read one item. True when it was told to.

        The NFO is local metadata, so a plain refresh picks the trailer up.
        Images are left alone and nothing is replaced from the internet - this
        should never undo what the user has set.
        """
        item_id = self.item_id(tmdb_id)
        if not item_id:
            return False
        self._call("POST", "/Items/{}/Refresh".format(item_id),
                   MetadataRefreshMode="FullRefresh",
                   ImageRefreshMode="None",
                   ReplaceAllMetadata="false",
                   ReplaceAllImages="false")
        return True

    def forget_index(self):
        self._index = {}
        self._index_time = 0.0
