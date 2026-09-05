"""Talking to Emby. The HTTP layer is stubbed - no server is contacted."""

import json
from urllib.error import HTTPError

import pytest

import emby as emby_mod


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8") if payload is not None else b""

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def recorder(monkeypatch, payloads):
    """Capture every request and answer from a list of payloads."""
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append({
            "method": request.get_method(),
            "url": request.full_url,
            "headers": {k.lower(): v for k, v in request.header_items()},
        })
        payload = payloads[min(len(calls) - 1, len(payloads) - 1)]
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)

    monkeypatch.setattr(emby_mod, "urlopen", fake_urlopen)
    return calls


LIBRARY = {"Items": [
    {"Id": "abc123", "Name": "Test Movie", "ProviderIds": {"Tmdb": "550", "Imdb": "tt0137523"}},
    {"Id": "def456", "Name": "Test Show", "ProviderIds": {"Tmdb": "1396"}},
    {"Id": "no-ids", "Name": "Homemade", "ProviderIds": {}},
]}


def test_the_address_is_tidied_up():
    assert emby_mod.normalise("192.168.1.10:8096") == "http://192.168.1.10:8096"
    assert emby_mod.normalise("http://emby/ ") == "http://emby"
    assert emby_mod.normalise("https://emby.example/") == "https://emby.example"
    assert emby_mod.normalise(None) == ""


def test_nothing_happens_without_an_address_or_key():
    assert emby_mod.Emby("", "key").configured() is False
    assert emby_mod.Emby("http://emby", "").configured() is False
    with pytest.raises(emby_mod.EmbyError):
        emby_mod.Emby("", "").info()


def test_both_authentication_headers_are_sent(monkeypatch):
    calls = recorder(monkeypatch, [{"ServerName": "Keller", "Version": "4.8"}])
    info = emby_mod.Emby("http://emby:8096", "secret").info()

    assert info == {"name": "Keller", "version": "4.8"}
    headers = calls[0]["headers"]
    assert headers["X-emby-token".lower()] == "secret"
    assert headers["authorization"] == 'MediaBrowser Token="secret"'
    assert calls[0]["url"] == "http://emby:8096/System/Info"


def test_items_are_indexed_by_provider_id(monkeypatch):
    recorder(monkeypatch, [LIBRARY])
    index = emby_mod.Emby("http://emby", "k")._build_index()
    assert index[("tmdb", "550")] == "abc123"
    assert index[("imdb", "tt0137523")] == "abc123"
    assert index[("tmdb", "1396")] == "def456"
    assert ("tmdb", "") not in index


def test_refresh_targets_the_right_item(monkeypatch):
    calls = recorder(monkeypatch, [LIBRARY, None])
    assert emby_mod.Emby("http://emby", "k").refresh("550") is True

    refresh = calls[1]
    assert refresh["method"] == "POST"
    assert refresh["url"].startswith("http://emby/Items/abc123/Refresh?")
    assert "MetadataRefreshMode=FullRefresh" in refresh["url"]
    # Nothing may be replaced - a refresh must not undo what the user set.
    assert "ReplaceAllMetadata=false" in refresh["url"]
    assert "ReplaceAllImages=false" in refresh["url"]
    assert "ImageRefreshMode=None" in refresh["url"]


def test_an_unknown_movie_is_reported_not_refreshed(monkeypatch):
    calls = recorder(monkeypatch, [LIBRARY])
    assert emby_mod.Emby("http://emby", "k").refresh("999999") is False
    # One index and no POST - a freshly built index is not fetched twice.
    assert [c["method"] for c in calls] == ["GET"]


def test_a_movie_added_later_is_found_on_a_rebuild(monkeypatch):
    """A film Emby learned about after the index was built still gets refreshed."""
    later = {"Items": [{"Id": "new1", "Name": "Fresh", "ProviderIds": {"Tmdb": "777"}}]}
    calls = recorder(monkeypatch, [LIBRARY, None, later, None])
    server = emby_mod.Emby("http://emby", "k")

    assert server.refresh("550") is True          # builds the index
    assert server.refresh("777") is True          # misses, rebuilds, finds it
    assert [c["method"] for c in calls] == ["GET", "POST", "GET", "POST"]


