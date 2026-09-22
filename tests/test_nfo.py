"""Reading and writing NFOs, and the link formats."""

import xml.etree.ElementTree as ET

import pytest

import nfo


def test_video_id_from_every_spelling():
    vid = "dQw4w9WgXcQ"
    assert nfo.video_id_from("plugin://plugin.video.youtube/play/?video_id=" + vid) == vid
    kodi = "plugin://plugin.video.youtube/?action=play_video&videoid=" + vid
    assert nfo.video_id_from(kodi) == vid
    assert nfo.video_id_from("https://www.youtube.com/watch?v=" + vid) == vid
    assert nfo.video_id_from("https://youtu.be/" + vid) == vid
    assert nfo.video_id_from("https://www.youtube.com/embed/" + vid) == vid
    assert nfo.video_id_from(vid) == vid


def test_video_id_rejects_nonsense():
    assert nfo.video_id_from("") is None
    assert nfo.video_id_from(None) is None
    assert nfo.video_id_from("not a link") is None
    assert nfo.video_id_from("https://vimeo.com/12345") is None


def test_format_and_detection_agree():
    vid = "dQw4w9WgXcQ"
    for name in ("emby", "kodi", "url"):
        link = nfo.format_link(vid, name)
        assert nfo.detect_format(link) == name
        assert nfo.video_id_from(link) == vid


def test_parse_nfo_reads_ids(movie_nfo):
    data = nfo.parse_nfo(movie_nfo)
    assert data["title"] == "Test Movie"
    assert data["year"] == "2021"
    assert data["tmdb"] == "550"
    assert data["imdb"] == "tt0137523"
    assert data["trailer"] == ""


def test_parse_nfo_ignores_foreign_files(tmp_path):
    episode = tmp_path / "S01E01.nfo"
    episode.write_text("<episodedetails><title>Pilot</title></episodedetails>",
                       encoding="utf-8")
    assert nfo.parse_nfo(episode) is None
    broken = tmp_path / "broken.nfo"
    broken.write_text("<movie><title>", encoding="utf-8")
    assert nfo.parse_nfo(broken) is None


def test_parse_nfo_reads_a_series(tmp_path):
    show = tmp_path / "tvshow.nfo"
    show.write_text('<tvshow><title>Test Show</title>'
                    '<premiered>2015-04-13</premiered>'
                    '<uniqueid type="tmdb">1396</uniqueid></tvshow>',
                    encoding="utf-8")
    data = nfo.parse_nfo(show)
    assert data["kind"] == "tv"
    assert data["title"] == "Test Show"
    assert data["year"] == "2015"          # taken from <premiered>
    assert data["tmdb"] == "1396"


def test_a_library_kind_rejects_the_other_shape(tmp_path, movie_nfo):
    """A stray movie.nfo in a series folder must not land in the wrong library."""
    show = tmp_path / "tvshow.nfo"
    show.write_text("<tvshow><title>Show</title></tvshow>", encoding="utf-8")
    assert nfo.parse_nfo(show, kind="tv") is not None
    assert nfo.parse_nfo(show, kind="movie") is None
    assert nfo.parse_nfo(movie_nfo, kind="movie") is not None
    assert nfo.parse_nfo(movie_nfo, kind="tv") is None


def test_series_scan_only_opens_tvshow_files(tmp_path):
    show = tmp_path / "Test Show" / "Season 01"
    show.mkdir(parents=True)
    (tmp_path / "Test Show" / "tvshow.nfo").write_text("<tvshow/>", encoding="utf-8")
    for n in range(5):
        (show / "S01E0{}.nfo".format(n)).write_text("<episodedetails/>", encoding="utf-8")

    found = [p for p, _m, _s in nfo.walk_nfo_files(tmp_path, only_names={"tvshow.nfo"})]
    assert len(found) == 1 and found[0].endswith("tvshow.nfo")
    assert len(nfo.walk_nfo_files(tmp_path)) == 6


def test_write_change_and_remove_trailer(movie_nfo):
    link = nfo.format_link("dQw4w9WgXcQ", "emby")
    assert nfo.write_trailer(movie_nfo, link, backup=False) is True
    assert nfo.parse_nfo(movie_nfo)["trailer"] == link
    # Calling again with the same value must not write a second time.
    assert nfo.write_trailer(movie_nfo, link, backup=False) is False

    other = nfo.format_link("aaaaaaaaaaa", "emby")
    assert nfo.write_trailer(movie_nfo, other, backup=False) is True
    assert nfo.parse_nfo(movie_nfo)["trailer"] == other

    assert nfo.write_trailer(movie_nfo, "", backup=False) is True
    assert nfo.parse_nfo(movie_nfo)["trailer"] == ""


