"""Trailer DE - web interface.

Writes German TMDB trailers into the NFO files of an Emby movie library: on a
schedule, at the push of a button, or right away when Emby or Jellyseerr
reports a new movie.
"""

import functools
import hmac
import secrets
import threading
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
import i18n
import nfo
import scanner as scanner_mod
import tmdb

app = Flask(__name__)
app.secret_key = config.ensure_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = config.COOKIE_SECURE
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=config.SESSION_DAYS)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024      # webhook payloads are small

SCANNER = None
MIN_PASSWORD_LENGTH = 8


@app.template_filter("ts")
def format_ts(value):
    """Make a timestamp readable, in the notation of the chosen language."""
    if not value:
        return ""
    try:
        stamp = time.localtime(float(value))
    except (TypeError, ValueError):
        return ""
    pattern = "%d.%m.%Y %H:%M:%S" if current_lang() == "de" else "%Y-%m-%d %H:%M:%S"
    return time.strftime(pattern, stamp)


# --------------------------------------------------------------------- settings
def setting(key, default=None):
    value = db.get_setting(key)
    if value is None or value == "":
        value = config.DEFAULTS.get(key, default)
    return value if value is not None else default


def flag(key, default="0"):
    return str(setting(key, default)) in ("1", "true", "True", "on", "yes")


def primary_language():
    """First configured language - the one the dashboard counts."""
    raw = setting("languages", "de") or "de"
    first = raw.split(",")[0].strip().split("-")[0]
    return (first or "de").lower()


# ------------------------------------------------------------------------ auth
def _equal(left, right):
    """Constant time comparison that also copes with non-ASCII passwords.

    hmac.compare_digest raises a TypeError on strings outside ASCII, so encode
    to UTF-8 first.
    """
    return hmac.compare_digest((left or "").encode("utf-8"),
                               (right or "").encode("utf-8"))


def current_username():
    """The environment wins when it carries credentials, otherwise the wizard."""
    if config.credentials_from_env():
        return config.WEB_USERNAME
    return db.get_setting("web_username") or config.WEB_USERNAME


def password_ok(password):
    if config.WEB_PASSWORD_HASH:
        return check_password_hash(config.WEB_PASSWORD_HASH, password)
    if config.WEB_PASSWORD:
        return _equal(config.WEB_PASSWORD, password)
    stored = db.get_setting("web_password_hash")
    if stored:
        return check_password_hash(stored, password)
    return False


_ATTEMPTS = {}                          # {ip: (count, time of the last attempt)}
_ATTEMPTS_LOCK = threading.Lock()
LOCKOUT_AFTER = 5                       # failed attempts before we start waiting
LOCKOUT_SECONDS = 300                   # after this the counter starts over


def _login_delay(ip):
    """Delay after repeated failures, capped at 30 seconds."""
    with _ATTEMPTS_LOCK:
        count, last = _ATTEMPTS.get(ip, (0, 0.0))
        if time.time() - last > LOCKOUT_SECONDS:
            count = 0
    return 0 if count < LOCKOUT_AFTER else min(30, 2 ** (count - LOCKOUT_AFTER + 1))


def _note_attempt(ip, success):
    with _ATTEMPTS_LOCK:
        if success:
            _ATTEMPTS.pop(ip, None)
            return
        count, last = _ATTEMPTS.get(ip, (0, 0.0))
        if time.time() - last > LOCKOUT_SECONDS:
            count = 0
        _ATTEMPTS[ip] = (count + 1, time.time())
        if len(_ATTEMPTS) > 1000:       # do not keep an unbounded list in memory
            cutoff = time.time() - LOCKOUT_SECONDS
            for key in [k for k, v in _ATTEMPTS.items() if v[1] < cutoff]:
                _ATTEMPTS.pop(key, None)


def login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if config.AUTH_DISABLED or session.get("user"):
            return view(*args, **kwargs)
        return redirect(url_for("login", next=request.path))
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "?"
        time.sleep(1 + _login_delay(ip))    # slows brute force down
        user = request.form.get("username", "")
        pwd = request.form.get("password", "")
        if _equal(user, current_username()) and password_ok(pwd):
            _note_attempt(ip, True)
            session.clear()                 # fresh session id after a login
            session["user"] = user
            session.permanent = True
            db.log("info", "Login: {}".format(user), "auth")
            return redirect(_safe_next(request.args.get("next")))
        _note_attempt(ip, False)
        error = t("login.failed")
        db.log("warn", "Failed login from {}".format(ip), "auth")
    return render_template("login.html", error=error)


