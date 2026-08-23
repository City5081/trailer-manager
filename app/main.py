"""Trailer DE - Weboberflaeche.

Traegt deutsche TMDB-Trailer in die NFO-Dateien einer Emby-Filmbibliothek ein:
per Zeitplan, per Knopfdruck oder sofort, wenn Emby/Jellyseerr einen neuen Film
melden.
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
from werkzeug.security import check_password_hash

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
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024      # Webhook-Nutzlasten sind klein

SCANNER = None


@app.template_filter("ts")
def format_ts(value):
    """Zeitstempel lesbar machen - in der Schreibweise der gewaehlten Sprache."""
    if not value:
        return ""
    try:
        stamp = time.localtime(float(value))
    except (TypeError, ValueError):
        return ""
    pattern = "%d.%m.%Y %H:%M:%S" if current_lang() == "de" else "%Y-%m-%d %H:%M:%S"
    return time.strftime(pattern, stamp)


# --------------------------------------------------------------- Einstellungen
def setting(key, default=None):
    value = db.get_setting(key)
    if value is None or value == "":
        value = config.DEFAULTS.get(key, default)
    return value if value is not None else default


def flag(key, default="0"):
    return str(setting(key, default)) in ("1", "true", "True", "on", "yes")


# ------------------------------------------------------------------ Anmeldung
def _equal(left, right):
    """Zeitkonstanter Vergleich, der auch Umlaute im Passwort vertraegt.

    hmac.compare_digest wirft bei Zeichenketten ausserhalb von ASCII einen
    TypeError - deshalb erst nach UTF-8 wandeln.
    """
    return hmac.compare_digest((left or "").encode("utf-8"),
                               (right or "").encode("utf-8"))


def password_ok(password):
    if config.WEB_PASSWORD_HASH:
        return check_password_hash(config.WEB_PASSWORD_HASH, password)
    if config.WEB_PASSWORD:
        return _equal(config.WEB_PASSWORD, password)
    return False


_ATTEMPTS = {}                          # {ip: [Anzahl, Zeitpunkt des letzten Versuchs]}
_ATTEMPTS_LOCK = threading.Lock()
LOCKOUT_AFTER = 5                       # ab so vielen Fehlversuchen wird gewartet
LOCKOUT_SECONDS = 300                   # danach zaehlt der Zaehler wieder von vorn


def _login_delay(ip):
    """Wartezeit nach wiederholten Fehlversuchen, gedeckelt auf 30 Sekunden."""
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
        if len(_ATTEMPTS) > 1000:       # keine unbegrenzte Liste im Speicher
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
        time.sleep(1 + _login_delay(ip))    # bremst Rateversuche aus
        user = request.form.get("username", "")
        pwd = request.form.get("password", "")
        if _equal(user, config.WEB_USERNAME) and password_ok(pwd):
            _note_attempt(ip, True)
            session.clear()                 # neue Sitzungskennung nach dem Login
            session["user"] = user
            session.permanent = True
            db.log("info", "Anmeldung: {}".format(user), "auth")
            return redirect(_safe_next(request.args.get("next")))
        _note_attempt(ip, False)
        error = t("login.failed")
        db.log("warn", "Fehlgeschlagene Anmeldung von {}".format(ip), "auth")
    return render_template("login.html", error=error)


def _safe_next(target):
    """Nur Weiterleitungen innerhalb der eigenen Oberflaeche zulassen."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("index")


def _back():
    """Zurueck zur vorigen Seite - aber nur, wenn sie zu uns gehoert."""
    referrer = request.referrer or ""
    if referrer.startswith(request.host_url):
        return referrer
    return url_for("index")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------- Sprache
def current_lang():
    return session.get("lang") or setting("ui_language", "de")


def t(key):
    return i18n.translate(current_lang(), key)


@app.route("/lang/<code>")
def switch_language(code):
    if code in i18n.LANGUAGES:
        session["lang"] = code
    return redirect(_back())


# ----------------------------------------------------------------------- CSRF
CSRF_EXEMPT = {"webhook", "health", "static"}


def csrf_token():
    """Ein Token je Sitzung; liegt in jedem Formular und wird beim POST geprueft."""
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
    # Ohne Token in der Sitzung darf nichts durchgehen - sonst wuerde ein leeres
    # Feld gegen einen leeren Erwartungswert stimmen.
    if not expected or not _equal(supplied, expected):
        db.log("warn", "Anfrage ohne gueltiges CSRF-Token ({})".format(request.path), "auth")
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


