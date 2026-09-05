"""Trailer Manager - web interface.

Writes TMDB trailers in the language you want into the NFO files of an Emby
library: on a schedule, at the push of a button, or right away when Emby or
Jellyseerr reports a new item. Any number of libraries, each holding movies or
TV shows.
"""

import functools
import hmac
import secrets
import threading
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
import emby as emby_mod
import i18n
import notify as notify_mod
import nfo
import scanner as scanner_mod
import tmdb

app = Flask(__name__)
app.secret_key = config.ensure_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = config.COOKIE_SECURE
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=config.SESSION_DAYS)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024      # forms here are tiny

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


def primary_language(lib=None):
    """First configured language - the one the dashboard counts.

    A library may point at a different one, so an anime library looking for
    Japanese trailers is measured against Japanese, not against German.
    """
    raw = None
    if lib is not None:
        raw = lib["languages"]
    if not raw:
        raw = setting("languages", "de") or "de"
    first = str(raw).split(",")[0].strip().split("-")[0]
    return (first or "de").lower()


def library_stats(library_id=None):
    """One block of counts per library, so they are never lumped together."""
    out = []
    for lib in db.list_libraries():
        if library_id is not None and lib["id"] != library_id:
            continue
        out.append({"lib": lib,
                    "stats": db.stats(primary_language(lib), lib["id"])})
    return out


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
    """Back to the previous page.

    Only the path of the referrer is used, never its host, which does two
    things at once: it cannot send anyone to another site, and it survives a
    reverse proxy. Comparing against request.host_url used to fail there - the
    browser reports https://example.com/settings while the application sees
    itself as http://container:8081/, so every button landed on the start page.
    """
    parts = urlsplit(request.referrer or "")
    target = parts.path + (("?" + parts.query) if parts.query else "")
    if target.startswith("/") and not target.startswith("//"):
        return target
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
CSRF_EXEMPT = {"health", "static"}


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


def _optional_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def nav_libraries():
    """Libraries for the header. Empty while the wizard is still running."""
    if not setup_done():
        return []
    return db.list_libraries(only_enabled=True)


@app.context_processor
def inject_globals():
    return {
        "t": t,
        "csrf_token": csrf_token,
        "nav_libraries": nav_libraries(),
        "active_library": _optional_int(request.args.get("library")),
        "lang": current_lang(),
        "languages": i18n.LANGUAGES,
        "link_formats": nfo.LINK_FORMATS,
        "busy": SCANNER.busy if SCANNER else False,
        "progress": SCANNER.state if SCANNER else {},
        "auth_disabled": config.AUTH_DISABLED,
    }