def test_other_fields_survive(movie_nfo):
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=False)
    root = ET.parse(movie_nfo).getroot()
    assert root.findtext("title") == "Test Movie"
    assert len(root.findall("uniqueid")) == 2


def test_backup_is_written_once(movie_nfo):
    bak = movie_nfo.with_suffix(movie_nfo.suffix + ".bak")
    original = movie_nfo.read_bytes()
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=True)
    assert bak.read_bytes() == original
    nfo.write_trailer(movie_nfo, nfo.format_link("aaaaaaaaaaa"), backup=True)
    assert bak.read_bytes() == original          # still the original state


def test_lockdata_is_added(movie_nfo):
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"),
                      lockdata=True, backup=False)
    root = ET.parse(movie_nfo).getroot()
    assert root.findtext("lockdata") == "true"


def test_writing_leaves_no_temporary_files(movie_nfo):
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=False)
    leftovers = [p.name for p in movie_nfo.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_a_failed_write_leaves_the_nfo_intact(movie_nfo, monkeypatch):
    """If writing is cut short, the old file must not be damaged."""
    before = movie_nfo.read_bytes()

    def broken(*args, **kwargs):
        raise OSError("no space left")

    monkeypatch.setattr(ET.ElementTree, "write", broken)
    with pytest.raises(nfo.WriteError):
        nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=False)
    assert movie_nfo.read_bytes() == before


def test_walk_finds_nfos(tmp_path):
    (tmp_path / "Movie A").mkdir()
    (tmp_path / "Movie A" / "a.nfo").write_text("<movie/>", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "b.nfo").write_text("<movie/>", encoding="utf-8")
    (tmp_path / "Movie A" / "movie.mkv").write_text("x", encoding="utf-8")

    found = {p for p, _m, _s in nfo.walk_nfo_files(tmp_path)}
    assert len(found) == 1
    assert next(iter(found)).endswith("a.nfo")


def test_titles_starting_with_dots_are_not_mistaken_for_hidden_folders(tmp_path):
    """"... denn zum Kuessen sind sie da" is a real film, not a dotfile."""
    for name in ("... denn zum Kuessen sind sie da (1997)", "...And Justice for All (1979)"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "movie.nfo").write_text("<movie/>", encoding="utf-8")
    hidden = tmp_path / ".AppleDouble"
    hidden.mkdir()
    (hidden / "movie.nfo").write_text("<movie/>", encoding="utf-8")

    found = [p for p, _m, _s in nfo.walk_nfo_files(tmp_path)]
    assert len(found) == 2
    assert not any(".AppleDouble" in p for p in found)


def test_padding_after_the_closing_tag_is_tolerated(movie_nfo):
    """Seen over SMB while a file was being rewritten elsewhere: intact XML
    followed by 450 NUL bytes. A strict parser rejects that and the entry
    vanishes from the list with no explanation."""
    link = nfo.format_link("dQw4w9WgXcQ")
    nfo.write_trailer(movie_nfo, link, backup=False)

    with open(movie_nfo, "ab") as handle:
        handle.write(b"\x00" * 450)

    data = nfo.parse_nfo(movie_nfo)
    assert data is not None
    assert data["trailer"] == link


def test_writing_clears_the_padding(movie_nfo):
    """Once noticed, the file is left valid rather than merely readable."""
    nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"), backup=False)
    with open(movie_nfo, "ab") as handle:
        handle.write(b"\x00" * 100)

    # Same value as before: without the padding this would be a no-op.
    assert nfo.write_trailer(movie_nfo, nfo.format_link("dQw4w9WgXcQ"),
                             backup=False) is True
    assert b"\x00" not in movie_nfo.read_bytes()

    import xml.etree.ElementTree as ET
    ET.parse(movie_nfo)                      # strict parsers accept it again


def test_a_genuinely_broken_file_is_still_refused(tmp_path):
    broken = tmp_path / "broken.nfo"
    broken.write_text("<movie><title>no end tag", encoding="utf-8")
    assert nfo.parse_nfo(broken) is None