def test_a_cached_index_is_reused(monkeypatch):
    calls = recorder(monkeypatch, [LIBRARY, None, None])
    server = emby_mod.Emby("http://emby", "k")
    server.refresh("550")
    server.refresh("1396")
    # One index, two refreshes - not one index per movie.
    assert [c["method"] for c in calls] == ["GET", "POST", "POST"]


def test_a_rejected_key_says_so(monkeypatch):
    recorder(monkeypatch, [HTTPError("http://emby", 401, "Unauthorized", {}, None)])
    with pytest.raises(emby_mod.EmbyError) as error:
        emby_mod.Emby("http://emby", "wrong").info()
    assert "API key" in str(error.value)


def test_an_unreachable_server_says_so(monkeypatch):
    from urllib.error import URLError
    recorder(monkeypatch, [URLError("connection refused")])
    with pytest.raises(emby_mod.EmbyError) as error:
        emby_mod.Emby("http://nowhere", "k").info()
    assert "Cannot reach" in str(error.value)


# --------------------------------------------------------- inside the scanner
def scanner_with(**settings):
    import scanner as scanner_mod

    values = {"emby_url": "http://emby", "emby_api_key": "k", "emby_refresh": "1"}
    values.update(settings)
    return scanner_mod.Scanner(lambda key, default=None: values.get(key, default))


def test_the_notification_can_be_switched_off(monkeypatch):
    calls = recorder(monkeypatch, [LIBRARY, None])
    scanner = scanner_with(emby_refresh="0")
    assert scanner.notify_media_server({"title": "X"}, "550") is False
    assert calls == []


def test_nothing_is_sent_without_a_configured_server(monkeypatch):
    calls = recorder(monkeypatch, [LIBRARY, None])
    assert scanner_with(emby_url="").notify_media_server({"title": "X"}, "550") is False
    assert calls == []


def test_a_failing_server_never_breaks_the_write(monkeypatch, database):
    """The trailer is already on disk - Emby being down must not undo that."""
    from urllib.error import URLError
    recorder(monkeypatch, [URLError("host is down")])

    scanner = scanner_with()
    assert scanner.notify_media_server({"title": "Broken Server"}, "550") is False
    messages = [r["message"] for r in database.recent_log(10) if r["source"] == "emby"]
    assert any("Broken Server" in m for m in messages)


def test_the_index_is_kept_across_movies(monkeypatch):
    """One index per run, not one per trailer - otherwise a run of 1600 movies
    would download the whole library 1600 times."""
    calls = recorder(monkeypatch, [LIBRARY, None, None])
    scanner = scanner_with()
    assert scanner.notify_media_server({"title": "A"}, "550") is True
    assert scanner.notify_media_server({"title": "B"}, "1396") is True
    assert [c["method"] for c in calls] == ["GET", "POST", "POST"]


def test_changing_the_address_replaces_the_client():
    scanner = scanner_with()
    first = scanner.media_server()
    assert scanner.media_server() is first
    scanner.get = lambda key, default=None: {"emby_url": "http://other",
                                             "emby_api_key": "k"}.get(key, default)
    assert scanner.media_server() is not first


# ------------------------------------------------------- asking for new items
def library_with(*items):
    return {"Items": list(items)}


def movie(name, tmdb, created, path):
    return {"Id": "id-" + tmdb, "Name": name, "Type": "Movie",
            "ProviderIds": {"Tmdb": tmdb}, "DateCreated": created, "Path": path}


