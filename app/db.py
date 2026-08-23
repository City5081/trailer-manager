"""SQLite-Ablage: Filme, Protokoll, Einstellungen.

Der Filmbestand wird dauerhaft gespeichert. Ein Automatiklauf fasst deshalb nur
noch Filme an, die neu sind, deren NFO sich geaendert hat oder die beim letzten
Mal keinen Trailer bekommen haben.
"""

import sqlite3
import threading
import time
from contextlib import contextmanager

_local = threading.local()
_DB_PATH = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    path           TEXT PRIMARY KEY,
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
    last_scanned   REAL,            -- NFO zuletzt eingelesen
    last_checked   REAL,            -- TMDB zuletzt gefragt
    last_changed   REAL             -- NFO zuletzt von uns geschrieben
);
CREATE INDEX IF NOT EXISTS idx_movies_state  ON movies(state);
CREATE INDEX IF NOT EXISTS idx_movies_tmdb   ON movies(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_movies_folder ON movies(folder);

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
    trigger   TEXT,          -- manual | schedule | webhook
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


# --------------------------------------------------------------- Einstellungen
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


# ---------------------------------------------------------------------- Filme
def upsert_movie(path, folder, data, mtime, size):
    now = time.time()
    with connect() as con:
        con.execute("""
            INSERT INTO movies(path, folder, title, year, tmdb_id, imdb_id, trailer,
                               state, mtime, size, first_seen, last_scanned)
            VALUES(?,?,?,?,?,?,?, COALESCE((SELECT state FROM movies WHERE path=?), 'pending'),
                   ?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET
                folder=excluded.folder, title=excluded.title, year=excluded.year,
                tmdb_id=excluded.tmdb_id, imdb_id=excluded.imdb_id,
                trailer=excluded.trailer, mtime=excluded.mtime, size=excluded.size,
                last_scanned=excluded.last_scanned
        """, (path, folder, data["title"], data["year"], data["tmdb"], data["imdb"],
              data["trailer"], path, mtime, size, now, now))


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


def get_movie(path):
    with connect() as con:
        return con.execute("SELECT * FROM movies WHERE path=?", (path,)).fetchone()


def find_by_tmdb(tmdb_id):
    with connect() as con:
        return con.execute("SELECT * FROM movies WHERE tmdb_id=?", (str(tmdb_id),)).fetchall()


def find_by_folder(folder):
    with connect() as con:
        return con.execute("SELECT * FROM movies WHERE folder=?", (folder,)).fetchall()


def known_files():
    """{pfad: (mtime, size)} - fuer den Abgleich beim Einlesen."""
    with connect() as con:
        return {r["path"]: (r["mtime"], r["size"])
                for r in con.execute("SELECT path, mtime, size FROM movies")}


def delete_missing(paths_present):
    """Filme entfernen, deren NFO es nicht mehr gibt."""
    with connect() as con:
        rows = con.execute("SELECT path FROM movies").fetchall()
        gone = [r["path"] for r in rows if r["path"] not in paths_present]
        for path in gone:
            con.execute("DELETE FROM movies WHERE path=?", (path,))
    return gone


def pending_movies(recheck_seconds, overwrite_existing=False, limit=None):
    """Was beim Automatiklauf angefasst wird.

    - immer: neue Filme und solche ohne Trailer
    - erneut: Filme ohne Treffer, wenn der letzte Versuch lange her ist
    - nie: fertige Filme, ausser 'overwrite_existing' ist gesetzt
    """
    cutoff = time.time() - recheck_seconds
    sql = """
        SELECT * FROM movies
        WHERE (:overwrite = 1)
           OR state IS NULL OR state IN ('pending', 'error')
           OR (trailer IS NULL OR trailer = '')
           OR (state IN ('no_trailer', 'no_id')
               AND (last_checked IS NULL OR last_checked < :cutoff))
        ORDER BY (last_checked IS NOT NULL), last_checked ASC, title ASC
    """
    if limit:
        sql += " LIMIT {:d}".format(int(limit))
    with connect() as con:
        return con.execute(sql, {"overwrite": 1 if overwrite_existing else 0,
                                 "cutoff": cutoff}).fetchall()


def list_movies(search=None, state=None, only_missing=False, limit=500, offset=0):
    where, params = [], {}
    if search:
        where.append("(title LIKE :s OR folder LIKE :s)")
        params["s"] = "%{}%".format(search)
    if state:
        where.append("state = :state")
        params["state"] = state
    if only_missing:
        where.append("(trailer IS NULL OR trailer = '')")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params["limit"] = limit
    params["offset"] = offset
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM movies {} ORDER BY title COLLATE NOCASE "
            "LIMIT :limit OFFSET :offset".format(clause), params).fetchall()
        total = con.execute("SELECT COUNT(*) c FROM movies {}".format(clause),
                            params).fetchone()["c"]
    return rows, total


def stats():
    with connect() as con:
        row = con.execute("""
            SELECT COUNT(*) total,
                   SUM(CASE WHEN trailer IS NOT NULL AND trailer <> ''
                            THEN 1 ELSE 0 END) with_trailer,
                   SUM(CASE WHEN trailer_lang = 'de' THEN 1 ELSE 0 END) german,
                   SUM(CASE WHEN state = 'no_trailer' THEN 1 ELSE 0 END) no_trailer,
                   SUM(CASE WHEN state = 'no_id' THEN 1 ELSE 0 END) no_id,
                   SUM(CASE WHEN state = 'error' THEN 1 ELSE 0 END) errors
            FROM movies""").fetchone()
    return {k: (row[k] or 0) for k in row.keys()}


# ------------------------------------------------------------------ Protokoll
LOG_KEEP = 2000
_log_writes = 0


def log(level, message, source="app"):
    """Protokollzeile schreiben; alte Zeilen nur gelegentlich wegraeumen.

    Das Aufraeumen bei jedem Eintrag kostet waehrend eines Laufs mit tausenden
    Meldungen spuerbar Zeit, deshalb nur jedes hundertste Mal.
    """
    global _log_writes
    with connect() as con:
        con.execute("INSERT INTO log(ts, level, source, message) VALUES(?,?,?,?)",
                    (time.time(), level, source, str(message)[:2000]))
        _log_writes += 1
        if _log_writes % 100 == 0:
            con.execute("DELETE FROM log WHERE id NOT IN "
                        "(SELECT id FROM log ORDER BY id DESC LIMIT ?)", (LOG_KEEP,))


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


# ----------------------------------------------------------------- Durchlaeufe
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
