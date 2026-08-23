"""Konfiguration aus Umgebungsvariablen (Docker-freundlich)."""

import os
import secrets
from pathlib import Path


def _bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on", "ja")


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


DATA_DIR = Path(os.environ.get("DATA_DIR", "/config"))
MOVIES_DIR = Path(os.environ.get("MOVIES_DIR", "/movies"))
DB_PATH = DATA_DIR / "trailerde.sqlite3"

# Zugang zur Weboberflaeche
WEB_USERNAME = os.environ.get("WEB_USERNAME", "admin")
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")
WEB_PASSWORD_HASH = os.environ.get("WEB_PASSWORD_HASH", "")
AUTH_DISABLED = _bool("AUTH_DISABLED", False)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "")

# Hinter einem Reverse Proxy mit TLS: Sitzungscookie nur ueber HTTPS senden.
COOKIE_SECURE = _bool("COOKIE_SECURE", False)
SESSION_DAYS = _int("SESSION_DAYS", 30)

# Voreinstellungen; in der Oberflaeche aenderbar und dann in der Datenbank
DEFAULTS = {
    "tmdb_api_key": os.environ.get("TMDB_API_KEY", ""),
    "languages": os.environ.get("LANGUAGES", "de"),
    "link_format": os.environ.get("LINK_FORMAT", "emby"),
    "keep_format": "1" if _bool("KEEP_FORMAT", True) else "0",
    "backup": "1" if _bool("BACKUP", True) else "0",
    "lockdata": "0",
    "scan_interval_hours": str(_int("SCAN_INTERVAL_HOURS", 12)),
    "scan_on_start": "1" if _bool("SCAN_ON_START", True) else "0",
    "recheck_days": str(_int("RECHECK_DAYS", 30)),
    "ui_language": os.environ.get("UI_LANGUAGE", "de"),
    "overwrite_existing": "0",
}

PORT = _int("PORT", 8081)


def _persisted(name, erzeuger):
    """Einen Zufallswert dauerhaft unter DATA_DIR ablegen und wiederverwenden.

    Gibt es die Datei schon, gilt ihr Inhalt. Laesst sich nichts schreiben -
    /config nur lesbar eingebunden -, kommt ein fluechtiger Wert zurueck; das
    meldet der Aufrufer.
    """
    path = DATA_DIR / name
    try:
        if path.exists():
            vorhanden = path.read_text(encoding="utf-8").strip()
            if vorhanden:
                return vorhanden, True
        wert = erzeuger()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(wert, encoding="utf-8")
        path.chmod(0o600)
        return wert, True
    except OSError:
        return erzeuger(), False


def ensure_webhook_token():
    """Webhook-Token besorgen: aus der Umgebung, sonst einmalig erzeugen.

    Ohne Token bliebe der Webhook geschlossen - und wer ihn erst selbst erzeugen
    muss, vergisst es leicht und wundert sich dann ueber einen stummen Webhook.
    Der erzeugte Wert steht in der Oberflaeche unter Einstellungen -> Webhook.

    Gibt (token, dauerhaft) zurueck.
    """
    if WEBHOOK_TOKEN:
        return WEBHOOK_TOKEN, True
    return _persisted("webhook_token", lambda: secrets.token_urlsafe(32))


def ensure_secret_key():
    """Sitzungsschluessel dauerhaft ablegen, damit Logins Neustarts ueberleben."""
    if SECRET_KEY:
        return SECRET_KEY
    key, _dauerhaft = _persisted("secret_key", lambda: secrets.token_hex(32))
    return key
