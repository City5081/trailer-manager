"""Several libraries side by side: movies, anime films, TV shows."""

import db
import nfo
import scanner as scanner_mod
import tmdb


def settings(**overrides):
    values = {"languages": "de", "link_format": "emby", "keep_format": "1",
              "backup": "0", "lockdata": "0", "tmdb_api_key": "testkey",
              "recheck_days": "30", "overwrite_existing": "0"}
    values.update(overrides)
    return lambda key, default=None: values.get(key, default)


def write_show(root, name, tmdb_id):
    folder = root / name
    (folder / "Season 01").mkdir(parents=True)
    (folder / "tvshow.nfo").write_text(
        '<tvshow><title>{}</title><premiered>2015-04-13</premiered>'
        '<uniqueid type="tmdb">{}</uniqueid></tvshow>'.format(name, tmdb_id),
        encoding="utf-8")
    (folder / "Season 01" / "S01E01.nfo").write_text(
        "<episodedetails><title>Pilot</title></episodedetails>", encoding="utf-8")
    return folder / "tvshow.nfo"


def test_a_library_override_beats_the_global_setting(library):
    s = scanner_mod.Scanner(settings(languages="de", link_format="emby"))
    assert s._langs(library) == ["de"]
    assert s.setting_for(library, "link_format") == "emby"

    db.update_library(library["id"], languages="ja,en", link_format="url")
    changed = db.get_library(library["id"])
    assert s._langs(changed) == ["ja", "en"]
    assert s.setting_for(changed, "link_format") == "url"

    # An empty override keeps falling back to the global value.
    db.update_library(library["id"], languages="")
    assert s._langs(db.get_library(library["id"])) == ["de"]


def test_libraries_do_not_delete_each_others_entries(tmp_path, movie_nfo, library):
    other_root = tmp_path / "anime"
    other_root.mkdir()
    other_folder = other_root / "Anime Film (2019)"
    other_folder.mkdir()
    (other_folder / "movie.nfo").write_text(
        '<movie><title>Anime Film</title><uniqueid type="tmdb">99</uniqueid></movie>',
        encoding="utf-8")
    other_id = db.add_library("Anime", str(other_root), "movie")
    try:
        s = scanner_mod.Scanner(settings())
        s.scan_library(library, workers=2)
        s.scan_library(db.get_library(other_id), workers=2)

        assert db.get_movie(str(movie_nfo)) is not None
        assert db.get_movie(str(other_folder / "movie.nfo")) is not None

        # Scanning one library again must leave the other one alone.
        s.scan_library(library, workers=2)
        assert db.get_movie(str(other_folder / "movie.nfo")) is not None
    finally:
        db.delete_library(other_id)


def test_a_tv_library_reads_only_tvshow_files(tmp_path, tv_library):
    show = write_show(tmp_path, "Test Show", "1396")
    s = scanner_mod.Scanner(settings())
    result = s.scan_library(tv_library, workers=2)

    assert result["files"] == 1                 # the episode NFO is never opened
    row = db.get_movie(str(show))
    assert row is not None and row["title"] == "Test Show"
    assert row["year"] == "2015"


def test_a_series_trailer_uses_the_tv_endpoint(tmp_path, tv_library, monkeypatch):
    show = write_show(tmp_path, "Test Show", "1396")
    s = scanner_mod.Scanner(settings())
    s.scan_library(tv_library, workers=2)

    seen = {}

    def fake_fetch(tmdb_id, api_key, langs, kind="movie"):
        seen["kind"] = kind
        seen["id"] = tmdb_id
        return [{"key": "dQw4w9WgXcQ", "lang": "de", "type": "Trailer",
                 "official": True, "site": "YouTube", "size": 1080}]

    monkeypatch.setattr(tmdb, "fetch_videos", fake_fetch)
    status, _ = s.process_movie(db.get_movie(str(show)))

    assert status == "ok"
    assert seen == {"kind": "tv", "id": "1396"}
    assert nfo.parse_nfo(show)["trailer"] == nfo.format_link("dQw4w9WgXcQ", "emby")


def test_deleting_a_library_drops_its_entries_only(tmp_path, movie_nfo, library):
    other_root = tmp_path / "second"
    other_root.mkdir()
    (other_root / "Film (2020)").mkdir()
    second_nfo = other_root / "Film (2020)" / "movie.nfo"
    second_nfo.write_text('<movie><title>Second</title></movie>', encoding="utf-8")
    other_id = db.add_library("Second", str(other_root), "movie")

    s = scanner_mod.Scanner(settings())
    s.scan_library(library, workers=2)
    s.scan_library(db.get_library(other_id), workers=2)

    db.delete_library(other_id)
    assert db.get_movie(str(second_nfo)) is None
    assert db.get_movie(str(movie_nfo)) is not None
    # The file itself stays where it is.
    assert second_nfo.exists()


