"""Reading the library, picking what to check, and a full run."""

import threading
import time

import db
import nfo
import scanner as scanner_mod
import tmdb


def settings(**overrides):
    values = {"languages": "de", "link_format": "emby", "keep_format": "1",
              "backup": "0", "lockdata": "0", "tmdb_api_key": "testkey",
              "recheck_days": "30", "overwrite_existing": "0",
              "scan_on_start": "0", "scan_interval_hours": "0"}
    values.update(overrides)
    return lambda key, default=None: values.get(key, default)


def german_trailer(*_a, **_k):
    return [{"key": "dQw4w9WgXcQ", "lang": "de", "type": "Trailer",
             "official": True, "site": "YouTube", "size": 1080}]


def test_scan_detects_new_and_removed_movies(movie_nfo, library):
    s = scanner_mod.Scanner(settings())

    result = s.scan_library(library, workers=2)
    assert result["files"] == 1 and result["changed"] == 1
    assert db.get_movie(str(movie_nfo))["title"] == "Test Movie"

    # Unchanged files are not parsed again on the second pass.
    assert s.scan_library(library, workers=2)["changed"] == 0

    movie_nfo.unlink()
    assert s.scan_library(library, workers=2)["removed"] == 1
    assert db.get_movie(str(movie_nfo)) is None


def test_writes_the_german_trailer(movie_nfo, library, monkeypatch):
    s = scanner_mod.Scanner(settings())
    s.scan_library(library, workers=2)

    monkeypatch.setattr(tmdb, "fetch_videos", german_trailer)
    status, _ = s.process_movie(db.get_movie(str(movie_nfo)))
    assert status == "ok"

    expected = nfo.format_link("dQw4w9WgXcQ", "emby")
    assert nfo.parse_nfo(movie_nfo)["trailer"] == expected
    row = db.get_movie(str(movie_nfo))
    assert row["state"] == "ok" and row["trailer_lang"] == "de"


def test_nothing_is_written_without_a_hit(movie_nfo, library, monkeypatch):
    s = scanner_mod.Scanner(settings())
    s.scan_library(library, workers=2)
    monkeypatch.setattr(tmdb, "fetch_videos", lambda *a, **k: [])
    status, _ = s.process_movie(db.get_movie(str(movie_nfo)))
    assert status == "no_trailer"
    assert nfo.parse_nfo(movie_nfo)["trailer"] == ""


def test_language_of_an_existing_trailer_is_recorded(movie_nfo, library, monkeypatch):
    """Links that Emby wrote have no language attached. Without this the whole
    language column stays empty for an existing library."""
    english = nfo.format_link("bbbbbbbbbbb", "emby")
    nfo.write_trailer(movie_nfo, english, backup=False)

    s = scanner_mod.Scanner(settings())
    s.scan_library(library, workers=2)
    assert db.get_movie(str(movie_nfo))["trailer_lang"] is None

    monkeypatch.setattr(tmdb, "fetch_videos", lambda *a, **k: [
        {"key": "bbbbbbbbbbb", "lang": "en", "type": "Trailer",
         "official": True, "site": "YouTube", "size": 1080}])
    status, _ = s.process_movie(db.get_movie(str(movie_nfo)))

    # No German trailer exists, so nothing is written - but we now know the
    # existing link is English.
    assert status == "no_trailer"
    assert db.get_movie(str(movie_nfo))["trailer_lang"] == "en"
    assert nfo.parse_nfo(movie_nfo)["trailer"] == english


def test_movie_without_ids_is_reported(tmp_path, library):
    folder = tmp_path / "No IDs (2020)"
    folder.mkdir()
    path = folder / "movie.nfo"
    path.write_text("<movie><title>No IDs</title></movie>", encoding="utf-8")

    s = scanner_mod.Scanner(settings())
    s.scan_library(library, workers=2)
    status, _ = s.process_movie(db.get_movie(str(path)))
    assert status == "no_id"


def test_existing_link_format_is_kept(movie_nfo, library, monkeypatch):
    """If the NFO already holds a plain YouTube URL, it must not be switched to
    plugin:// - otherwise every run rewrites every file."""
    nfo.write_trailer(movie_nfo, nfo.format_link("aaaaaaaaaaa", "url"), backup=False)
    s = scanner_mod.Scanner(settings())
    s.scan_library(library, workers=2)
    monkeypatch.setattr(tmdb, "fetch_videos", german_trailer)
    s.process_movie(db.get_movie(str(movie_nfo)))
    assert nfo.parse_nfo(movie_nfo)["trailer"].startswith("https://www.youtube.com/")


def test_only_one_run_at_a_time():
    """Two quick clicks must not start two runs."""
    s = scanner_mod.Scanner(settings())
    assert s._claim() is True
    assert s._claim() is False

    results = []
    threads = [threading.Thread(target=lambda: results.append(s._claim()))
               for _ in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert results == [False] * 10

    s._release()
    assert s._claim() is True
    s._release()


def test_pending_picks_only_open_movies(tmp_path):
    data = {"title": "X", "year": "2020", "tmdb": "1", "imdb": None, "trailer": ""}
    done = str(tmp_path / "done.nfo")
    open_one = str(tmp_path / "open.nfo")
    stale = str(tmp_path / "stale.nfo")
    for path in (done, open_one, stale):
        db.upsert_movie(path, str(tmp_path), data, 1.0, 10)

    db.mark_result(done, "ok", "done", trailer="plugin://x", written=True)
    db.mark_result(stale, "no_trailer", "nothing found")
    with db.connect() as con:                     # last check long ago
        con.execute("UPDATE movies SET last_checked=? WHERE path=?",
                    (time.time() - 90 * 86400, stale))

    paths = {r["path"] for r in db.pending_movies(30 * 86400)}
    assert open_one in paths and stale in paths and done not in paths

    everything = {r["path"] for r in db.pending_movies(30 * 86400, overwrite_existing=True)}
    assert done in everything


def test_stats_count_the_first_configured_language(tmp_path):
    data = {"title": "Y", "year": "2020", "tmdb": "2", "imdb": None, "trailer": "x"}
    path = str(tmp_path / "lang.nfo")
    db.upsert_movie(path, str(tmp_path), data, 1.0, 10)
    db.note_trailer_lang(path, "fr")

    assert db.stats("fr")["primary_lang"] >= 1
    assert db.stats("fr")["primary_lang_code"] == "fr"
