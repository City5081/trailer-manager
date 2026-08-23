"""TMDB access.

The language filter of the videos endpoint returns nothing for some language
and region combinations even though the video exists. So we query more than
once and sort by the iso_639_1 field on the video itself. Errors are never
swallowed - failing quietly would look exactly like "this movie has no trailer".
"""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.themoviedb.org/3"


class TmdbError(RuntimeError):
    pass


def _explain(error):
    text = str(error)
    if "CERTIFICATE_VERIFY_FAILED" in text or "SSL" in text.upper():
        return text + "  (check the certificates in the container: ca-certificates)"
    if "getaddrinfo" in text or "Name or service not known" in text:
        return text + "  (DNS/network: api.themoviedb.org is unreachable)"
    return text


def get(path, api_key, **params):
    if not api_key:
        raise TmdbError("No TMDB API key configured.")
    params["api_key"] = api_key
    url = "{}{}?{}".format(API, path, urlencode(params))
    req = Request(url, headers={"Accept": "application/json",
                                "User-Agent": "trailer-manager/0.2"})
    last = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=25) as resp:
                return json.load(resp)
        except HTTPError as e:
            if e.code == 429:
                time.sleep(2 + attempt * 2)
                last = e
                continue
            if e.code == 404:
                return None
            if e.code in (401, 403):
                raise TmdbError("TMDB rejects the API key (HTTP {}). Please check "
                                "that this is the v3 API key, not the read access "
                                "token.".format(e.code)) from e
            raise TmdbError("TMDB answered with HTTP {} - {}"
                            .format(e.code, e.reason)) from e
        except URLError as e:
            last = e
            time.sleep(1 + attempt)
        except ValueError as e:
            raise TmdbError("Unreadable answer from TMDB: {}".format(e)) from e
    raise TmdbError("Cannot reach api.themoviedb.org. {}".format(
        _explain(getattr(last, "reason", last))))


def selftest(api_key):
    data = get("/movie/550/videos", api_key, language="en-US")
    if data is None:
        raise TmdbError("Unexpected answer from TMDB.")
    return len(data.get("results") or [])


# TMDB keeps movies and TV shows behind separate paths; everything else about
# the videos endpoint is identical.
KIND_PATHS = {"movie": "movie", "tv": "tv"}
KIND_RESULTS = {"movie": "movie_results", "tv": "tv_results"}


def lookup_by_imdb(imdb_id, api_key, kind="movie"):
    data = get("/find/{}".format(imdb_id), api_key, external_source="imdb_id")
    results = (data or {}).get(KIND_RESULTS.get(kind, "movie_results")) or []
    return str(results[0]["id"]) if results else None


def _rank(v):
    vtype = (v.get("type") or "").lower()
    return ({"trailer": 0, "teaser": 1}.get(vtype, 3),
            0 if v.get("official") else 1,
            -int(v.get("size") or 0),
            v.get("published_at") or "")


def _usable(videos):
    """Only YouTube trailers and teasers - Emby cannot play anything else."""
    return [v for v in videos
            if (v.get("site") or "").lower() == "youtube" and v.get("key")
            and (v.get("type") or "").lower() in ("trailer", "teaser")]


def fetch_videos(tmdb_id, api_key, langs, kind="movie"):
    """Collect all videos of a movie or TV show, each with its actual language."""
    section = KIND_PATHS.get(kind, "movie")
    variants = []
    for lang in langs:
        base = lang.split("-")[0]
        variants.extend([lang, base, "{}-{}".format(base, base.upper())])
    variants.extend(["en-US", "en"])
    variants = list(dict.fromkeys(v for v in variants if v))

    include = ",".join(list(dict.fromkeys(
        [l.split("-")[0] for l in langs] + ["en", "null"]))[:5])

    wanted = {l.split("-")[0].lower() for l in langs}
    found = {}

    def absorb(results):
        for v in results or []:
            if v.get("key") and v["key"] not in found:
                v = dict(v)
                v["lang"] = (v.get("iso_639_1") or "").lower() or "??"
                v["region"] = (v.get("iso_3166_1") or "").upper()
                found[v["key"]] = v

    def have_wanted():
        return any(v.get("lang") in wanted for v in _usable(found.values()))

    data = get("/{}/{}/videos".format(section, tmdb_id), api_key,
               language=variants[0], include_video_language=include)
    absorb((data or {}).get("results"))
    if have_wanted():
        # The first request usually returns everything. Only when nothing in the
        # wanted language shows up are the other variants worth it - otherwise a
        # library of 1600 movies would mean a few thousand requests too many.
        return list(found.values())

    for lang in variants:
        data = get("/{}/{}/videos".format(section, tmdb_id), api_key, language=lang)
        absorb((data or {}).get("results"))
        if have_wanted():
            break
    return list(found.values())


def sort_candidates(videos, langs):
    order = [l.split("-")[0].lower() for l in langs]

    def key(v):
        lang = v.get("lang", "??")
        pos = order.index(lang) if lang in order else len(order) + 1
        return (pos,) + _rank(v)

    return sorted(_usable(videos), key=key)


def pick_best(videos, langs):
    """Best match - strictly within the wanted languages."""
    order = [l.split("-")[0].lower() for l in langs]
    cands = [v for v in sort_candidates(videos, langs) if v.get("lang") in order]
    return cands[0] if cands else None


def language_of(videos, video_id):
    """Language of a specific video id, if TMDB knows it.

    Used for links that were already in the NFO: they came from Emby, so we
    never picked their language ourselves.
    """
    if not video_id:
        return None
    for v in videos:
        if v.get("key") == video_id:
            lang = v.get("lang") or (v.get("iso_639_1") or "").lower()
            return lang or None
    return None