def test_orphans_are_cleaned_up(tmp_path, library):
    data = {"title": "Orphan", "year": "", "tmdb": "1", "imdb": None,
            "trailer": "", "kind": "movie"}
    orphan = str(tmp_path / "orphan.nfo")
    db.upsert_movie(orphan, str(tmp_path), data, 1.0, 10, library_id=999999)
    assert db.get_movie(orphan) is not None
    db.delete_orphans()
    assert db.get_movie(orphan) is None


def test_the_path_decides_which_library_an_item_belongs_to(tmp_path, library, tv_library):
    s = scanner_mod.Scanner(settings())
    # tv_library and library share tmp_path, so the longer path has to win.
    inner = tmp_path / "shows"
    inner.mkdir()
    inner_id = db.add_library("Inner", str(inner), "tv")
    try:
        found = s._library_for(str(inner / "Some Show" / "Season 01" / "e.mkv"))
        assert found["id"] == inner_id
    finally:
        db.delete_library(inner_id)


def test_a_new_movie_reads_only_its_own_folder(tmp_path, library, monkeypatch):
    """The path pins down the folder - nothing else may be touched."""
    wanted = tmp_path / "New Film (2024)"
    wanted.mkdir()
    (wanted / "movie.nfo").write_text(
        '<movie><title>New Film</title><uniqueid type="tmdb">77</uniqueid></movie>',
        encoding="utf-8")
    other = tmp_path / "Other Film (2001)"
    other.mkdir()
    (other / "movie.nfo").write_text("<movie><title>Other</title></movie>",
                                     encoding="utf-8")

    s = scanner_mod.Scanner(settings())
    walked = []
    real_walk = nfo.walk_nfo_files
    monkeypatch.setattr(nfo, "walk_nfo_files",
                        lambda root, *a, **k: walked.append(str(root)) or real_walk(root, *a, **k))

    rows = s._rows_for_path(str(wanted / "New Film.mkv"), library)
    assert [r["title"] for r in rows] == ["New Film"]
    assert walked == [str(wanted)]                  # not the library root
    assert db.get_movie(str(other / "movie.nfo")) is None


def test_a_series_path_walks_up_to_the_tvshow_nfo(tmp_path, tv_library):
    """Emby may report an episode file; the trailer belongs on the series."""
    show = write_show(tmp_path, "Deep Show", "1396")
    episode = show.parent / "Season 01" / "S01E01.mkv"

    s = scanner_mod.Scanner(settings())
    rows = s._rows_for_path(str(episode), tv_library)
    assert [r["title"] for r in rows] == ["Deep Show"]
    assert rows[0]["path"] == str(show)


def test_the_wait_is_configurable_and_can_be_switched_off():
    s = scanner_mod.Scanner(settings(nfo_wait="60"))
    assert sum(s._wait_steps()) == 60

    s = scanner_mod.Scanner(settings(nfo_wait="7"))
    assert sum(s._wait_steps()) == 7        # never longer than asked for

    s = scanner_mod.Scanner(settings(nfo_wait="0"))
    assert s._wait_steps() == []

    s = scanner_mod.Scanner(settings(nfo_wait="nonsense"))
    assert sum(s._wait_steps()) == 60       # falls back to the default


def test_a_late_nfo_is_picked_up_after_waiting(tmp_path, library, monkeypatch):
    """Emby reports the item before the NFO exists - the retry has to find it."""
    folder = tmp_path / "Late Film (2024)"
    folder.mkdir()
    s = scanner_mod.Scanner(settings(nfo_wait="5"))

    written = {"done": False}

    def fake_sleep(_seconds):
        # Stand in for the media server writing the NFO between two attempts.
        if not written["done"]:
            (folder / "movie.nfo").write_text(
                '<movie><title>Late Film</title><uniqueid type="tmdb">88</uniqueid></movie>',
                encoding="utf-8")
            written["done"] = True

    monkeypatch.setattr(scanner_mod.time, "sleep", fake_sleep)
    rows = s._wait_for_nfo(str(folder / "Late Film.mkv"), library, "88", "Late Film")
    assert [r["title"] for r in rows] == ["Late Film"]
