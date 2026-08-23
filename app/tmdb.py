"""TMDB-Zugriff.

Der language-Filter der Videos-Schnittstelle liefert je nach Sprach-/Regions-
kombination nichts zurueck, obwohl das Video vorhanden ist. Deshalb wird
mehrfach abgefragt und anhand des Feldes iso_639_1 des Videos selbst einsortiert.
Fehler werden nie verschluckt - stilles Scheitern saehe sonst aus wie
"dieser Film hat keinen Trailer".
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
        return text + "  (Zertifikate im Container pruefen: ca-certificates)"
    if "getaddrinfo" in text or "Name or service not known" in text:
        return text + "  (DNS/Netzwerk: api.themoviedb.org nicht erreichbar)"
    return text


def get(path, api_key, **params):
    if not api_key:
        raise TmdbError("Kein TMDB API-Key hinterlegt.")
    params["api_key"] = api_key
    url = "{}{}?{}".format(API, path, urlencode(params))
    req = Request(url, headers={"Accept": "application/json",
                                "User-Agent": "trailer-de/1.0"})
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
                raise TmdbError("TMDB lehnt den API-Key ab (HTTP {}). Bitte den "
                                "v3-API-Key pruefen, nicht das Read-Access-Token."
                                .format(e.code)) from e
            raise TmdbError("TMDB antwortet mit HTTP {} - {}"
                            .format(e.code, e.reason)) from e
        except URLError as e:
            last = e
            time.sleep(1 + attempt)
        except ValueError as e:
            raise TmdbError("Unlesbare Antwort von TMDB: {}".format(e)) from e
    raise TmdbError("Keine Verbindung zu api.themoviedb.org. {}".format(
        _explain(getattr(last, "reason", last))))


def selftest(api_key):
    data = get("/movie/550/videos", api_key, language="en-US")
    if data is None:
        raise TmdbError("Unerwartete Antwort von TMDB.")
    return len(data.get("results") or [])


def lookup_by_imdb(imdb_id, api_key):
    data = get("/find/{}".format(imdb_id), api_key, external_source="imdb_id")
    results = (data or {}).get("movie_results") or []
    return str(results[0]["id"]) if results else None


def _rank(v):
    vtype = (v.get("type") or "").lower()
    return ({"trailer": 0, "teaser": 1}.get(vtype, 3),
            0 if v.get("official") else 1,
            -int(v.get("size") or 0),
            v.get("published_at") or "")


def _usable(videos):
    """Nur YouTube-Trailer und -Teaser - alles andere kann Emby nicht abspielen."""
    return [v for v in videos
            if (v.get("site") or "").lower() == "youtube" and v.get("key")
            and (v.get("type") or "").lower() in ("trailer", "teaser")]


def fetch_videos(tmdb_id, api_key, langs):
    """Alle Videos eines Films einsammeln, je Video die tatsaechliche Sprache."""
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

    data = get("/movie/{}/videos".format(tmdb_id), api_key,
               language=variants[0], include_video_language=include)
    absorb((data or {}).get("results"))
    if have_wanted():
        # Die erste Abfrage liefert meist schon alles. Nur wenn nichts in der
        # gewuenschten Sprache dabei ist, lohnen die weiteren Varianten - sonst
        # waeren es bei 1600 Filmen ein paar tausend Abfragen zu viel.
        return list(found.values())

    for lang in variants:
        data = get("/movie/{}/videos".format(tmdb_id), api_key, language=lang)
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
    """Bester Treffer - ausschliesslich in den gewuenschten Sprachen."""
    order = [l.split("-")[0].lower() for l in langs]
    cands = [v for v in sort_candidates(videos, langs) if v.get("lang") in order]
    return cands[0] if cands else None
