"""Language selection and request behaviour against TMDB."""

import pytest

import tmdb


def video(key, lang, vtype="Trailer", official=True, size=1080, site="YouTube"):
    return {"key": key, "iso_639_1": lang, "type": vtype, "official": official,
            "size": size, "site": site, "name": key, "iso_3166_1": lang.upper()}


def tagged(videos):
    """Reproduce what fetch_videos adds to every video."""
    out = []
    for v in videos:
        v = dict(v)
        v["lang"] = (v.get("iso_639_1") or "").lower() or "??"
        out.append(v)
    return out


def test_german_trailer_wins():
    videos = tagged([video("en1", "en"), video("de1", "de")])
    assert tmdb.pick_best(videos, ["de"])["key"] == "de1"


def test_no_silent_fallback_to_english():
    videos = tagged([video("en1", "en")])
    assert tmdb.pick_best(videos, ["de"]) is None
    assert tmdb.pick_best(videos, ["de", "en"])["key"] == "en1"


def test_trailer_beats_teaser_and_official_beats_fanmade():
    videos = tagged([
        video("teaser", "de", vtype="Teaser"),
        video("unofficial", "de", official=False),
        video("right", "de"),
    ])
    assert tmdb.pick_best(videos, ["de"])["key"] == "right"


def test_only_youtube_trailers_qualify():
    videos = tagged([
        video("vimeo", "de", site="Vimeo"),
        video("featurette", "de", vtype="Featurette"),
        video("good", "de"),
    ])
    keys = [v["key"] for v in tmdb.sort_candidates(videos, ["de"])]
    assert keys == ["good"]


def test_language_of_known_video():
    videos = tagged([video("en1", "en"), video("de1", "de")])
    assert tmdb.language_of(videos, "en1") == "en"
    assert tmdb.language_of(videos, "nope") is None
    assert tmdb.language_of(videos, None) is None


def test_fetch_stops_once_the_language_is_there(monkeypatch):
    """The first request already returns German - asking further would turn a
    run over 1600 movies into a flood of requests."""
    calls = []

    def fake_get(path, api_key, **params):
        calls.append(params)
        return {"results": [video("de1", "de"), video("en1", "en")]}

    monkeypatch.setattr(tmdb, "get", fake_get)
    result = tmdb.fetch_videos("550", "key", ["de"])
    assert len(calls) == 1
    assert {v["lang"] for v in result} == {"de", "en"}


def test_fetch_keeps_asking_when_nothing_matches(monkeypatch):
    calls = []

    def fake_get(path, api_key, **params):
        calls.append(params)
        return {"results": [video("en1", "en")]}

    monkeypatch.setattr(tmdb, "get", fake_get)
    tmdb.fetch_videos("550", "key", ["de"])
    assert len(calls) > 1


def test_missing_api_key_gives_a_clear_message():
    with pytest.raises(tmdb.TmdbError) as error:
        tmdb.get("/movie/550/videos", "")
    assert "API key" in str(error.value)
