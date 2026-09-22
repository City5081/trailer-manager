"""Web interface: login, CSRF, webhook, robust addresses."""

import re

import config


def token_from(html):
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    return m.group(1) if m else None


def sign_in(client):
    page = client.get("/login").get_data(as_text=True)
    response = client.post("/login", data={"username": config.WEB_USERNAME,
                                           "password": config.WEB_PASSWORD,
                                           "csrf": token_from(page)})
    assert response.status_code == 302
    return response


def test_health_is_open(client):
    assert client.get("/health").get_json()["ok"] is True


def test_protected_pages_redirect_to_the_login(client):
    for path in ("/", "/settings", "/log"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_login_with_a_non_ascii_password(client):
    """hmac.compare_digest would otherwise raise a TypeError."""
    sign_in(client)
    assert client.get("/").status_code == 200


def test_a_wrong_password_stays_out(client):
    page = client.get("/login").get_data(as_text=True)
    response = client.post("/login", data={"username": config.WEB_USERNAME,
                                           "password": "wrong",
                                           "csrf": token_from(page)})
    assert response.status_code == 200
    assert client.get("/").status_code == 302


def test_redirects_stay_inside_the_interface(client):
    page = client.get("/login").get_data(as_text=True)
    response = client.post("/login?next=https://evil.example/",
                           data={"username": config.WEB_USERNAME,
                                 "password": config.WEB_PASSWORD,
                                 "csrf": token_from(page)})
    assert "evil.example" not in response.headers["Location"]


def test_post_without_a_csrf_token_is_refused(client):
    sign_in(client)
    assert client.post("/run", data={}).status_code == 400


def test_post_with_a_csrf_token_goes_through(client):
    sign_in(client)
    page = client.get("/").get_data(as_text=True)
    response = client.post("/run", data={"csrf": token_from(page)})
    assert response.status_code == 302


def test_a_nonsense_page_number_is_not_a_server_error(client):
    sign_in(client)
    for value in ("abc", "-5", "", "99999999999999999999"):
        assert client.get("/?page=" + value).status_code == 200


def test_security_headers_are_set(client):
    headers = client.get("/login").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"


def test_an_unknown_movie_gives_404(client):
    sign_in(client)
    assert client.get("/movie?path=/does/not/exist.nfo").status_code == 404


def test_buttons_return_to_the_page_they_were_pressed_on(client):
    """Behind a reverse proxy the browser reports the outside address while the
    application sees its own - comparing the two sent every button to the start
    page."""
    sign_in(client)
    page = client.get("/settings").get_data(as_text=True)
    csrf = token_from(page)

    response = client.post("/scan", data={"csrf": csrf},
                           headers={"Referer": "https://schnuckshome.net/settings"})
    assert response.headers["Location"] == "/settings"


def test_the_referrer_can_never_send_anyone_off_site(client):
    """Only the path is kept, so a foreign host cannot become a redirect."""
    sign_in(client)
    page = client.get("/settings").get_data(as_text=True)
    csrf = token_from(page)

    response = client.post("/scan", data={"csrf": csrf},
                           headers={"Referer": "https://evil.example/settings?x=1"})
    assert response.headers["Location"] == "/settings?x=1"
    assert "evil.example" not in response.headers["Location"]


def test_a_missing_referrer_falls_back_to_the_start_page(client):
    sign_in(client)
    page = client.get("/").get_data(as_text=True)
    response = client.post("/scan", data={"csrf": token_from(page)})
    assert response.headers["Location"] == "/"


def test_the_newest_trailers_are_the_default_order(client):
    """What the tool just did is the most interesting thing on the page."""
    sign_in(client)
    page = client.get("/").get_data(as_text=True)
    # The header link offers the opposite direction, which is how you can tell
    # which way the page is currently sorted.
    assert "sort=changed&amp;dir=asc" in page
    assert 'class="sort on"' in page


def test_an_explicit_order_still_wins(client):
    sign_in(client)
    page = client.get("/?sort=title").get_data(as_text=True)
    assert "sort=title&amp;dir=desc" in page       # title defaults to ascending


def test_a_nonsense_sort_key_falls_back(client):
    sign_in(client)
    assert client.get("/?sort=;DROP TABLE movies&dir=sideways").status_code == 200


def test_the_running_version_is_on_every_page(client):
    """Answers 'which version is actually running here' without a terminal."""
    from version import VERSION

    sign_in(client)
    for path in ("/", "/settings", "/log"):
        assert VERSION in client.get(path).get_data(as_text=True)


def test_the_log_can_be_filtered_by_level(client):
    """The log used to be a flat list of everything, which is how an error sits
    unnoticed between a hundred info lines."""
    import db

    sign_in(client)
    db.log("error", "a write failed", "write")
    db.log("info", "library read", "scan")

    page = client.get("/log?level=error").get_data(as_text=True)
    assert "a write failed" in page
    assert "library read" not in page

    everything = client.get("/log").get_data(as_text=True)
    assert "a write failed" in everything and "library read" in everything


def test_a_nonsense_log_level_shows_everything(client):
    sign_in(client)
    assert client.get("/log?level=;DROP TABLE log").status_code == 200


def test_the_movie_list_can_show_only_problems(client, database, tmp_path):
    """'no_trailer' is an answer, not a fault - it does not belong here."""
    data = {"title": "X", "year": "", "tmdb": "1", "imdb": None, "trailer": "",
            "kind": "movie"}
    lib_id = database.add_library("Probe", str(tmp_path), "movie")
    paths = {}
    try:
        for state in ("error", "no_id", "no_trailer", "ok"):
            path = str(tmp_path / (state + ".nfo"))
            paths[state] = path
            database.upsert_movie(path, str(tmp_path), dict(data, title=state.upper()),
                                  1.0, 10, library_id=lib_id)
            database.mark_result(path, state, "message for " + state)

        rows, _ = database.list_movies(state="problem", library_id=lib_id)
        found = {r["state"] for r in rows}
        assert found == {"error", "no_id"}
    finally:
        database.delete_library(lib_id)
