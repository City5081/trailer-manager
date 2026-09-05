"""Notifications. The HTTP layer is stubbed - nothing is actually sent."""

import json

import pytest

import notify as notify_mod


class FakeResponse:
    status = 200

    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def recorder(monkeypatch, error=None):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "headers": {k.lower(): v for k, v in request.header_items()},
            "body": request.data.decode("utf-8") if request.data else "",
        })
        if error:
            raise error
        return FakeResponse()

    monkeypatch.setattr(notify_mod, "urlopen", fake_urlopen)
    return calls


def test_gotify_puts_the_token_in_the_query_and_json_in_the_body(monkeypatch):
    calls = recorder(monkeypatch)
    notify_mod.send("gotify", "https://gotify.example", "AppToken123",
                    "Trailer set", "Mayday")

    call = calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://gotify.example/message?token=AppToken123"
    body = json.loads(call["body"])
    assert body == {"title": "Trailer set", "message": "Mayday", "priority": 5}


def test_gotify_raises_its_priority_for_errors(monkeypatch):
    calls = recorder(monkeypatch)
    notify_mod.send("gotify", "https://gotify.example", "t", "Errors", "3 failed",
                    priority=notify_mod.HIGH)
    assert json.loads(calls[0]["body"])["priority"] == 8


def test_gotify_needs_a_token():
    with pytest.raises(notify_mod.NotifyError) as error:
        notify_mod.send("gotify", "https://gotify.example", "", "t", "m")
    assert "token" in str(error.value)


def test_ntfy_sends_plain_text_with_the_title_as_a_header(monkeypatch):
    calls = recorder(monkeypatch)
    notify_mod.send("ntfy", "https://ntfy.sh/my-topic", "", "Trailer set", "Mayday")

    call = calls[0]
    assert call["url"] == "https://ntfy.sh/my-topic"
    assert call["body"] == "Mayday"
    assert call["headers"]["title"] == "Trailer set"
    assert call["headers"]["priority"] == "default"
    assert "authorization" not in call["headers"]


def test_ntfy_adds_a_bearer_token_when_given(monkeypatch):
    calls = recorder(monkeypatch)
    notify_mod.send("ntfy", "https://ntfy.sh/secret", "tk_abc", "t", "m",
                    priority=notify_mod.HIGH)
    assert calls[0]["headers"]["authorization"] == "Bearer tk_abc"
    assert calls[0]["headers"]["priority"] == "high"


def test_discord_folds_the_title_into_the_message(monkeypatch):
    calls = recorder(monkeypatch)
    notify_mod.send("discord", "https://discord.com/api/webhooks/x", "", "Head", "Body")
    assert json.loads(calls[0]["body"]) == {"content": "**Head**\nBody"}


def test_a_plain_webhook_gets_structured_json(monkeypatch):
    calls = recorder(monkeypatch)
    notify_mod.send("webhook", "https://example.com/hook", "secret", "Head", "Body")
    assert json.loads(calls[0]["body"]) == {"title": "Head", "message": "Body",
                                            "priority": "normal"}
    assert calls[0]["headers"]["authorization"] == "Bearer secret"


def test_an_address_without_a_scheme_still_works(monkeypatch):
    calls = recorder(monkeypatch)
    notify_mod.send("gotify", "192.168.1.5:8080", "t", "a", "b")
    assert calls[0]["url"].startswith("http://192.168.1.5:8080/message")


def test_unknown_services_and_empty_addresses_are_refused():
    with pytest.raises(notify_mod.NotifyError):
        notify_mod.send("carrier-pigeon", "https://x", "", "a", "b")
    with pytest.raises(notify_mod.NotifyError):
        notify_mod.send("gotify", "", "t", "a", "b")


def test_a_rejected_token_says_so(monkeypatch):
    from urllib.error import HTTPError
    recorder(monkeypatch, HTTPError("https://x", 403, "Forbidden", {}, None))
    with pytest.raises(notify_mod.NotifyError) as error:
        notify_mod.send("gotify", "https://gotify.example", "wrong", "a", "b")
    assert "token" in str(error.value)


def test_an_unreachable_service_says_so(monkeypatch):
    from urllib.error import URLError
    recorder(monkeypatch, URLError("connection refused"))
    with pytest.raises(notify_mod.NotifyError) as error:
        notify_mod.send("gotify", "https://gotify.example", "t", "a", "b")
    assert "Cannot reach" in str(error.value)


def test_every_service_has_an_example_address():
    for name in notify_mod.SERVICES:
        assert notify_mod.example_url(name).startswith("http")


# ------------------------------------------------------------ in the scanner
def scanner_with(**settings):
    import scanner as scanner_mod

    values = {"notify_on_new": "1", "notify_on_error": "1", "notify_on_run": "0"}
    values.update(settings)
    return scanner_mod.Scanner(lambda key, default=None: values.get(key, default))


@pytest.fixture
def target(database):
    """One enabled Gotify target, removed again afterwards."""
    notifier_id = database.add_notifier("gotify", "https://gotify.example", "tok")
    yield notifier_id
    database.delete_notifier(notifier_id)


def test_nothing_is_sent_without_a_target(monkeypatch, database):
    calls = recorder(monkeypatch)
    for existing in database.list_notifiers():
        database.delete_notifier(existing["id"])
    assert scanner_with().notify("a", "b") == 0
    assert calls == []


