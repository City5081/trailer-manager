"""Configuration from environment variables (Docker friendly).

Only the values that must be known before the database exists are read here:
credentials, paths and secrets. Everything else has a default that the setup
wizard and the settings page write to the database, so a fresh install needs
no environment variables at all beyond the volumes.
"""

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
# The file name predates the rename to Trailer Manager and stays as it is:
# changing it would leave an existing installation with an empty database.
DB_PATH = DATA_DIR / "trailerde.sqlite3"

# Web interface credentials. Leaving these unset is the normal case: the setup
# wizard asks for a user name and password and stores a hash in the database.
WEB_USERNAME = os.environ.get("WEB_USERNAME", "admin")
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")
WEB_PASSWORD_HASH = os.environ.get("WEB_PASSWORD_HASH", "")
AUTH_DISABLED = _bool("AUTH_DISABLED", False)


def credentials_from_env():
    """True when the environment already carries a password.

    In that case the wizard skips its account step and leaves the environment
    in charge, so a deployment that manages secrets elsewhere keeps working.
    """
    return bool(WEB_PASSWORD or WEB_PASSWORD_HASH)


SECRET_KEY = os.environ.get("SECRET_KEY", "")

# Behind a reverse proxy with TLS: only send the session cookie over HTTPS.
COOKIE_SECURE = _bool("COOKIE_SECURE", False)
SESSION_DAYS = _int("SESSION_DAYS", 30)

# Starting values. The wizard and the settings page override each of these and
# store the result in the database, which then takes precedence.
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
    "nfo_wait": str(_int("NFO_WAIT", 60)),
    "emby_poll_minutes": str(_int("EMBY_POLL_MINUTES", 5)),
    "emby_url": os.environ.get("EMBY_URL", ""),
    "emby_api_key": os.environ.get("EMBY_API_KEY", ""),
    "notify_service": os.environ.get("NOTIFY_SERVICE", ""),
    "notify_url": os.environ.get("NOTIFY_URL", ""),
    "notify_token": os.environ.get("NOTIFY_TOKEN", ""),
    "emby_refresh": "1" if _bool("EMBY_REFRESH", True) else "0",
    "notify_on_new": "1" if _bool("NOTIFY_ON_NEW", True) else "0",
    "notify_on_run": "0" if not _bool("NOTIFY_ON_RUN", False) else "1",
    "notify_on_error": "1" if _bool("NOTIFY_ON_ERROR", True) else "0",
    "notify_on_warning": "1" if _bool("NOTIFY_ON_WARNING", False) else "0",
    "ui_language": os.environ.get("UI_LANGUAGE", "de"),
    "overwrite_existing": "0",
}

PORT = _int("PORT", 8081)


def _persisted(name, make_value):
    """Keep a generated secret in DATA_DIR and reuse it on the next start.

    If the file already exists its content wins. When nothing can be written -
    /config mounted read only - a throwaway value is returned; the caller is
    told so it can warn.

    Returns (value, persisted).
    """
    path = DATA_DIR / name
    try:
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing, True
        value = make_value()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return value, True
    except OSError:
        return make_value(), False


def ensure_secret_key():
    """Persist the session key so logins survive a restart."""
    if SECRET_KEY:
        return SECRET_KEY
    key, _persisted_ok = _persisted("secret_key", lambda: secrets.token_hex(32))
    return key