def _safe_next(target):
    """Only allow redirects that stay inside this interface."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("index")


def _back():
    """Back to the previous page - but only if it is ours."""
    referrer = request.referrer or ""
    if referrer.startswith(request.host_url):
        return referrer
    return url_for("index")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------------------------------------------------------------------- language
def current_lang():
    return session.get("lang") or setting("ui_language", "de")


def t(key):
    return i18n.translate(current_lang(), key)


@app.route("/lang/<code>")
def switch_language(code):
    if code in i18n.LANGUAGES:
        session["lang"] = code
    return redirect(_back())


# ------------------------------------------------------------------------ CSRF
CSRF_EXEMPT = {"webhook", "health", "static"}


def csrf_token():
    """One token per session; it sits in every form and is checked on POST."""
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


@app.before_request
def check_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    if request.endpoint in CSRF_EXEMPT:
        return None
    expected = session.get("csrf", "")
    supplied = request.form.get("csrf") or request.headers.get("X-CSRF-Token", "")
    # Nothing may pass without a token in the session - otherwise an empty field
    # would match an empty expectation.
    if not expected or not _equal(supplied, expected):
        db.log("warn", "Request without a valid CSRF token ({})".format(request.path), "auth")
        abort(400)
    return None


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.context_processor
def inject_globals():
    return {
        "t": t,
        "csrf_token": csrf_token,
        "lang": current_lang(),
        "languages": i18n.LANGUAGES,
        "link_formats": nfo.LINK_FORMATS,
        "busy": SCANNER.busy if SCANNER else False,
        "progress": SCANNER.state if SCANNER else {},
        "auth_disabled": config.AUTH_DISABLED,
    }


# ----------------------------------------------------------------- setup wizard
SETUP_EXEMPT = {"setup", "static", "health", "webhook", "login", "switch_language"}


def setup_done():
    return db.get_setting("setup_done") == "1"


@app.before_request
def require_setup():
    """Send everything to the wizard until the basics are configured."""
    if setup_done() or request.endpoint in SETUP_EXEMPT or request.endpoint is None:
        return None
    return redirect(url_for("setup"))


def setup_is_protected():
    """Does the wizard itself need a login?

    On a fresh install there is no password yet, so the wizard has to be open -
    the same first run window every self hosted application has. As soon as
    credentials exist anywhere, it is behind the login.
    """
    return bool(config.credentials_from_env() or db.get_setting("web_password_hash"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if setup_is_protected() and not (config.AUTH_DISABLED or session.get("user")):
        return redirect(url_for("login", next=request.path))

    needs_account = not config.credentials_from_env()
    values = {
        "web_username": current_username(),
        "tmdb_api_key": setting("tmdb_api_key", ""),
        "languages": setting("languages", "de"),
        "link_format": setting("link_format", "emby"),
        "keep_format": flag("keep_format", "1"),
        "backup": flag("backup", "1"),
        "scan_interval_hours": setting("scan_interval_hours", "12"),
        "scan_on_start": flag("scan_on_start", "1"),
        "recheck_days": setting("recheck_days", "30"),
        "ui_language": current_lang(),
    }
    errors = []

    if request.method == "POST":
        for key in ("web_username", "tmdb_api_key", "languages", "link_format",
                    "scan_interval_hours", "recheck_days", "ui_language"):
            values[key] = request.form.get(key, "").strip()
        for key in ("keep_format", "backup", "scan_on_start"):
            values[key] = bool(request.form.get(key))

        password = request.form.get("password", "")
        repeat = request.form.get("password_repeat", "")
        skip_check = bool(request.form.get("skip_check"))

        if needs_account:
            if not values["web_username"]:
                errors.append(t("setup.err_user"))
            if len(password) < MIN_PASSWORD_LENGTH:
                errors.append(t("setup.err_short"))
            elif password != repeat:
                errors.append(t("setup.err_repeat"))

        if not values["tmdb_api_key"]:
            errors.append(t("setup.err_key"))
        elif not skip_check:
            # Check the key right away - a wrong key is the one mistake that
            # makes the whole application look broken later on.
            try:
                tmdb.selftest(values["tmdb_api_key"])
            except tmdb.TmdbError as e:
                errors.append(str(e))

        if not errors:
            if needs_account:
                db.set_setting("web_username", values["web_username"])
                db.set_setting("web_password_hash", generate_password_hash(password))
            for key in ("tmdb_api_key", "languages", "link_format",
                        "scan_interval_hours", "recheck_days", "ui_language"):
                db.set_setting(key, values[key])
            for key in ("keep_format", "backup", "scan_on_start"):
                db.set_setting(key, "1" if values[key] else "0")
            db.set_setting("setup_done", "1")
            session["lang"] = values["ui_language"]
            db.log("info", "Setup completed", "setup")

            if needs_account:
                session["user"] = values["web_username"]
                session.permanent = True
            flash(t("setup.finished"), "ok")
            return redirect(url_for("settings_page"))

    return render_template("setup.html", values=values, errors=errors,
                           needs_account=needs_account,
                           min_password=MIN_PASSWORD_LENGTH)


# ----------------------------------------------------------------------- pages
MAX_PAGE = 1_000_000


def _positive_int(value, default):
    """Numbers from the address bar must not end in a server error.

    The upper bound matters too: SQLite refuses arbitrarily large OFFSET values
    and raises an OverflowError.
    """
    try:
        return min(MAX_PAGE, max(1, int(value)))
    except (TypeError, ValueError):
        return default


@app.route("/")
@login_required
def index():
    search = request.args.get("q", "").strip()
    state = request.args.get("state", "").strip()
    only_missing = request.args.get("missing") == "1"
    page = _positive_int(request.args.get("page"), 1)
    per_page = 100
    rows, total = db.list_movies(search or None, state or None, only_missing,
                                 limit=per_page, offset=(page - 1) * per_page)
    return render_template("index.html", movies=rows, total=total, page=page,
                           pages=max(1, (total + per_page - 1) // per_page),
                           stats=db.stats(primary_language()), search=search, state=state,
                           only_missing=only_missing, video_id=nfo.video_id_from)


@app.route("/movie")
@login_required
def movie_detail():
    row = db.get_movie(request.args.get("path", ""))
    if not row:
        abort(404)
    candidates = []
    error = None
    if request.args.get("search") == "1":
        try:
            candidates = SCANNER.candidates_for(row)
        except tmdb.TmdbError as e:
            error = str(e)
    return render_template("movie.html", movie=row, candidates=candidates,
                           error=error, video_id=nfo.video_id_from)


@app.route("/movie/save", methods=["POST"])
@login_required
def movie_save():
    path = request.form.get("path", "")
    row = db.get_movie(path)
    if not row:
        abort(404)
    raw = (request.form.get("link") or "").strip()
    if raw:
        vid = nfo.video_id_from(raw)
        if not vid:
            flash(t("msg.invalid_link"), "error")
            return redirect(url_for("movie_detail", path=path))
        fmt = setting("link_format", "emby")
        if flag("keep_format", "1") and row["trailer"]:
            fmt = nfo.detect_format(row["trailer"]) or fmt
        value = nfo.format_link(vid, fmt)
    else:
        value = ""

    try:
        nfo.write_trailer(Path(path), value, lockdata=flag("lockdata"),
                          backup=flag("backup", "1"))
    except (nfo.WriteError, OSError) as e:
        flash(str(e).splitlines()[0], "error")
        return redirect(url_for("movie_detail", path=path))

    db.mark_result(path, "ok" if value else "pending",
                   "Set by hand" if value else "Removed by hand",
                   trailer=value, trailer_lang=request.form.get("lang") or None,
                   written=True)
    db.log("ok", "{}: manually {}".format(row["title"], value or "removed"), "manual")
    flash(t("msg.saved") if value else t("msg.removed"), "ok")
    return redirect(url_for("movie_detail", path=path))


@app.route("/movie/check", methods=["POST"])
@login_required
def movie_check():
    path = request.form.get("path", "")
    row = db.get_movie(path)
    if not row:
        abort(404)
    status, msg = SCANNER.process_movie(row, force=True)
    flash("{}: {}".format(status, msg), "ok" if status == "ok" else "error")
    return redirect(url_for("movie_detail", path=path))


@app.route("/movie/diag")
@login_required
def movie_diag():
    """Plain text report on permissions - the usual cause of write failures."""
    path = request.args.get("path", "")
    row = db.get_movie(path)
    if not row:
        abort(404)
    return ("\n".join(nfo.check_write_access(path)), 200,
            {"Content-Type": "text/plain; charset=utf-8"})


@app.route("/run", methods=["POST"])
@login_required
def run_now():
    force = request.form.get("force") == "1"
    started = SCANNER.run_async(trigger="manual", force=force)
    flash(t("msg.started") if started else t("msg.already"), "ok" if started else "error")
    return redirect(_back())


@app.route("/scan", methods=["POST"])
@login_required
def scan_only():
    if SCANNER.scan_async():
        flash(t("msg.started"), "ok")
    else:
        flash(t("msg.already"), "error")
    return redirect(_back())


@app.route("/stop", methods=["POST"])
@login_required
def stop_run():
    SCANNER.stop()
    return redirect(_back())


@app.route("/status")
@login_required
def status():
    return jsonify({"busy": SCANNER.busy, "state": SCANNER.state,
                    "stats": db.stats(primary_language())})


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    keys_text = ["tmdb_api_key", "languages", "link_format", "scan_interval_hours",
                 "recheck_days", "ui_language"]
    keys_flag = ["keep_format", "backup", "lockdata", "scan_on_start", "overwrite_existing"]
    if request.method == "POST":
        for key in keys_text:
            db.set_setting(key, request.form.get(key, "").strip())
        for key in keys_flag:
            db.set_setting(key, "1" if request.form.get(key) else "0")
        session["lang"] = request.form.get("ui_language", "de")
        db.log("info", "Settings changed", "settings")
        flash(t("settings.saved"), "ok")
        return redirect(url_for("settings_page"))

    values = {key: setting(key, "") for key in keys_text}
    values.update({key: flag(key) for key in keys_flag})
    webhook_url = url_for("webhook", _external=True)
    if config.WEBHOOK_TOKEN:
        webhook_url += "?token=" + quote(config.WEBHOOK_TOKEN)
    return render_template("settings.html", values=values, webhook_url=webhook_url,
                           runs=db.last_runs(5))


@app.route("/settings/password", methods=["POST"])
@login_required
def settings_password():
    """Change the password - only meaningful when the wizard set it."""
    if config.credentials_from_env():
        flash(t("settings.pw_from_env"), "error")
        return redirect(url_for("settings_page"))
    current = request.form.get("current", "")
    new = request.form.get("password", "")
    repeat = request.form.get("password_repeat", "")
    if not password_ok(current):
        flash(t("settings.pw_wrong"), "error")
    elif len(new) < MIN_PASSWORD_LENGTH:
        flash(t("setup.err_short"), "error")
    elif new != repeat:
        flash(t("setup.err_repeat"), "error")
    else:
        db.set_setting("web_password_hash", generate_password_hash(new))
        db.log("info", "Password changed", "auth")
        flash(t("settings.pw_saved"), "ok")
    return redirect(url_for("settings_page"))


@app.route("/settings/test", methods=["POST"])
@login_required
def settings_test():
    try:
        count = tmdb.selftest(setting("tmdb_api_key", ""))
        flash("{} ({} videos)".format(t("msg.test_ok"), count), "ok")
    except tmdb.TmdbError as e:
        flash(str(e), "error")
    return redirect(url_for("settings_page"))


@app.route("/log")
@login_required
def log_page():
    return render_template("log.html", entries=db.recent_log(300), runs=db.last_runs(10))


# --------------------------------------------------------------------- webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    """Emby, Jellyfin and Jellyseerr report new movies here.

    Guarded by a token (query parameter or header), because webhooks have to
    work without a session.
    """
    if not config.WEBHOOK_TOKEN:
        # Without a token the endpoint would be open to anyone who reaches the port.
        db.log("warn", "Webhook refused: WEBHOOK_TOKEN is not set", "webhook")
        abort(403)
    supplied = (request.args.get("token")
                or request.headers.get("X-Webhook-Token", ""))
    if not _equal(supplied, config.WEBHOOK_TOKEN):
        db.log("warn", "Webhook with a wrong token from {}".format(request.remote_addr),
               "webhook")
        abort(403)

    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() or {}
    event = (payload.get("Event") or payload.get("NotificationType")
             or payload.get("notification_type") or "")
    if event and not any(word in str(event).lower()
                         for word in ("add", "new", "created", "available", "library")):
        return jsonify({"ignored": event})

    threading.Thread(target=SCANNER.handle_event, args=(payload,), daemon=True).start()
    return jsonify({"accepted": True, "event": event})


@app.route("/health")
def health():
    return jsonify({"ok": True, "busy": SCANNER.busy if SCANNER else False})


# ----------------------------------------------------------------------- start
def create_app():
    """Build the application. Calling this twice (Gunicorn reload) is harmless."""
    global SCANNER
    if SCANNER is not None:
        return app
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db.init(config.DB_PATH)
    for key, value in config.DEFAULTS.items():
        if db.get_setting(key) is None:
            db.set_setting(key, value)

    # An installation that already ran before the wizard existed, or one fully
    # configured through the environment, should not be sent to the wizard.
    if db.get_setting("setup_done") is None:
        configured = bool(config.DEFAULTS["tmdb_api_key"] and config.credentials_from_env())
        db.set_setting("setup_done", "1" if configured else "0")

    config.WEBHOOK_TOKEN, persisted = config.ensure_webhook_token()
    if not persisted:
        db.log("warn", "The webhook token could not be stored under /config - it only "
                       "lasts until the next restart. Check the permissions.", "app")

    SCANNER = scanner_mod.Scanner(config.MOVIES_DIR, setting)
    SCANNER.start_scheduler()
    db.log("info", "Trailer DE started (library: {})".format(config.MOVIES_DIR), "app")
    return app


if __name__ == "__main__":
    create_app()
    app.run(host="0.0.0.0", port=config.PORT)
