"""Sprachauswahl und Abfrageverhalten gegenueber TMDB."""

import pytest

import tmdb


def video(key, lang, vtype="Trailer", official=True, size=1080, site="YouTube"):
    return {"key": key, "iso_639_1": lang, "type": vtype, "official": official,
            "size": size, "site": site, "name": key, "iso_3166_1": lang.upper()}


def markiert(videos):
    """Nachbilden, was fetch_videos an jedem Video ergaenzt."""
    out = []
    for v in videos:
        v = dict(v)
        v["lang"] = (v.get("iso_639_1") or "").lower() or "??"
        out.append(v)
    return out


def test_deutscher_trailer_gewinnt():
    videos = markiert([video("en1", "en"), video("de1", "de")])
    assert tmdb.pick_best(videos, ["de"])["key"] == "de1"


def test_ohne_deutschen_trailer_kein_rueckfall_auf_englisch():
    videos = markiert([video("en1", "en")])
    assert tmdb.pick_best(videos, ["de"]) is None
    assert tmdb.pick_best(videos, ["de", "en"])["key"] == "en1"


def test_trailer_vor_teaser_und_offiziell_vor_inoffiziell():
    videos = markiert([
        video("teaser", "de", vtype="Teaser"),
        video("inoffiziell", "de", official=False),
        video("richtig", "de"),
    ])
    assert tmdb.pick_best(videos, ["de"])["key"] == "richtig"


def test_nur_youtube_trailer_kommen_in_frage():
    videos = markiert([
        video("vimeo", "de", site="Vimeo"),
        video("featurette", "de", vtype="Featurette"),
        video("gut", "de"),
    ])
    keys = [v["key"] for v in tmdb.sort_candidates(videos, ["de"])]
    assert keys == ["gut"]


def test_fetch_videos_hoert_auf_wenn_die_sprache_da_ist(monkeypatch):
    """Die erste Abfrage liefert schon Deutsch - dann darf nicht weitergefragt
    werden, sonst wird aus einem Lauf ueber 1600 Filme eine Abfrageflut."""
    aufrufe = []

    def fake_get(path, api_key, **params):
        aufrufe.append(params)
        return {"results": [video("de1", "de"), video("en1", "en")]}

    monkeypatch.setattr(tmdb, "get", fake_get)
    ergebnis = tmdb.fetch_videos("550", "key", ["de"])
    assert len(aufrufe) == 1
    assert {v["lang"] for v in ergebnis} == {"de", "en"}


def test_fetch_videos_fragt_weiter_wenn_nichts_passt(monkeypatch):
    aufrufe = []

    def fake_get(path, api_key, **params):
        aufrufe.append(params)
        return {"results": [video("en1", "en")]}

    monkeypatch.setattr(tmdb, "get", fake_get)
    tmdb.fetch_videos("550", "key", ["de"])
    assert len(aufrufe) > 1


def test_ohne_api_key_klare_meldung():
    with pytest.raises(tmdb.TmdbError) as fehler:
        tmdb.get("/movie/550/videos", "")
    assert "API-Key" in str(fehler.value)
