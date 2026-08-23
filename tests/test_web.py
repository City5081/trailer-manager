"""Weboberflaeche: Anmeldung, CSRF, Webhook, robuste Adressen."""

import re

import config


def token_aus(html):
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    return m.group(1) if m else None


def anmelden(client):
    seite = client.get("/login").get_data(as_text=True)
    antwort = client.post("/login", data={"username": config.WEB_USERNAME,
                                          "password": config.WEB_PASSWORD,
                                          "csrf": token_aus(seite)})
    assert antwort.status_code == 302
    return antwort


def test_health_ist_offen(client):
    assert client.get("/health").get_json()["ok"] is True


def test_geschuetzte_seiten_leiten_zur_anmeldung(client):
    for pfad in ("/", "/settings", "/log"):
        antwort = client.get(pfad)
        assert antwort.status_code == 302
        assert "/login" in antwort.headers["Location"]


def test_anmeldung_mit_umlaut_im_passwort(client):
    """hmac.compare_digest wirft bei Nicht-ASCII sonst einen TypeError."""
    anmelden(client)
    assert client.get("/").status_code == 200


def test_falsches_passwort_bleibt_draussen(client):
    seite = client.get("/login").get_data(as_text=True)
    antwort = client.post("/login", data={"username": config.WEB_USERNAME,
                                          "password": "falsch",
                                          "csrf": token_aus(seite)})
    assert antwort.status_code == 200
    assert client.get("/").status_code == 302


def test_weiterleitung_nur_innerhalb_der_oberflaeche(client):
    seite = client.get("/login").get_data(as_text=True)
    antwort = client.post("/login?next=https://boese.example/",
                          data={"username": config.WEB_USERNAME,
                                "password": config.WEB_PASSWORD,
                                "csrf": token_aus(seite)})
    assert "boese.example" not in antwort.headers["Location"]


def test_post_ohne_csrf_token_wird_abgewiesen(client):
    anmelden(client)
    assert client.post("/run", data={}).status_code == 400


def test_post_mit_csrf_token_geht_durch(client):
    anmelden(client)
    seite = client.get("/").get_data(as_text=True)
    antwort = client.post("/run", data={"csrf": token_aus(seite)})
    assert antwort.status_code == 302


def test_unsinnige_seitenzahl_ergibt_keinen_serverfehler(client):
    anmelden(client)
    for wert in ("abc", "-5", "", "99999999999999999999"):
        assert client.get("/?page=" + wert).status_code == 200


def test_webhook_braucht_das_token(client):
    assert client.post("/webhook", json={"Event": "library.new"}).status_code == 403
    assert client.post("/webhook?token=falsch", json={}).status_code == 403
    antwort = client.post("/webhook?token=" + config.WEBHOOK_TOKEN,
                          json={"Event": "library.new", "Item": {"Name": "Test"}})
    assert antwort.status_code == 200
    assert antwort.get_json()["accepted"] is True


def test_webhook_ignoriert_fremde_ereignisse(client):
    antwort = client.post("/webhook?token=" + config.WEBHOOK_TOKEN,
                          json={"Event": "playback.start"})
    assert antwort.get_json() == {"ignored": "playback.start"}


def test_sicherheitskopfzeilen_sind_gesetzt(client):
    kopf = client.get("/login").headers
    assert kopf["X-Content-Type-Options"] == "nosniff"
    assert kopf["X-Frame-Options"] == "SAMEORIGIN"


def test_unbekannter_film_ergibt_404(client):
    anmelden(client)
    assert client.get("/movie?path=/gibt/es/nicht.nfo").status_code == 404
