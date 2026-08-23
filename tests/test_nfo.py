"""NFO lesen, schreiben, Linkformate."""

import xml.etree.ElementTree as ET

import pytest

import nfo


def test_video_id_aus_allen_schreibweisen():
    vid = "dQw4w9WgXcQ"
    assert nfo.video_id_from("plugin://plugin.video.youtube/play/?video_id=" + vid) == vid
    kodi = "plugin://plugin.video.youtube/?action=play_video&videoid=" + vid
    assert nfo.video_id_from(kodi) == vid
    assert nfo.video_id_from("https://www.youtube.com/watch?v=" + vid) == vid
    assert nfo.video_id_from("https://youtu.be/" + vid) == vid
    assert nfo.video_id_from("https://www.youtube.com/embed/" + vid) == vid
    assert nfo.video_id_from(vid) == vid


def test_video_id_lehnt_unsinn_ab():
    assert nfo.video_id_from("") is None
    assert nfo.video_id_from(None) is None
    assert nfo.video_id_from("kein Link") is None
    assert nfo.video_id_from("https://vimeo.com/12345") is None


def test_format_und_erkennung_passen_zusammen():
    vid = "dQw4w9WgXcQ"
    for name in ("emby", "kodi", "url"):
        link = nfo.format_link(vid, name)
        assert nfo.detect_format(link) == name
        assert nfo.video_id_from(link) == vid


def test_parse_nfo_liest_ids(movie_nfo):
    data = nfo.parse_nfo(movie_nfo)
    assert data["title"] == "Testfilm"
    assert data["year"] == "2021"
    assert data["tmdb"] == "550"
    assert data["imdb"] == "tt0137523"
    assert data["trailer"] == ""


def test_parse_nfo_ignoriert_fremde_dateien(tmp_path):
    other = tmp_path / "serie.nfo"
    other.write_text("<tvshow><title>Nein</title></tvshow>", encoding="utf-8")
    assert nfo.parse_nfo(other) is None
    kaputt = tmp_path / "kaputt.nfo"
    kaputt.write_text("<movie><title>", encoding="utf-8")
    assert nfo.parse_nfo(kaputt) is None


def test_trailer_schreiben_aendern_entfernen(movie_nfo):
    link = nfo.format_link("dQw4w9WgXcQ", "emby")
    assert nfo.write_trailer(movie_nfo, link, backup=False) is True
    assert nfo.parse_nfo(movie_nfo)["trailer"] == link
    # Der zweite Aufruf mit demselben Wert schreibt nicht noch einmal.
    assert nfo.write_trailer(movie_nfo, link, backup=False) is False

    anderer = nfo.format_link("aaaaaaaaaaa", "emby")
    assert nfo.write_trailer(movie_nfo, anderer, backup=False) is True
    assert nfo.parse_nfo(movie_nfo)["trailer"] == anderer

    assert nfo.write_trailer(movie_nfo, "", backup=False) is True
    assert nfo.parse_nfo(movie_nfo)["trailer"] == ""


def test_uebrige_felder_bleiben_erhalten(movie_nfo):
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=False)
    root = ET.parse(movie_nfo).getroot()
    assert root.findtext("title") == "Testfilm"
    assert len(root.findall("uniqueid")) == 2


def test_sicherungskopie_nur_einmal(movie_nfo):
    bak = movie_nfo.with_suffix(movie_nfo.suffix + ".bak")
    original = movie_nfo.read_bytes()
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=True)
    assert bak.read_bytes() == original
    nfo.write_trailer(movie_nfo, nfo.format_link("aaaaaaaaaaa"), backup=True)
    assert bak.read_bytes() == original          # bleibt der Urzustand


def test_lockdata_wird_gesetzt(movie_nfo):
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"),
                      lockdata=True, backup=False)
    root = ET.parse(movie_nfo).getroot()
    assert root.findtext("lockdata") == "true"


def test_schreiben_hinterlaesst_keine_zwischendateien(movie_nfo):
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=False)
    uebrig = [p.name for p in movie_nfo.parent.iterdir() if p.suffix == ".tmp"]
    assert uebrig == []


def test_kaputte_nfo_bleibt_unangetastet(movie_nfo, monkeypatch):
    """Bricht das Schreiben ab, darf die alte Datei nicht beschaedigt sein."""
    vorher = movie_nfo.read_bytes()

    def kaputt(*args, **kwargs):
        raise OSError("kein Platz mehr")

    monkeypatch.setattr(ET.ElementTree, "write", kaputt)
    with pytest.raises(nfo.WriteError):
        nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=False)
    assert movie_nfo.read_bytes() == vorher


def test_walk_findet_nfos(tmp_path):
    (tmp_path / "Film A").mkdir()
    (tmp_path / "Film A" / "a.nfo").write_text("<movie/>", encoding="utf-8")
    (tmp_path / ".versteckt").mkdir()
    (tmp_path / ".versteckt" / "b.nfo").write_text("<movie/>", encoding="utf-8")
    (tmp_path / "Film A" / "film.mkv").write_text("x", encoding="utf-8")

    gefunden = {p for p, _m, _s in nfo.walk_nfo_files(tmp_path)}
    assert len(gefunden) == 1
    assert next(iter(gefunden)).endswith("a.nfo")
