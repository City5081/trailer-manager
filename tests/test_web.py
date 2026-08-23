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


def test_webhook_requires_the_token(client):
    assert client.post("/webhook", json={"Event": "library.new"}).status_code == 403
    assert client.post("/webhook?token=wrong", json={}).status_code == 403
    response = client.post("/webhook?token=" + config.WEBHOOK_TOKEN,
                           json={"Event": "library.new", "Item": {"Name": "Test"}})
    assert response.status_code == 200
    assert response.get_json()["accepted"] is True


def test_webhook_ignores_unrelated_events(client):
    response = client.post("/webhook?token=" + config.WEBHOOK_TOKEN,
                           json={"Event": "playback.start"})
    assert response.get_json() == {"ignored": "playback.start"}


def test_security_headers_are_set(client):
    headers = client.get("/login").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"


def test_an_unknown_movie_gives_404(client):
    sign_in(client)
    assert client.get("/movie?path=/does/not/exist.nfo").status_code == 404


def test_the_settings_page_shows_the_webhook_instructions(client):
    sign_in(client)
    page = client.get("/settings").get_data(as_text=True)
    assert "application/json" in page
    assert config.WEBHOOK_TOKEN in page