def test_every_enabled_target_receives_the_message(monkeypatch, database, target):
    """Several services in parallel is the point - one message, two deliveries."""
    calls = recorder(monkeypatch)
    second = database.add_notifier("ntfy", "https://ntfy.sh/mine", "")
    third = database.add_notifier("discord", "https://discord.example/hook", "")
    database.update_notifier(third, enabled=0)          # switched off by hand
    try:
        assert scanner_with().notify("Head", "Body", when="on_new") == 2
        assert sorted(c["url"] for c in calls) == [
            "https://gotify.example/message?token=tok",
            "https://ntfy.sh/mine",
        ]
    finally:
        database.delete_notifier(second)
        database.delete_notifier(third)


def test_each_kind_can_be_switched_off_on_its_own(monkeypatch, target):
    calls = recorder(monkeypatch)
    scanner = scanner_with(notify_on_new="0", notify_on_run="1")
    assert scanner.notify("a", "b", when="on_new") == 0
    assert scanner.notify("a", "b", when="on_run") == 1
    assert len(calls) == 1


def test_one_broken_target_does_not_stop_the_others(monkeypatch, database, target):
    """A dead Gotify must not cost the message on every other service."""
    import notify as module

    second = database.add_notifier("ntfy", "https://ntfy.sh/mine", "")
    reached = []

    def selective(service, url, token, title, message, priority=module.NORMAL):
        if service == "gotify":
            raise module.NotifyError("host is down")
        reached.append(service)

    monkeypatch.setattr(module, "send", selective)
    try:
        assert scanner_with().notify("a", "b", when="on_new") == 1
        assert reached == ["ntfy"]
        messages = [r["message"] for r in database.recent_log(10)
                    if r["source"] == "notify"]
        assert any("gotify" in m for m in messages)
    finally:
        database.delete_notifier(second)


def test_a_broken_service_is_only_logged(monkeypatch, database, target):
    """The trailer is already written - a phone service must not undo that."""
    from urllib.error import URLError
    recorder(monkeypatch, URLError("host is down"))

    assert scanner_with().notify("Trailer set", "Mayday", when="on_new") == 0
    messages = [r["message"] for r in database.recent_log(10) if r["source"] == "notify"]
    assert any("failed" in m for m in messages)


# --------------------------------------------------------- editing a target
def csrf_from(html):
    import re
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    return match.group(1) if match else None


def sign_in(client):
    import config
    page = client.get("/login").get_data(as_text=True)
    client.post("/login", data={"username": config.WEB_USERNAME,
                                "password": config.WEB_PASSWORD,
                                "csrf": csrf_from(page)})


def test_a_target_can_be_edited(client, database, target):
    sign_in(client)
    page = client.get("/notifier/{}".format(target)).get_data(as_text=True)
    assert "gotify" in page

    response = client.post("/notifier/{}".format(target), data={
        "csrf": csrf_from(page), "service": "ntfy",
        "url": "https://ntfy.sh/changed", "token": "new-token", "enabled": "on"})
    assert response.status_code == 302

    changed = database.get_notifier(target)
    assert changed["service"] == "ntfy"
    assert changed["url"] == "https://ntfy.sh/changed"
    assert changed["token"] == "new-token"
    assert changed["enabled"] == 1


def test_editing_refuses_an_empty_address(client, database, target):
    sign_in(client)
    page = client.get("/notifier/{}".format(target)).get_data(as_text=True)
    response = client.post("/notifier/{}".format(target), data={
        "csrf": csrf_from(page), "service": "gotify", "url": "   "})
    assert response.status_code == 200                      # stays on the form
    assert database.get_notifier(target)["url"] == "https://gotify.example"


def test_toggling_stays_on_the_settings_page(client, database, target):
    """It used to land on the start page, losing your place every time."""
    sign_in(client)
    page = client.get("/settings").get_data(as_text=True)
    response = client.post("/notifier/{}/toggle".format(target),
                           data={"csrf": csrf_from(page)},
                           headers={"Referer": "https://schnuckshome.net/settings"})
    assert response.headers["Location"].endswith("/settings")
    assert database.get_notifier(target)["enabled"] == 0


def test_an_unknown_target_gives_404(client):
    sign_in(client)
    assert client.get("/notifier/999999").status_code == 404


def test_a_rejected_gotify_token_says_which_kind_is_needed(monkeypatch):
    """403 on its own leaves you guessing; Gotify has two kinds of token and
    only the application one can send."""
    from urllib.error import HTTPError
    recorder(monkeypatch, HTTPError("https://x", 403, "Forbidden", {}, None))

    with pytest.raises(notify_mod.NotifyError) as error:
        notify_mod.send("gotify", "https://gotify.example", "CkJ3xyz", "a", "b")
    assert "client token" in str(error.value)
    assert "Apps tab" in str(error.value)

    with pytest.raises(notify_mod.NotifyError) as error:
        notify_mod.send("gotify", "https://gotify.example", "AkJ3xyz", "a", "b")
    assert "Apps tab" in str(error.value)


def test_a_rejected_ntfy_topic_points_at_the_token(monkeypatch):
    from urllib.error import HTTPError
    recorder(monkeypatch, HTTPError("https://x", 401, "Unauthorized", {}, None))
    with pytest.raises(notify_mod.NotifyError) as error:
        notify_mod.send("ntfy", "https://ntfy.sh/private", "", "a", "b")
    assert "access token" in str(error.value)
