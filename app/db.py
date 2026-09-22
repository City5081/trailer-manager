"""SQLite storage: libraries, entries, log, settings, runs.

The inventory is kept between runs. An automatic run therefore only touches
entries that are new, whose NFO changed, or that came back empty last time.

"Entries" are movies or TV shows: one row per NFO file. Which of the two it is
follows from the library the row belongs to.
"""

import sqlite3
import threading
import time
from contextlib import contextmanager

_local = threading.local()
_DB_PATH = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS libraries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    path         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'movie',   -- movie | tv
    enabled      INTEGER NOT NULL DEFAULT 1,
    -- Empty means "use the global setting"; every library may override.
    languages    TEXT DEFAULT '',
    link_format  TEXT DEFAULT '',
    keep_format  TEXT DEFAULT '',
    backup       TEXT DEFAULT '',
    lockdata     TEXT DEFAULT '',
    recheck_days TEXT DEFAULT '',
    created      REAL
);

CREATE TABLE IF NOT EXISTS movies (
    path           TEXT PRIMARY KEY,
    library_id     INTEGER,
    folder         TEXT NOT NULL,
    title          TEXT,
    year           TEXT,
    tmdb_id        TEXT,
    imdb_id        TEXT,
    trailer        TEXT,
    trailer_lang   TEXT,
    state          TEXT,            -- ok | no_trailer | no_id | error | pending
    message        TEXT,
    mtime          REAL,
    size           INTEGER,
    first_seen     REAL,
    last_scanned   REAL,            -- NFO last read
    last_checked   REAL,            -- TMDB last asked
    last_changed   REAL             -- NFO last written by us
);
CREATE INDEX IF NOT EXISTS idx_movies_state   ON movies(state);
CREATE INDEX IF NOT EXISTS idx_movies_tmdb    ON movies(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_movies_folder  ON movies(folder);
CREATE INDEX IF NOT EXISTS idx_movies_library ON movies(library_id);

-- Notification targets. Several can be active at once; each is one service
-- with its own address, and can be switched off without losing its settings.
CREATE TABLE IF NOT EXISTS notifiers (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    url     TEXT NOT NULL,
    token   TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created REAL
);

CREATE TABLE IF NOT EXISTS log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    level   TEXT NOT NULL,
    source  TEXT,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_ts ON log(ts DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started   REAL,
    finished  REAL,
    trigger   TEXT,          -- manual | schedule | start
    scanned   INTEGER DEFAULT 0,
    checked   INTEGER DEFAULT 0,
    updated   INTEGER DEFAULT 0,
    failed    INTEGER DEFAULT 0
);
"""


def init(path):
    global _DB_PATH
    _DB_PATH = str(path)
    with connect() as con:
        con.executescript(SCHEMA)
        _migrate(con)


def _migrate(con):
    """Bring an older database up to date.

    Installations from before multiple libraries existed have a movies table
    without library_id. Adding the column keeps their inventory - re-reading
    1600 NFOs over SMB is not something to ask for on an update.
    """
    columns = {r["name"] for r in con.execute("PRAGMA table_info(movies)")}
    if "library_id" not in columns:
        con.execute("ALTER TABLE movies ADD COLUMN library_id INTEGER")


def _conn():
    con = getattr(_local, "con", None)
    if con is None:
        con = sqlite3.connect(_DB_PATH, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA synchronous=NORMAL")
        _local.con = con
    return con


@contextmanager
def connect():
    con = _conn()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise


# ------------------------------------------------------------------- settings
def get_setting(key, default=None):
    with connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with connect() as con:
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value)))


def all_settings():
    with connect() as con:
        return {r["key"]: r["value"] for r in con.execute("SELECT key,value FROM settings")}


# ------------------------------------------------------------------ libraries
LIBRARY_OVERRIDES = ("languages", "link_format", "keep_format", "backup",
                     "lockdata", "recheck_days")
KINDS = ("movie", "tv")


def add_library(name, path, kind="movie", **overrides):
    with connect() as con:
        cur = con.execute(
            "INSERT INTO libraries(name, path, kind, enabled, created) VALUES(?,?,?,1,?)",
            (name, str(path).rstrip("/") or "/", kind if kind in KINDS else "movie",
             time.time()))
        lib_id = cur.lastrowid
    if overrides:
        update_library(lib_id, **overrides)
    return lib_id


def update_library(lib_id, **fields):
    allowed = ("name", "path", "kind", "enabled") + LIBRARY_OVERRIDES
    sets, params = [], []
    for key, value in fields.items():
        if key not in allowed:
            continue
        sets.append("{}=?".format(key))
        params.append(value)
    if not sets:
        return
    params.append(lib_id)
    with connect() as con:
        con.execute("UPDATE libraries SET {} WHERE id=?".format(", ".join(sets)), params)


def delete_library(lib_id):
    """Remove a library and everything it held.

    Only the database rows go - the NFO files themselves are never touched.
    """
    with connect() as con:
        con.execute("DELETE FROM movies WHERE library_id=?", (lib_id,))
        con.execute("DELETE FROM libraries WHERE id=?", (lib_id,))


def get_library(lib_id):
    if lib_id is None:
        return None
    with connect() as con:
        return con.execute("SELECT * FROM libraries WHERE id=?", (lib_id,)).fetchone()


def list_libraries(only_enabled=False):
    sql = "SELECT * FROM libraries"
    if only_enabled:
        sql += " WHERE enabled=1"
    sql += " ORDER BY name COLLATE NOCASE"
    with connect() as con:
        return con.execute(sql).fetchall()


def library_counts():
    """{library_id: number of entries} - for the overview in the settings."""
    with connect() as con:
        return {r["library_id"]: r["c"] for r in con.execute(
            "SELECT library_id, COUNT(*) c FROM movies GROUP BY library_id")}


# ------------------------------------------------------------------ notifiers
def add_notifier(service, url, token="", enabled=True):
    with connect() as con:
        cur = con.execute(
            "INSERT INTO notifiers(service, url, token, enabled, created) "
            "VALUES(?,?,?,?,?)",
            (service, url.strip(), (token or "").strip(), 1 if enabled else 0,
             time.time()))
        return cur.lastrowid


def update_notifier(notifier_id, **fields):
    allowed = ("service", "url", "token", "enabled")
    sets, params = [], []
    for key, value in fields.items():
        if key in allowed:
            sets.append("{}=?".format(key))
            params.append(value)
    if not sets:
        return
    params.append(notifier_id)
    with connect() as con:
        con.execute("UPDATE notifiers SET {} WHERE id=?".format(", ".join(sets)), params)


def delete_notifier(notifier_id):
    with connect() as con:
        con.execute("DELETE FROM notifiers WHERE id=?", (notifier_id,))


def get_notifier(notifier_id):
    with connect() as con:
        return con.execute("SELECT * FROM notifiers WHERE id=?",
                           (notifier_id,)).fetchone()


def list_notifiers(only_enabled=False):
    sql = "SELECT * FROM notifiers"
    if only_enabled:
        sql += " WHERE enabled=1"
    sql += " ORDER BY id"
    with connect() as con:
        return con.execute(sql).fetchall()


# --------------------------------------------------------------------- movies
def upsert_movie(path, folder, data, mtime, size, library_id=None):
    """Record what an NFO says. True when its trailer was changed by someone else.

    A media server rewrites NFOs when it refreshes metadata, and puts its own
    trailer in ours. Keeping the state as it was would leave the entry at "done"
    with a trailer nobody here chose, and it would never be looked at again -
    so a trailer that differs from the one on record sends it back to pending.
    """
    now = time.time()
    with connect() as con:
        row = con.execute("SELECT trailer, state FROM movies WHERE path=?",
                          (path,)).fetchone()
        replaced = row is not None and (row["trailer"] or "") != (data["trailer"] or "")

        if row is None:
            con.execute("""
                INSERT INTO movies(path, library_id, folder, title, year, tmdb_id,
                                   imdb_id, trailer, state, mtime, size,
                                   first_seen, last_scanned)
                VALUES(?,?,?,?,?,?,?,?,'pending',?,?,?,?)
            """, (path, library_id, folder, data["title"], data["year"], data["tmdb"],
                  data["imdb"], data["trailer"], mtime, size, now, now))
            return False

        con.execute("""
            UPDATE movies SET library_id=?, folder=?, title=?, year=?, tmdb_id=?,
                              imdb_id=?, trailer=?, mtime=?, size=?, last_scanned=?,
                              state=CASE WHEN ? THEN 'pending' ELSE state END
            WHERE path=?
        """, (library_id, folder, data["title"], data["year"], data["tmdb"],
              data["imdb"], data["trailer"], mtime, size, now,
              1 if replaced else 0, path))
        return replaced


def mark_result(path, state, message=None, trailer=None, trailer_lang=None, written=False):
    now = time.time()
    with connect() as con:
        if written:
            con.execute("UPDATE movies SET state=?, message=?, trailer=?, trailer_lang=?, "
                        "last_checked=?, last_changed=? WHERE path=?",
                        (state, message, trailer, trailer_lang, now, now, path))
        else:
            con.execute("UPDATE movies SET state=?, message=?, last_checked=? WHERE path=?",
                        (state, message, now, path))


def note_trailer_lang(path, lang):
    """Record the language of a trailer that was already in the NFO.

    Those links come from Emby, not from us, so nothing is written to disk -
    but knowing the language is what makes the language column and the
    "of which German" figure meaningful.
    """
    with connect() as con:
        con.execute("UPDATE movies SET trailer_lang=? WHERE path=?", (lang, path))


def get_movie(path):
    with connect() as con:
        return con.execute("SELECT * FROM movies WHERE path=?", (path,)).fetchone()


def find_by_tmdb(tmdb_id):
    with connect() as con:
        return con.execute("SELECT * FROM movies WHERE tmdb_id=?", (str(tmdb_id),)).fetchall()


def find_by_folder(folder):
    with connect() as con:
        return con.execute("SELECT * FROM movies WHERE folder=?", (folder,)).fetchall()


def known_files(library_id=None):
    """{path: (mtime, size)} - used to skip unchanged files while scanning."""
    sql = "SELECT path, mtime, size FROM movies"
    params = ()
    if library_id is not None:
        sql += " WHERE library_id=?"
        params = (library_id,)
    with connect() as con:
        return {r["path"]: (r["mtime"], r["size"]) for r in con.execute(sql, params)}


def delete_movie(path):
    """Forget one entry, e.g. after its file was renamed away."""
    with connect() as con:
        con.execute("DELETE FROM movies WHERE path=?", (path,))


def delete_missing(paths_present, library_id=None):
    """Drop entries whose NFO is gone.

    Scoped to one library, so scanning a single folder never deletes rows that
    belong to another one.
    """
    sql = "SELECT path FROM movies"
    params = ()
    if library_id is not None:
        sql += " WHERE library_id=?"
        params = (library_id,)
    with connect() as con:
        rows = con.execute(sql, params).fetchall()
        gone = [r["path"] for r in rows if r["path"] not in paths_present]
        for path in gone:
            con.execute("DELETE FROM movies WHERE path=?", (path,))
    return gone


def pending_movies(recheck_seconds, overwrite_existing=False, limit=None,
                   library_id=None):
    """What an automatic run picks up.

    - always: new entries and entries without a trailer
    - again: entries that came back empty, once the last attempt is old enough
    - never: finished entries, unless 'overwrite_existing' is set

    Scoped to one library when asked, because the recheck interval is a
    per-library setting.
    """
    cutoff = time.time() - recheck_seconds
    scope = "" if library_id is None else " AND library_id = :library"
    sql = """
        SELECT * FROM movies
        WHERE ((:overwrite = 1)
           OR state IS NULL OR state IN ('pending', 'error')
           OR (trailer IS NULL OR trailer = '')
           OR (state IN ('no_trailer', 'no_id')
               AND (last_checked IS NULL OR last_checked < :cutoff))){}
        ORDER BY (last_checked IS NOT NULL), last_checked ASC, title ASC
    """.format(scope)
    if limit:
        sql += " LIMIT {:d}".format(int(limit))
    with connect() as con:
        return con.execute(sql, {"overwrite": 1 if overwrite_existing else 0,
                                 "cutoff": cutoff,
                                 "library": library_id}).fetchall()


# A filter that spans the states you would actually want to do something about.
PROBLEM_STATES_KEY = "problem"

# What the column headers may sort by. A whitelist, because the value comes
# straight out of the address bar and goes into an ORDER BY.
SORT_COLUMNS = {
    "title": "m.title COLLATE NOCASE",
    "library": "l.name COLLATE NOCASE",
    "year": "m.year",
    "lang": "m.trailer_lang",
    "state": "m.state",
    "changed": "m.last_changed",     # when we last wrote a trailer
    "checked": "m.last_checked",     # when TMDB was last asked
}
# Columns that can be empty. Those rows belong at the end either way, otherwise
# "newest first" starts with a screen full of movies that never got a trailer.
SORT_NULLABLE = ("year", "lang", "changed", "checked")


def order_clause(sort, direction):
    column = SORT_COLUMNS.get(sort) or SORT_COLUMNS["title"]
    heading = "DESC" if str(direction).lower() == "desc" else "ASC"
    empty_last = ""
    if sort in SORT_NULLABLE:
        empty_last = "({} IS NULL OR {} = ''), ".format(column, column)
    return "{}{} {}, m.title COLLATE NOCASE ASC".format(empty_last, column, heading)


def list_movies(search=None, state=None, only_missing=False, limit=500, offset=0,
                library_id=None, sort="title", direction="asc"):
    where, params = [], {}
    if search:
        where.append("(m.title LIKE :s OR m.folder LIKE :s)")
        params["s"] = "%{}%".format(search)
    if state == PROBLEM_STATES_KEY:
        # The states worth acting on. "no_trailer" is not one of them: a film
        # TMDB has nothing for is an answer, not a fault.
        where.append("m.state IN ('error', 'no_id')")
    elif state:
        where.append("m.state = :state")
        params["state"] = state
    if only_missing:
        where.append("(m.trailer IS NULL OR m.trailer = '')")
    if library_id is not None:
        where.append("m.library_id = :library")
        params["library"] = library_id
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params["limit"] = limit
    params["offset"] = offset
    with connect() as con:
        rows = con.execute(
            "SELECT m.*, l.name AS library_name, l.kind AS library_kind "
            "FROM movies m LEFT JOIN libraries l ON l.id = m.library_id {} "
            "ORDER BY {} LIMIT :limit OFFSET :offset"
            .format(clause, order_clause(sort, direction)), params).fetchall()
        total = con.execute(
            "SELECT COUNT(*) c FROM movies m "
            "LEFT JOIN libraries l ON l.id = m.library_id {}".format(clause),
            params).fetchone()["c"]
    return rows, total


def stats(primary_lang="de", library_id=None):
    """Counts for the dashboard.

    The "of which <language>" figure follows the first configured language, so
    it stays meaningful for an English or French library too.
    """
    scope = "" if library_id is None else " WHERE library_id = :library"
    with connect() as con:
        row = con.execute("""
            SELECT COUNT(*) total,
                   SUM(CASE WHEN trailer IS NOT NULL AND trailer <> ''
                            THEN 1 ELSE 0 END) with_trailer,
                   SUM(CASE WHEN trailer_lang = :lang THEN 1 ELSE 0 END) primary_lang,
                   SUM(CASE WHEN state = 'no_trailer' THEN 1 ELSE 0 END) no_trailer,
                   SUM(CASE WHEN state = 'no_id' THEN 1 ELSE 0 END) no_id,
                   SUM(CASE WHEN state = 'error' THEN 1 ELSE 0 END) errors
            FROM movies{}""".format(scope),
            {"lang": (primary_lang or "de").lower(), "library": library_id}).fetchone()
    out = {k: (row[k] or 0) for k in row.keys()}
    out["primary_lang_code"] = (primary_lang or "de").lower()
    return out


# ------------------------------------------------------------------------ log
LOG_KEEP = 2000
_log_writes = 0
_log_hook = None


def set_log_hook(hook):
    """Watch every log entry as it is written.

    Used to turn warnings into notifications without having to remember a
    notify() call at each of the two dozen places that can warn.
    """
    global _log_hook
    _log_hook = hook


def log(level, message, source="app"):
    """Write a log line; clean out old ones only now and then.

    Pruning on every insert costs real time during a run with thousands of
    messages, so it happens every hundredth write instead.
    """
    global _log_writes
    text = str(message)[:2000]
    with connect() as con:
        con.execute("INSERT INTO log(ts, level, source, message) VALUES(?,?,?,?)",
                    (time.time(), level, source, text))
        _log_writes += 1
        if _log_writes % 100 == 0:
            con.execute("DELETE FROM log WHERE id NOT IN "
                        "(SELECT id FROM log ORDER BY id DESC LIMIT ?)", (LOG_KEEP,))

    # After the write, never inside it: a hook that logs would otherwise
    # re-enter the connection it is already holding.
    hook = _log_hook
    if hook is not None:
        try:
            hook(level, text, source)
        except Exception:                                  # noqa: BLE001
            pass            # logging must not fail because a hook did


def log_counts():
    """How many entries of each level - shown on the filter itself, so the
    number of errors is visible without clicking through to them."""
    with connect() as con:
        return {r["level"]: r["c"] for r in con.execute(
            "SELECT level, COUNT(*) c FROM log GROUP BY level")}


def recent_log(limit=200, level=None):
    sql = "SELECT * FROM log"
    params = []
    if level:
        sql += " WHERE level=?"
        params.append(level)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect() as con:
        return con.execute(sql, params).fetchall()


# ----------------------------------------------------------------------- runs
def start_run(trigger):
    with connect() as con:
        cur = con.execute("INSERT INTO runs(started, trigger) VALUES(?,?)",
                          (time.time(), trigger))
        return cur.lastrowid


def finish_run(run_id, scanned=0, checked=0, updated=0, failed=0):
    with connect() as con:
        con.execute("UPDATE runs SET finished=?, scanned=?, checked=?, updated=?, failed=? "
                    "WHERE id=?", (time.time(), scanned, checked, updated, failed, run_id))


def last_runs(limit=10):
    with connect() as con:
        return con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def delete_orphans():
    """Remove entries that belong to no existing library.

    Happens after a library is deleted while a scan was running, or when an
    older database is migrated and a folder is no longer configured.
    """
    with connect() as con:
        cur = con.execute(
            "DELETE FROM movies WHERE library_id IS NULL "
            "OR library_id NOT IN (SELECT id FROM libraries)")
        return cur.rowcount


def assign_all_to_library(lib_id):
    """Put every entry without a library into the given one (migration)."""
    with connect() as con:
        cur = con.execute("UPDATE movies SET library_id=? WHERE library_id IS NULL",
                          (lib_id,))
        return cur.rowcount
