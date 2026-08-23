"""Einlesen, Auswahl der zu pruefenden Filme, Ablauf eines Durchgangs."""

import threading
import time

import db
import nfo
import scanner as scanner_mod
import tmdb


def einstellungen(**abweichend):
    werte = {"languages": "de", "link_format": "emby", "keep_format": "1",
             "backup": "0", "lockdata": "0", "tmdb_api_key": "testkey",
             "recheck_days": "30", "overwrite_existing": "0",
             "scan_on_start": "0", "scan_interval_hours": "0"}
    werte.update(abweichend)
    return lambda key, default=None: werte.get(key, default)


def test_einlesen_erkennt_neue_und_geloeschte_filme(tmp_path, movie_nfo):
    bib = movie_nfo.parent.parent
    s = scanner_mod.Scanner(bib, einstellungen())

    ergebnis = s.scan_library(workers=2)
    assert ergebnis["files"] == 1 and ergebnis["changed"] == 1
    assert db.get_movie(str(movie_nfo))["title"] == "Testfilm"

    # Unveraenderte Dateien werden beim zweiten Lauf nicht neu geparst.
    assert s.scan_library(workers=2)["changed"] == 0

    movie_nfo.unlink()
    assert s.scan_library(workers=2)["removed"] == 1
    assert db.get_movie(str(movie_nfo)) is None


def test_traegt_deutschen_trailer_ein(movie_nfo, monkeypatch):
    s = scanner_mod.Scanner(movie_nfo.parent.parent, einstellungen())
    s.scan_library(workers=2)

    monkeypatch.setattr(tmdb, "fetch_videos",
                        lambda *a, **k: [{"key": "dQw4w9WgXcQ", "lang": "de",
                                          "type": "Trailer", "official": True,
                                          "site": "YouTube", "size": 1080}])
    status, _ = s.process_movie(db.get_movie(str(movie_nfo)))
    assert status == "ok"

    erwartet = nfo.format_link("dQw4w9WgXcQ", "emby")
    assert nfo.parse_nfo(movie_nfo)["trailer"] == erwartet
    zeile = db.get_movie(str(movie_nfo))
    assert zeile["state"] == "ok" and zeile["trailer_lang"] == "de"


def test_ohne_treffer_wird_nichts_geschrieben(movie_nfo, monkeypatch):
    s = scanner_mod.Scanner(movie_nfo.parent.parent, einstellungen())
    s.scan_library(workers=2)
    monkeypatch.setattr(tmdb, "fetch_videos", lambda *a, **k: [])
    status, _ = s.process_movie(db.get_movie(str(movie_nfo)))
    assert status == "no_trailer"
    assert nfo.parse_nfo(movie_nfo)["trailer"] == ""


def test_film_ohne_ids_wird_gemeldet(tmp_path):
    ordner = tmp_path / "Ohne IDs (2020)"
    ordner.mkdir()
    pfad = ordner / "film.nfo"
    pfad.write_text("<movie><title>Ohne IDs</title></movie>", encoding="utf-8")

    s = scanner_mod.Scanner(tmp_path, einstellungen())
    s.scan_library(workers=2)
    status, _ = s.process_movie(db.get_movie(str(pfad)))
    assert status == "no_id"


def test_vorhandenes_linkformat_wird_beibehalten(movie_nfo, monkeypatch):
    """Steht in der NFO schon eine YouTube-URL, soll sie nicht auf plugin://
    umgestellt werden - sonst aendert sich bei jedem Lauf jede Datei."""
    nfo.write_trailer(movie_nfo, nfo.format_link("aaaaaaaaaaa", "url"), backup=False)
    s = scanner_mod.Scanner(movie_nfo.parent.parent, einstellungen())
    s.scan_library(workers=2)
    monkeypatch.setattr(tmdb, "fetch_videos",
                        lambda *a, **k: [{"key": "dQw4w9WgXcQ", "lang": "de",
                                          "type": "Trailer", "official": True,
                                          "site": "YouTube", "size": 1080}])
    s.process_movie(db.get_movie(str(movie_nfo)))
    assert nfo.parse_nfo(movie_nfo)["trailer"].startswith("https://www.youtube.com/")


def test_nur_ein_durchgang_gleichzeitig(tmp_path):
    """Zwei Klicks kurz hintereinander duerfen keine zwei Laeufe starten."""
    s = scanner_mod.Scanner(tmp_path, einstellungen())
    assert s._claim() is True
    assert s._claim() is False

    ergebnisse = []
    threads = [threading.Thread(target=lambda: ergebnisse.append(s._claim()))
               for _ in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert ergebnisse == [False] * 10

    s._release()
    assert s._claim() is True
    s._release()


def test_pending_waehlt_nur_offene_filme(tmp_path):
    daten = {"title": "X", "year": "2020", "tmdb": "1", "imdb": None, "trailer": ""}
    fertig = str(tmp_path / "fertig.nfo")
    offen = str(tmp_path / "offen.nfo")
    alt = str(tmp_path / "alt.nfo")
    for pfad in (fertig, offen, alt):
        db.upsert_movie(pfad, str(tmp_path), daten, 1.0, 10)

    db.mark_result(fertig, "ok", "fertig", trailer="plugin://x", written=True)
    db.mark_result(alt, "no_trailer", "nichts gefunden")
    with db.connect() as con:                     # letzte Pruefung lange her
        con.execute("UPDATE movies SET last_checked=? WHERE path=?",
                    (time.time() - 90 * 86400, alt))

    pfade = {r["path"] for r in db.pending_movies(30 * 86400)}
    assert offen in pfade and alt in pfade and fertig not in pfade

    alle = {r["path"] for r in db.pending_movies(30 * 86400, overwrite_existing=True)}
    assert fertig in alle