# ----------------------------------------------------------------- setup wizard
SETUP_EXEMPT = {"setup", "static", "health", "login", "switch_language"}


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
    first = (db.list_libraries() or [None])[0]
    values = {
        "library_name": (first["name"] if first else "Movies"),
        "library_path": (first["path"] if first else str(config.MOVIES_DIR)),
        "library_kind": (first["kind"] if first else "movie"),
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
                    "scan_interval_hours", "recheck_days", "ui_language",
                    "library_name", "library_path", "library_kind"):
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

        if not values["library_name"] or not values["library_path"]:
            errors.append(t("library.err_fields"))
        elif not Path(values["library_path"]).is_dir():
            errors.append(t("library.err_path"))

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
            kind = values["library_kind"] if values["library_kind"] in db.KINDS else "movie"
            if first:
                db.update_library(first["id"], name=values["library_name"],
                                  path=values["library_path"], kind=kind)
            else:
                db.add_library(values["library_name"], values["library_path"], kind)
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
    library_id = _optional_int(request.args.get("library"))
    sort = request.args.get("sort", "title")
    if sort not in db.SORT_COLUMNS:
        sort = "title"
    direction = "desc" if request.args.get("dir") == "desc" else "asc"
    page = _positive_int(request.args.get("page"), 1)
    per_page = 100
    rows, total = db.list_movies(search or None, state or None, only_missing,
                                 limit=per_page, offset=(page - 1) * per_page,
                                 library_id=library_id, sort=sort, direction=direction)
    return render_template("index.html", movies=rows, total=total, page=page,
                           pages=max(1, (total + per_page - 1) // per_page),
                           library_stats=library_stats(library_id),
                           libraries=db.list_libraries(), library_id=library_id,
                           sort=sort, direction=direction,
                           search=search, state=state,
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
        db.log("error", "{}:\n{}".format(row["title"], nfo.failure_report(path, e)), "write")
        flash(str(e).splitlines()[0], "error")
        return redirect(url_for("movie_detail", path=path))

    db.mark_result(path, "ok" if value else "pending",
                   "Set by hand" if value else "Removed by hand",
                   trailer=value, trailer_lang=request.form.get("lang") or None,
                   written=True)
    db.log("ok", "{}: manually {}".format(row["title"], value or "removed"), "manual")
    SCANNER.notify_media_server(row, row["tmdb_id"])
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
    # Back to wherever the button was pressed - the list or the detail page.
    return redirect(_back())


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
                 "recheck_days", "emby_poll_minutes", "ui_language",
                 "emby_url", "emby_api_key"]
    keys_flag = ["keep_format", "backup", "lockdata", "scan_on_start",
                 "overwrite_existing"]
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
    values.update({key: flag(key) for key in NOTIFY_EVENTS})
    return render_template("settings.html", values=values,
                           runs=db.last_runs(5), libraries=db.list_libraries(),
                           counts=db.library_counts(), kinds=db.KINDS,
                           notify_services=sorted(notify_mod.SERVICES),
                           notify_examples={name: notify_mod.example_url(name)
                                            for name in notify_mod.SERVICES},
                           notifiers=db.list_notifiers(),
                           last_poll=db.get_setting("emby_last_poll") or "")


# --------------------------------------------------------------------- libraries
def _library_form():
    """The fields shared by adding and editing a library."""
    overrides = {}
    for key in db.LIBRARY_OVERRIDES:
        overrides[key] = request.form.get(key, "").strip()
    # Checkboxes need three states here: inherit, on, off. A select box sends
    # "", "1" or "0", so an empty value keeps the global setting.
    return overrides


@app.route("/library/add", methods=["POST"])
@login_required
def library_add():
    name = request.form.get("name", "").strip()
    path = request.form.get("path", "").strip()
    kind = request.form.get("kind", "movie")
    if not name or not path:
        flash(t("library.err_fields"), "error")
    elif not Path(path).is_dir():
        flash(t("library.err_path"), "error")
    else:
        lib_id = db.add_library(name, path, kind, **_library_form())
        db.log("info", "Library '{}' added ({}, {})".format(name, kind, path), "settings")
        flash(t("library.added"), "ok")
        return redirect(url_for("library_edit", lib_id=lib_id))
    return redirect(url_for("settings_page"))


@app.route("/library/<int:lib_id>", methods=["GET", "POST"])
@login_required
def library_edit(lib_id):
    lib = db.get_library(lib_id)
    if not lib:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        path = request.form.get("path", "").strip()
        if not name or not path:
            flash(t("library.err_fields"), "error")
        elif not Path(path).is_dir():
            flash(t("library.err_path"), "error")
        else:
            db.update_library(lib_id, name=name, path=path,
                              kind=request.form.get("kind", "movie"),
                              enabled=1 if request.form.get("enabled") else 0,
                              **_library_form())
            db.log("info", "Library '{}' changed".format(name), "settings")
            flash(t("settings.saved"), "ok")
            return redirect(url_for("settings_page"))
        lib = db.get_library(lib_id)
    return render_template("library.html", lib=lib, kinds=db.KINDS,
                           count=db.library_counts().get(lib_id, 0))


@app.route("/library/<int:lib_id>/delete", methods=["POST"])
@login_required
def library_delete(lib_id):
    lib = db.get_library(lib_id)
    if not lib:
        abort(404)
    db.delete_library(lib_id)
    db.log("warn", "Library '{}' removed from the database".format(lib["name"]), "settings")
    flash(t("library.deleted"), "ok")
    return redirect(url_for("settings_page"))


@app.route("/library/<int:lib_id>/scan", methods=["POST"])
@login_required
def library_scan(lib_id):
    lib = db.get_library(lib_id)
    if not lib:
        abort(404)
    started = SCANNER.run_async(trigger="manual", library_id=lib_id)
    flash(t("msg.started") if started else t("msg.already"), "ok" if started else "error")
    return redirect(_back())


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


NOTIFY_EVENTS = ("notify_on_new", "notify_on_run", "notify_on_error")


@app.route("/settings/notifications", methods=["POST"])
@login_required
def settings_notifications():
    """Only the three event switches - the targets have their own forms."""
    for key in NOTIFY_EVENTS:
        db.set_setting(key, "1" if request.form.get(key) else "0")
    db.log("info", "Notification settings changed", "settings")
    flash(t("settings.saved"), "ok")
    return redirect(url_for("settings_page"))


@app.route("/notifier/add", methods=["POST"])
@login_required
def notifier_add():
    service = request.form.get("service", "")
    url = request.form.get("url", "").strip()
    if service not in notify_mod.SERVICES:
        flash(t("notify.err_service"), "error")
    elif not url:
        flash(t("notify.err_url"), "error")
    else:
        db.add_notifier(service, url, request.form.get("token", ""))
        db.log("info", "Notification target added ({})".format(service), "settings")
        flash(t("notify.added"), "ok")
    return redirect(url_for("settings_page"))


@app.route("/notifier/<int:notifier_id>/toggle", methods=["POST"])
@login_required
def notifier_toggle(notifier_id):
    target = db.get_notifier(notifier_id)
    if not target:
        abort(404)
    db.update_notifier(notifier_id, enabled=0 if target["enabled"] else 1)
    # Straight back to the settings, never to the start page.
    return redirect(url_for("settings_page"))


@app.route("/notifier/<int:notifier_id>", methods=["GET", "POST"])
@login_required
def notifier_edit(notifier_id):
    target = db.get_notifier(notifier_id)
    if not target:
        abort(404)
    if request.method == "POST":
        service = request.form.get("service", "")
        url = request.form.get("url", "").strip()
        if service not in notify_mod.SERVICES:
            flash(t("notify.err_service"), "error")
        elif not url:
            flash(t("notify.err_url"), "error")
        else:
            db.update_notifier(notifier_id, service=service, url=url,
                               token=request.form.get("token", "").strip(),
                               enabled=1 if request.form.get("enabled") else 0)
            db.log("info", "Notification target changed ({})".format(service), "settings")
            flash(t("settings.saved"), "ok")
            return redirect(url_for("settings_page"))
        target = db.get_notifier(notifier_id)
    return render_template("notifier.html", target=target,
                           services=sorted(notify_mod.SERVICES),
                           examples={name: notify_mod.example_url(name)
                                     for name in notify_mod.SERVICES})


@app.route("/notifier/<int:notifier_id>/delete", methods=["POST"])
@login_required
def notifier_delete(notifier_id):
    if not db.get_notifier(notifier_id):
        abort(404)
    db.delete_notifier(notifier_id)
    flash(t("notify.deleted"), "ok")
    return redirect(url_for("settings_page"))


@app.route("/notifier/<int:notifier_id>/test", methods=["POST"])
@login_required
def notifier_test(notifier_id):
    target = db.get_notifier(notifier_id)
    if not target:
        abort(404)
    try:
        notify_mod.send(target["service"], target["url"], target["token"],
                        t("notify.test_title"), t("notify.test_body"))
        flash("{}: {}".format(target["service"], t("notify.test_ok")), "ok")
    except notify_mod.NotifyError as e:
        flash("{}: {}".format(target["service"], e), "error")
    return redirect(url_for("settings_page"))


@app.route("/settings/emby-test", methods=["POST"])
@login_required
def settings_emby_test():
    server = emby_mod.Emby(setting("emby_url", ""), setting("emby_api_key", ""))
    if not server.configured():
        flash(t("emby.err_missing"), "error")
        return redirect(url_for("settings_page"))
    try:
        info = server.info()
        count = len(server._build_index())
        flash("{}: {} {} - {} {}".format(t("emby.test_ok"), info["name"], info["version"],
                                         count, t("emby.entries_found")), "ok")
    except emby_mod.EmbyError as e:
        flash(str(e), "error")
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


@app.route("/health")
def health():
    return jsonify({"ok": True, "busy": SCANNER.busy if SCANNER else False})


# ----------------------------------------------------------------------- start
def ensure_default_library():
    """Give an installation without libraries the one from MOVIES_DIR.

    That covers both a fresh start and an upgrade from the single folder
    version, whose entries are adopted instead of being read again - rescanning
    1600 NFOs over SMB is not something to ask for on an update.
    """
    if db.list_libraries():
        return None
    lib_id = db.add_library("Movies", str(config.MOVIES_DIR), "movie")
    adopted = db.assign_all_to_library(lib_id)
    if adopted:
        db.log("info", "{} existing entries moved into the library '{}'"
               .format(adopted, "Movies"), "app")
    return lib_id


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

    # A target configured through the environment, or from before several of
    # them were possible, becomes the first entry in the list.
    if not db.list_notifiers():
        service = (config.DEFAULTS.get("notify_service") or "").strip()
        url = (config.DEFAULTS.get("notify_url") or "").strip()
        if service in notify_mod.SERVICES and url:
            db.add_notifier(service, url, config.DEFAULTS.get("notify_token", ""))
            db.log("info", "Notification target taken from the environment ({})"
                   .format(service), "app")

    # The waiting time used to be called webhook_wait. Carry the configured
    # value over instead of silently resetting it to the default.
    old_wait = db.get_setting("webhook_wait")
    if old_wait and db.get_setting("nfo_wait") in (None, ""):
        db.set_setting("nfo_wait", old_wait)

    # An installation that already ran before the wizard existed, or one fully
    # configured through the environment, should not be sent to the wizard.
    if db.get_setting("setup_done") is None:
        configured = bool(config.DEFAULTS["tmdb_api_key"] and config.credentials_from_env())
        db.set_setting("setup_done", "1" if configured else "0")

    ensure_default_library()
    SCANNER = scanner_mod.Scanner(setting)
    SCANNER.start_scheduler()
    db.log("info", "Trailer Manager started ({} libraries)"
           .format(len(db.list_libraries())), "app")
    return app


if __name__ == "__main__":
    create_app()
    app.run(host="0.0.0.0", port=config.PORT)
