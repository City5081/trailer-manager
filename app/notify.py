"""Sending notifications to Gotify, ntfy, Discord or any plain webhook.

Every one of these services is the same thing underneath: POST something to a
URL. So a service is one small function that turns a message into a request,
and adding another one means writing that function and listing it in SERVICES -
nothing else in the application has to change.

Notifications are deliberately sparse. A first run over a whole library writes
hundreds of trailers, and hundreds of phone alerts would be worse than none, so
bulk work is reported as one summary and only genuinely new items are announced
individually.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TIMEOUT = 15

NORMAL, HIGH = "normal", "high"


class NotifyError(RuntimeError):
    pass


# --------------------------------------------------------------- the services
def _gotify(url, token, title, message, priority):
    """Gotify: token as a query parameter, JSON body."""
    if not token:
        raise NotifyError("Gotify needs an application token.")
    return ("{}/message?{}".format(url.rstrip("/"), urlencode({"token": token})),
            {"Content-Type": "application/json"},
            json.dumps({"title": title, "message": message,
                        "priority": 8 if priority == HIGH else 5}).encode("utf-8"))


def _ntfy(url, token, title, message, priority):
    """ntfy: the topic is part of the URL, the body is plain text."""
    headers = {"Content-Type": "text/plain; charset=utf-8",
               "Title": title,
               "Priority": "high" if priority == HIGH else "default"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return url, headers, message.encode("utf-8")


def _discord(url, token, title, message, priority):
    """Discord webhook: one JSON field, so title and text are joined."""
    return (url, {"Content-Type": "application/json"},
            json.dumps({"content": "**{}**\n{}".format(title, message)}).encode("utf-8"))


def _webhook(url, token, title, message, priority):
    """Anything else: plain JSON, with a bearer token if one is given."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return (url, headers,
            json.dumps({"title": title, "message": message,
                        "priority": priority}).encode("utf-8"))


SERVICES = {
    "gotify": _gotify,
    "ntfy": _ntfy,
    "discord": _discord,
    "webhook": _webhook,
}


# ----------------------------------------------------------------- the sending
def send(service, url, token, title, message, priority=NORMAL):
    """Deliver one notification. Raises NotifyError, never anything else."""
    build = SERVICES.get(service)
    if build is None:
        raise NotifyError("Unknown notification service: {}".format(service))
    url = (url or "").strip()
    if not url:
        raise NotifyError("No address configured.")
    if "://" not in url:
        url = "http://" + url

    target, headers, body = build(url, (token or "").strip(), title, message, priority)
    request = Request(target, data=body, method="POST")
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return response.status
    except HTTPError as e:
        if e.code in (401, 403):
            raise NotifyError("The service rejects the token (HTTP {}).".format(e.code)) from e
        raise NotifyError("The service answered with HTTP {} - {}"
                          .format(e.code, e.reason)) from e
    except URLError as e:
        raise NotifyError("Cannot reach {} ({})".format(url, e.reason)) from e


def example_url(service):
    """What the address field should look like, per service."""
    return {"gotify": "https://gotify.example.com",
            "ntfy": "https://ntfy.sh/my-topic",
            "discord": "https://discord.com/api/webhooks/...",
            "webhook": "https://example.com/hook"}.get(service, "")