def test_recent_items_asks_for_the_newest_first(monkeypatch):
    calls = recorder(monkeypatch, [library_with(movie("A", "1", "2026-01-01", "/x/A/a.mkv"))])
    items = emby_mod.Emby("http://emby", "k").recent_items(limit=25)

    assert [i["Name"] for i in items] == ["A"]
    url = calls[0]["url"]
    assert "SortBy=DateCreated" in url and "SortOrder=Descending" in url
    assert "Limit=25" in url
    assert "Fields=ProviderIds%2CPath%2CDateCreated" in url


def test_the_first_poll_only_remembers_where_it_starts(monkeypatch, database):
    """Otherwise connecting a server would look up the fifty newest films at once."""
    database.set_setting("emby_last_seen", "")
    recorder(monkeypatch, [library_with(
        movie("Old", "1", "2026-01-01T10:00:00", "/x/Old/o.mkv"),
        movie("New", "2", "2026-02-01T10:00:00", "/x/New/n.mkv"))])

    result = scanner_with().poll_new_items()
    assert result == {"bootstrapped": 2}
    assert database.get_setting("emby_last_seen") == "2026-02-01T10:00:00"


def test_only_items_added_since_last_time_are_handled(monkeypatch, database, tmp_path):
    import scanner as scanner_mod

    database.set_setting("emby_last_seen", "2026-01-15T00:00:00")
    recorder(monkeypatch, [library_with(
        movie("Older", "1", "2026-01-01T10:00:00", "/emby/Older (2020)/o.mkv"),
        movie("Newer", "2", "2026-02-01T10:00:00", "/emby/Newer (2021)/n.mkv"))])

    handled = []
    monkeypatch.setattr(scanner_mod.Scanner, "_handle_new_item",
                        lambda self, item: handled.append(item["Name"]) or True)

    result = scanner_with().poll_new_items()
    assert result == {"new": 1, "handled": 1}
    assert handled == ["Newer"]
    assert database.get_setting("emby_last_seen") == "2026-02-01T10:00:00"


def test_a_server_path_is_matched_by_folder_name(tmp_path, database):
    """Emby says /mnt/user/Movies/Film (2024); we see /movies/Film (2024)."""
    (tmp_path / "Film (2024)").mkdir()
    lib_id = database.add_library("Local", str(tmp_path), "movie")
    try:
        scanner = scanner_with()
        folder, lib = scanner._local_folder_for(
            {"Type": "Movie", "Path": "/mnt/user/Movies/Film (2024)/Film.mkv"})
        assert folder == tmp_path / "Film (2024)"
        assert lib["id"] == lib_id

        # A film that is not in any configured library stays unmatched.
        missing, _ = scanner._local_folder_for(
            {"Type": "Movie", "Path": "/mnt/user/Other/Nope (1999)/n.mkv"})
        assert missing is None
    finally:
        database.delete_library(lib_id)


def test_a_series_matches_its_own_folder(tmp_path, database):
    (tmp_path / "Blue Bloods").mkdir()
    lib_id = database.add_library("Shows", str(tmp_path), "tv")
    try:
        folder, _ = scanner_with()._local_folder_for(
            {"Type": "Series", "Path": "/mnt/user/Shows/Blue Bloods"})
        assert folder == tmp_path / "Blue Bloods"
    finally:
        database.delete_library(lib_id)


def test_a_movie_library_is_not_offered_for_a_series(tmp_path, database):
    (tmp_path / "Blue Bloods").mkdir()
    lib_id = database.add_library("Films only", str(tmp_path), "movie")
    try:
        folder, _ = scanner_with()._local_folder_for(
            {"Type": "Series", "Path": "/mnt/user/Shows/Blue Bloods"})
        assert folder is None
    finally:
        database.delete_library(lib_id)


def test_a_failing_poll_is_logged_and_not_raised(monkeypatch, database):
    from urllib.error import URLError
    recorder(monkeypatch, [URLError("host is down")])
    result = scanner_with().poll_new_items()
    assert "error" in result
    messages = [r["message"] for r in database.recent_log(10) if r["source"] == "emby"]
    assert any("Asking for new items failed" in m for m in messages)
