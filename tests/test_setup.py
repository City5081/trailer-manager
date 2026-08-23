"""The setup wizard: the first run asks for the basics."""

import re

import config
import db
import tmdb


def token_from(html):
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    return m.group(1) if m else None


def sign_in(client):
    page = client.get("/login").get_data(as_text=True)
    assert client.post("/login", data={"username": config.WEB_USERNAME,
                                       "password": config.WEB_PASSWORD,
                                       "csrf": token_from(page)}).status_code == 302


def start_over(client, signed_in=True):
    """Put the instance back into its unconfigured state.

    The wizard sits behind the login whenever credentials already exist, which
    is the case in the test environment - so sign in unless a test wants to
    look at exactly that.
    """
    db.set_setting("setup_done", "0")
    client.get("/logout")
    if signed_in:
        sign_in(client)


def test_the_wizard_is_protected_once_credentials_exist(client):
    start_over(client, signed_in=False)
    try:
        response = client.get("/setup")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
    finally:
        db.set_setting("setup_done", "1")


def test_everything_leads_to_the_wizard_until_it_is_done(client):
    start_over(client)
    try:
        for path in ("/", "/settings", "/log"):
            response = client.get(path)
            assert response.status_code == 302
            assert response.headers["Location"].endswith("/setup")
    finally:
        db.set_setting("setup_done", "1")


def test_the_wizard_stores_the_basics(client, monkeypatch):
    start_over(client)
    monkeypatch.setattr(tmdb, "selftest", lambda key: 3)
    try:
        page = client.get("/setup").get_data(as_text=True)
        response = client.post("/setup", data={
            "csrf": token_from(page),
            "tmdb_api_key": "a-real-key",
            "languages": "de,en",
            "link_format": "kodi",
            "scan_interval_hours": "6",
            "recheck_days": "14",
            "ui_language": "en",
            "keep_format": "on",
            "backup": "on",
        })
        assert response.status_code == 302
        assert db.get_setting("setup_done") == "1"
        assert db.get_setting("tmdb_api_key") == "a-real-key"
        assert db.get_setting("languages") == "de,en"
        assert db.get_setting("link_format") == "kodi"
        assert db.get_setting("scan_interval_hours") == "6"
        assert db.get_setting("scan_on_start") == "0"      # checkbox not ticked
    finally:
        db.set_setting("setup_done", "1")


def test_a_bad_api_key_does_not_finish_the_setup(client, monkeypatch):
    start_over(client)

    def refuse(key):
        raise tmdb.TmdbError("TMDB rejects the API key (HTTP 401).")

    monkeypatch.setattr(tmdb, "selftest", refuse)
    try:
        page = client.get("/setup").get_data(as_text=True)
        response = client.post("/setup", data={
            "csrf": token_from(page),
            "tmdb_api_key": "nonsense",
            "languages": "de",
            "link_format": "emby",
            "scan_interval_hours": "12",
            "recheck_days": "30",
            "ui_language": "de",
        })
        assert response.status_code == 200
        assert "HTTP 401" in response.get_data(as_text=True)
        assert db.get_setting("setup_done") == "0"
    finally:
        db.set_setting("setup_done", "1")


def test_the_key_check_can_be_skipped(client, monkeypatch):
    """A TMDB outage must not lock anyone out of their own setup."""
    start_over(client)

    def refuse(key):
        raise tmdb.TmdbError("Cannot reach api.themoviedb.org.")

    monkeypatch.setattr(tmdb, "selftest", refuse)
    try:
        page = client.get("/setup").get_data(as_text=True)
        response = client.post("/setup", data={
            "csrf": token_from(page),
            "tmdb_api_key": "offline-key",
            "languages": "de",
            "link_format": "emby",
            "scan_interval_hours": "12",
            "recheck_days": "30",
            "ui_language": "de",
            "skip_check": "on",
        })
        assert response.status_code == 302
        assert db.get_setting("tmdb_api_key") == "offline-key"
    finally:
        db.set_setting("setup_done", "1")


def test_the_account_step_is_skipped_when_the_environment_has_credentials(client):
    start_over(client)
    try:
        assert config.credentials_from_env() is True
        page = client.get("/setup").get_data(as_text=True)
        assert 'name="password"' not in page
    finally:
        db.set_setting("setup_done", "1")


def test_without_environment_credentials_the_wizard_asks_for_an_account(client, monkeypatch):
    start_over(client, signed_in=False)
    monkeypatch.setattr(config, "WEB_PASSWORD", "")
    monkeypatch.setattr(config, "WEB_PASSWORD_HASH", "")
    monkeypatch.setattr(tmdb, "selftest", lambda key: 3)
    try:
        page = client.get("/setup").get_data(as_text=True)
        assert 'name="password"' in page

        # Too short: the wizard refuses and stays where it is.
        response = client.post("/setup", data={
            "csrf": token_from(page), "web_username": "hannes",
            "password": "short", "password_repeat": "short",
            "tmdb_api_key": "key", "languages": "de", "link_format": "emby",
            "scan_interval_hours": "12", "recheck_days": "30", "ui_language": "de",
        })
        assert response.status_code == 200
        assert db.get_setting("setup_done") == "0"

        response = client.post("/setup", data={
            "csrf": token_from(page), "web_username": "hannes",
            "password": "long-enough-password", "password_repeat": "long-enough-password",
            "tmdb_api_key": "key", "languages": "de", "link_format": "emby",
            "scan_interval_hours": "12", "recheck_days": "30", "ui_language": "de",
        })
        assert response.status_code == 302
        assert db.get_setting("web_username") == "hannes"
        assert db.get_setting("web_password_hash", "").startswith(("scrypt:", "pbkdf2:"))
    finally:
        db.set_setting("setup_done", "1")
        db.set_setting("web_password_hash", "")
        db.set_setting("web_username", "")