MAX_PAGE = 1_000_000


def _positive_int(value, default):
    """Zahlen aus der Adresszeile duerfen nicht in einem Serverfehler enden.

    Auch die Obergrenze ist noetig: SQLite nimmt keine beliebig grossen Zahlen
    als OFFSET und wirft sonst einen OverflowError.
    """
    try:
        return min(MAX_PAGE, max(1, int(value)))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------- Seiten
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
                           stats=db.stats(), search=search, state=state,
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
                   "Manuell gesetzt" if value else "Manuell entfernt",
                   trailer=value, trailer_lang=request.form.get("lang") or None,
                   written=True)
    db.log("ok", "{}: manuell {}".format(row["title"], value or "entfernt"), "manual")
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
    """Klartext-Auskunft zu Rechten - die haeufigste Ursache fuer Schreibfehler."""
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
    return jsonify({"busy": SCANNER.busy, "state": SCANNER.state, "stats": db.stats()})


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
        db.log("info", "Einstellungen geaendert", "settings")
        flash(t("settings.saved"), "ok")
        return redirect(url_for("settings_page"))

    values = {key: setting(key, "") for key in keys_text}
    values.update({key: flag(key) for key in keys_flag})
    webhook_url = url_for("webhook", _external=True)
    if config.WEBHOOK_TOKEN:
        webhook_url += "?token=" + quote(config.WEBHOOK_TOKEN)
    return render_template("settings.html", values=values, webhook_url=webhook_url,
                           runs=db.last_runs(5))


@app.route("/settings/test", methods=["POST"])
@login_required
def settings_test():
    try:
        count = tmdb.selftest(setting("tmdb_api_key", ""))
        flash("{} ({} Videos)".format(t("msg.test_ok"), count), "ok")
    except tmdb.TmdbError as e:
        flash(str(e), "error")
    return redirect(url_for("settings_page"))


@app.route("/log")
@login_required
def log_page():
    return render_template("log.html", entries=db.recent_log(300), runs=db.last_runs(10))


# ------------------------------------------------------------------- Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    """Emby, Jellyfin und Jellyseerr melden hier neue Filme.

    Absicherung ueber ein Token (Query-Parameter oder Header), weil Webhooks
    ohne Sitzung auskommen muessen.
    """
    if not config.WEBHOOK_TOKEN:
        # Ohne Token waere der Endpunkt fuer jeden offen, der den Port erreicht.
        db.log("warn", "Webhook abgewiesen: WEBHOOK_TOKEN ist nicht gesetzt", "webhook")
        abort(403)
    supplied = (request.args.get("token")
                or request.headers.get("X-Webhook-Token", ""))
    if not _equal(supplied, config.WEBHOOK_TOKEN):
        db.log("warn", "Webhook mit falschem Token von {}".format(request.remote_addr),
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


# ---------------------------------------------------------------------- Start
def create_app():
    """Anwendung aufbauen. Mehrfachaufrufe (Gunicorn-Reload) sind harmlos."""
    global SCANNER
    if SCANNER is not None:
        return app
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db.init(config.DB_PATH)
    for key, value in config.DEFAULTS.items():
        if db.get_setting(key) is None:
            db.set_setting(key, value)
    config.WEBHOOK_TOKEN, dauerhaft = config.ensure_webhook_token()
    if not dauerhaft:
        db.log("warn", "Webhook-Token liess sich nicht unter /config ablegen - es "
                       "gilt nur bis zum Neustart. Schreibrechte pruefen.", "app")

    SCANNER = scanner_mod.Scanner(config.MOVIES_DIR, setting)
    SCANNER.start_scheduler()
    db.log("info", "Trailer DE gestartet (Bibliothek: {})".format(config.MOVIES_DIR), "app")
    if not config.WEB_PASSWORD and not config.WEB_PASSWORD_HASH and not config.AUTH_DISABLED:
        db.log("warn", "Kein WEB_PASSWORD gesetzt - Anmeldung nicht moeglich!", "app")
    return app


if __name__ == "__main__":
    create_app()
    app.run(host="0.0.0.0", port=config.PORT)
