"""Scanning the libraries, automatic runs, schedule, and new items from Emby.

Every library is a folder plus a kind: movies (one NFO per movie folder) or TV
shows (one tvshow.nfo per series folder). Each may override the global
settings - a library of anime films can look for Japanese trailers while the
main library stays German.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import db
import emby as emby_mod
import nfo
import notify as notify_mod
import tmdb


def _row_value(row, key):
    """Read a column that may not exist on this row object."""
    try:
        value = row[key]
    except (IndexError, KeyError, TypeError):
        return None
    return value


class Scanner:
    def __init__(self, settings_getter):
        self.get = settings_getter          # callable(key, default) -> str
        self.lock = threading.Lock()
        self.busy = False
        self.state = {"phase": "idle", "done": 0, "total": 0, "current": "",
                      "started": None, "trigger": None}
        self._stop = threading.Event()
        self._scheduler = None
        self._emby = None
        self._emby_settings = None
        self._poller = None

    # ------------------------------------------------------------------ helpers
    def setting_for(self, lib, key, default=None):
        """A library's own value, or the global one when it is empty."""
        value = _row_value(lib, key) if lib is not None else None
        if value not in (None, ""):
            return value
        return self.get(key, default)

    def _langs(self, lib=None):
        raw = self.setting_for(lib, "languages", "de")
        return [l.strip() for l in str(raw).split(",") if l.strip()] or ["de"]

    def _flag(self, lib, key, default="0"):
        return str(self.setting_for(lib, key, default)) in ("1", "true", "True", "on", "yes")

    def _api_key(self):
        return (self.get("tmdb_api_key", "") or "").strip()

    def _recheck_seconds(self, lib):
        try:
            days = int(self.setting_for(lib, "recheck_days", "30") or 30)
        except (TypeError, ValueError):
            days = 30
        return days * 86400

    def media_server(self):
        """The Emby client, rebuilt when address or key change.

        Kept on the scanner so its index of the library survives a whole run
        instead of being fetched again for every trailer.
        """
        current = (self.get("emby_url", ""), self.get("emby_api_key", ""))
        if self._emby is None or self._emby_settings != current:
            self._emby = emby_mod.Emby(*current)
            self._emby_settings = current
        return self._emby

    def notify_media_server(self, row, tmdb_id):
        """Ask Emby to re-read one item. Never lets a failure reach the caller.

        Always done when a server is configured - there is no reason to write a
        trailer and then leave the server unaware of it for twelve hours. The
        trailer is already on disk at this point, so a server that is off or
        misconfigured must not turn a successful write into an error.
        """
        server = self.media_server()
        if not server.configured():
            return False
        try:
            if server.refresh(tmdb_id):
                return True
            db.log("warn", "{} was not found on the media server (TMDB {}) - "
                           "refresh skipped".format(row["title"], tmdb_id), "emby")
        except emby_mod.EmbyError as e:
            db.log("warn", "Refresh for {} failed: {}".format(row["title"], e), "emby")
        return False

    # ---------------------------------------------------------- notifications
    def notify(self, title, message, priority=notify_mod.NORMAL, when="on_new"):
        """Send to every enabled target. Returns how many went out.

        A notification is never allowed to matter: the trailer is written, the
        run is finished, and a service being unreachable must not turn any of
        that into a failure. One broken target also must not stop the others.
        """
        if not self._flag(None, "notify_" + when, "0"):
            return 0
        sent = 0
        for target in db.list_notifiers(only_enabled=True):
            try:
                notify_mod.send(target["service"], target["url"], target["token"],
                                title, message, priority)
                sent += 1
            except notify_mod.NotifyError as e:
                db.log("warn", "Notification via {} failed: {}"
                       .format(target["service"], e), "notify")
        return sent

    def stop(self):
        self._stop.set()

    def _claim(self):
        """Take the busy flag. False when something is already running.

        Checking and setting have to happen under the same lock, otherwise two
        quick clicks start two runs.
        """
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            return True

    def _release(self):
        with self.lock:
            self.busy = False

    # ------------------------------------------------------------------ reading
    def scan_async(self):
        """Start reading all libraries in the background. False when busy."""
        if not self._claim():
            return False
        self._stop.clear()

        def job():
            try:
                self.scan_all()
            except Exception as e:                         # noqa: BLE001
                db.log("error", "Reading the libraries failed: {}".format(e), "scan")
            finally:
                self.state.update(phase="idle", current="")
                self._release()

        threading.Thread(target=job, daemon=True).start()
        return True

    def scan_all(self, workers=12):
        """Read every enabled library."""
        libraries = db.list_libraries(only_enabled=True)
        if not libraries:
            db.log("warn", "No library configured - nothing to scan.", "scan")
            return {"files": 0, "changed": 0, "removed": 0}

        total = {"files": 0, "changed": 0, "removed": 0}
        for lib in libraries:
            if self._stop.is_set():
                break
            result = self.scan_library(lib, workers=workers)
            for key in total:
                total[key] += result[key]
        gone = db.delete_orphans()
        if gone:
            db.log("info", "{} entries of removed libraries cleaned up".format(gone), "scan")
        return total

    def scan_library(self, lib, workers=12):
        """Read one library and reconcile it with the database. Only changed
        files are parsed again - mtime and size are already in the database."""
        started = time.time()
        kind = _row_value(lib, "kind") or "movie"
        lib_id = _row_value(lib, "id")
        name = _row_value(lib, "name") or "?"
        root = _row_value(lib, "path") or ""

        self.state.update(phase="scan", done=0, total=0, current=name)
        only_names = {nfo.TV_NFO_NAME} if kind == "tv" else None
        files = nfo.walk_nfo_files(root, self._stop, only_names=only_names)
        self.state["total"] = len(files)
        known = db.known_files(lib_id)
        present = set()
        todo = []
        for path, mtime, size in files:
            present.add(path)
            old = known.get(path)
            if old and abs((old[0] or 0) - mtime) < 1 and (old[1] or 0) == size:
                self.state["done"] += 1
                continue
            todo.append((path, mtime, size))

        added = 0
        if todo:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(nfo.parse_nfo, p, kind): (p, m, s)
                           for p, m, s in todo}
                for fut in as_completed(futures):
                    if self._stop.is_set():
                        break
                    path, mtime, size = futures[fut]
                    try:
                        data = fut.result()
                    except Exception:                      # noqa: BLE001
                        data = None
                    if data:
                        db.upsert_movie(path, str(Path(path).parent), data, mtime, size,
                                        library_id=lib_id)
                        added += 1
                    self.state["done"] += 1
                    self.state["current"] = "{}: {}".format(name, Path(path).parent.name)

        gone = db.delete_missing(present, lib_id)
        db.log("info", "{}: {} NFOs, {} new or changed, {} removed, {:.1f}s"
               .format(name, len(files), added, len(gone), time.time() - started), "scan")
        return {"files": len(files), "changed": added, "removed": len(gone)}

    # ------------------------------------------------------------- single entry
    def process_movie(self, row, force=False):
        """Look an entry up on TMDB and write the NFO.
        Returns (status, message)."""
        lib = db.get_library(_row_value(row, "library_id"))
        kind = _row_value(lib, "kind") or "movie"
        api_key = self._api_key()
        langs = self._langs(lib)
        path = row["path"]

        tmdb_id = row["tmdb_id"]
        try:
            if not tmdb_id and row["imdb_id"]:
                tmdb_id = tmdb.lookup_by_imdb(row["imdb_id"], api_key, kind)
            if not tmdb_id:
                db.mark_result(path, "no_id", "No TMDB or IMDb id in the NFO")
                return "no_id", "No TMDB or IMDb id in the NFO"

            videos = tmdb.fetch_videos(tmdb_id, api_key, langs, kind)
            best = tmdb.pick_best(videos, langs)
        except tmdb.TmdbError as e:
            db.mark_result(path, "error", str(e))
            db.log("error", "{}: {}".format(row["title"], e), "tmdb")
            return "error", str(e)

        # A link that was already in the NFO came from Emby, so its language is
        # unknown to us. Ask TMDB about it while we have the video list anyway -
        # that is what fills the language column for an existing library.
        existing_id = nfo.video_id_from(row["trailer"])
        if existing_id and not row["trailer_lang"]:
            existing_lang = tmdb.language_of(videos, existing_id)
            if existing_lang:
                db.note_trailer_lang(path, existing_lang)

        if not best:
            db.mark_result(path, "no_trailer",
                           "No trailer in {}".format(", ".join(langs)))
            return "no_trailer", "No trailer in {}".format(", ".join(langs))

        fmt = self.setting_for(lib, "link_format", "emby")
        if self._flag(lib, "keep_format", "1") and row["trailer"]:
            fmt = nfo.detect_format(row["trailer"]) or fmt
        value = nfo.format_link(best["key"], fmt)

        if value == (row["trailer"] or "") and not force:
            db.mark_result(path, "ok", "Already up to date", trailer=value,
                           trailer_lang=best.get("lang"), written=True)
            return "ok", "Already up to date"

        try:
            nfo.write_trailer(Path(path), value,
                              lockdata=self._flag(lib, "lockdata"),
                              backup=self._flag(lib, "backup", "1"))
        except (nfo.WriteError, OSError) as e:
            msg = str(e).splitlines()[0]
            db.mark_result(path, "error", msg)
            db.log("error", "{}:\n{}".format(row["title"], nfo.failure_report(path, e)),
                   "write")
            return "error", msg

        db.mark_result(path, "ok", "Trailer [{}] {}".format(best.get("lang"), best["key"]),
                       trailer=value, trailer_lang=best.get("lang"), written=True)
        db.log("ok", "{}: trailer [{}] {} written".format(
            row["title"], best.get("lang"), best["key"]), "auto")
        self.notify_media_server(row, tmdb_id)
        return "ok", best["key"]

    def candidates_for(self, row):
        """Every trailer of an entry - for picking one by hand in the interface."""
        lib = db.get_library(_row_value(row, "library_id"))
        kind = _row_value(lib, "kind") or "movie"
        api_key = self._api_key()
        langs = self._langs(lib)
        tmdb_id = row["tmdb_id"]
        if not tmdb_id and row["imdb_id"]:
            tmdb_id = tmdb.lookup_by_imdb(row["imdb_id"], api_key, kind)
        if not tmdb_id:
            return []
        return tmdb.sort_candidates(tmdb.fetch_videos(tmdb_id, api_key, langs, kind),
                                    langs)

    # ----------------------------------------------------------- automatic run
    def run(self, trigger="manual", only_paths=None, force=False, library_id=None):
        """Full run: read the libraries, then work through the open entries.

        With `library_id` only that one library is touched - useful right after
        adding a folder, when rescanning everything would take far longer.
        """
        if not self._claim():
            return {"skipped": True, "reason": "A run is already in progress"}

        # Without a key every single entry would fail with the same message.
        # The run at startup fires a few seconds after the container comes up,
        # which is before anyone can have finished the setup wizard - that used
        # to fill the log with one identical error per movie.
        if not self._api_key():
            self._release()
            db.log("warn", "Run ({}) skipped: no TMDB API key configured yet."
                   .format(trigger), "auto")
            return {"skipped": True, "reason": "No TMDB API key configured"}

        self._stop.clear()
        run_id = db.start_run(trigger)
        self.state.update(started=time.time(), trigger=trigger)
        scanned = checked = updated = failed = 0
        try:
            if only_paths is None:
                if library_id is None:
                    libraries = db.list_libraries(only_enabled=True)
                    info = self.scan_all()
                else:
                    one = db.get_library(library_id)
                    libraries = [one] if one else []
                    info = self.scan_library(one) if one else {"files": 0}
                scanned = info["files"]
                rows = []
                overwrite = self._flag(None, "overwrite_existing")
                for lib in libraries:
                    rows.extend(db.pending_movies(self._recheck_seconds(lib), overwrite,
                                                  library_id=lib["id"]))
            else:
                rows = [db.get_movie(p) for p in only_paths]
                rows = [r for r in rows if r]

            self.state.update(phase="check", done=0, total=len(rows), current="")
            db.log("info", "Automatic run ({}): {} entries to check".format(trigger, len(rows)),
                   "auto")

            for row in rows:
                if self._stop.is_set():
                    db.log("warn", "Automatic run cancelled", "auto")
                    break
                self.state["current"] = row["title"] or row["folder"]
                status, _msg = self.process_movie(row, force=force)
                checked += 1
                if status == "ok":
                    updated += 1
                elif status == "error":
                    failed += 1
                self.state["done"] = checked
                time.sleep(0.05)                # go easy on TMDB
        finally:
            db.finish_run(run_id, scanned, checked, updated, failed)
            self.state.update(phase="idle", current="")
            self._release()
        result = {"scanned": scanned, "checked": checked, "updated": updated,
                  "failed": failed}
        db.log("info", "Automatic run finished: {}".format(result), "auto")

        summary = ("{} checked, {} trailers written, {} failed"
                   .format(checked, updated, failed))
        if failed:
            # Errors are worth a message even when the summary itself is off.
            self.notify("Run finished with errors", summary,
                        priority=notify_mod.HIGH, when="on_error")
        if checked or updated:
            self.notify("Run finished", summary, when="on_run")
        return result

    def run_async(self, **kwargs):
        """Start a run in the background. The busy guard lives in run() itself,
        so the look at busy here is only a quick pre-check."""
        if self.busy:
            return False
        threading.Thread(target=self.run, kwargs=kwargs, daemon=True).start()
        return True

    # ------------------------------------------------------- new items from Emby
    def poll_new_items(self):
        """Ask the media server what was added, and give those items a trailer.

        This replaces the webhook. The server is asked instead of asking to be
        told, which means nothing has to be configured inside Emby and no
        connection has to reach this container from outside.
        """
        server = self.media_server()
        if not server.configured():
            return {"skipped": "no server configured"}
        try:
            items = server.recent_items()
        except emby_mod.EmbyError as e:
            db.log("warn", "Asking for new items failed: {}".format(e), "emby")
            return {"error": str(e)}

        db.set_setting("emby_last_poll", time.strftime("%Y-%m-%d %H:%M:%S"))
        seen = db.get_setting("emby_last_seen") or ""
        newest = max([str(i.get("DateCreated") or "") for i in items] or [""])

        if not seen:
            # First time: remember where we are instead of treating the whole
            # library as new and looking up fifty films at once.
            db.set_setting("emby_last_seen", newest)
            db.log("info", "Media server connected - watching for items added from "
                           "now on.", "emby")
            return {"bootstrapped": len(items)}

        fresh = [i for i in items if str(i.get("DateCreated") or "") > seen]
        if not fresh:
            return {"new": 0}

        db.log("info", "{} new item(s) reported by the media server".format(len(fresh)),
               "emby")
        handled = 0
        for item in sorted(fresh, key=lambda i: str(i.get("DateCreated") or "")):
            if self._stop.is_set():
                break
            if self._handle_new_item(item):
                handled += 1
            db.set_setting("emby_last_seen", str(item.get("DateCreated") or newest))
        return {"new": len(fresh), "handled": handled}

    def _handle_new_item(self, item):
        """One newly added movie or series."""
        title = item.get("Name") or "?"
        tmdb_id = (item.get("ProviderIds") or {}).get("Tmdb")

        rows = db.find_by_tmdb(tmdb_id) if tmdb_id else []
        if not rows:
            folder, lib = self._local_folder_for(item)
            if folder is None:
                db.log("warn", "{} is not in any configured library".format(title), "emby")
                return False
            rows = self._rows_for_path(str(folder), lib)
            if not rows:
                rows = self._wait_for_nfo(str(folder), lib, tmdb_id, title)
        if not rows:
            db.log("warn", "No NFO found for {} yet".format(title), "emby")
            return False

        for row in rows:
            status, message = self.process_movie(row)
            if status == "ok":
                self.notify("Trailer set", "{}\n{}".format(row["title"], message),
                            when="on_new")
            elif status in ("no_trailer", "no_id"):
                self.notify("No trailer found", "{}\n{}".format(row["title"], message),
                            when="on_new")
        return True

    def _local_folder_for(self, item):
        """Match an Emby item to a folder in our libraries.

        Emby reports its own paths - /mnt/user/Movies/... - while this container
        sees /movies, so only the folder name can be compared. For a movie that
        is the folder holding the media file, for a series the series folder.
        """
        emby_path = str(item.get("Path") or "").replace("\\", "/").rstrip("/")
        if not emby_path:
            return None, None
        kind = "tv" if item.get("Type") == "Series" else "movie"
        parts = [p for p in emby_path.split("/") if p]
        if not parts:
            return None, None
        name = parts[-1] if kind == "tv" else (parts[-2] if len(parts) > 1 else parts[-1])

        for lib in db.list_libraries(only_enabled=True):
            if (_row_value(lib, "kind") or "movie") != kind:
                continue
            candidate = Path(_row_value(lib, "path") or "/") / name
            if candidate.is_dir():
                return candidate, lib
        return None, None

    def _wait_steps(self):
        """Growing pauses that add up to the configured waiting time."""
        try:
            total = int(self.get("nfo_wait", "60") or 60)
        except (TypeError, ValueError):
            total = 60
        steps, spent = [], 0
        for delay in (2, 3, 5, 10, 20, 30, 30, 30):
            if spent >= total:
                break
            steps.append(min(delay, total - spent))
            spent += steps[-1]
        return steps

    def _wait_for_nfo(self, path, lib, tmdb_id, title):
        """Look again a few times while the media server catches up.

        Emby knows about a film before it has written the NFO next to it, so
        the first look often finds nothing at all.
        """
        waited = 0
        for delay in self._wait_steps():
            if self._stop.is_set():
                break
            time.sleep(delay)
            waited += delay
            rows = self._rows_for_path(path, lib)
            if not rows and tmdb_id:
                rows = db.find_by_tmdb(tmdb_id)
            if rows:
                db.log("info", "NFO for {} appeared after {}s".format(title, waited),
                       "emby")
                return rows
        return []

    def _rows_for_path(self, path, lib=None):
        """Find the entries a reported file belongs to.

        For a movie that is its own folder. For a series the notification points
        at an episode file several levels down, so we walk up towards the
        library root - first through the database, then looking for the
        tvshow.nfo on disk. Neither case reads more than it has to.
        """
        target = Path(path)
        folder = target if target.is_dir() else target.parent
        rows = db.find_by_folder(str(folder))
        if rows:
            return rows

        if lib is None:
            lib = self._library_for(path)
        if lib is None:
            return []
        kind = _row_value(lib, "kind") or "movie"
        lib_id = _row_value(lib, "id")
        root = Path(_row_value(lib, "path") or "/")

        if kind == "tv":
            for parent in _ancestors(folder, root):
                rows = db.find_by_folder(str(parent))
                if rows:
                    return rows
            for parent in _ancestors(folder, root):
                candidate = parent / nfo.TV_NFO_NAME
                if self._adopt(candidate, parent, lib_id, "tv"):
                    return db.find_by_folder(str(parent))
            return []

        # Movie: read this one folder, nothing else.
        for nfo_path, mtime, size in nfo.walk_nfo_files(str(folder)):
            data = nfo.parse_nfo(nfo_path, "movie")
            if data:
                db.upsert_movie(nfo_path, str(Path(nfo_path).parent), data, mtime, size,
                                library_id=lib_id)
        return db.find_by_folder(str(folder))

    def _adopt(self, nfo_path, folder, lib_id, kind):
        """Read a single NFO into the database. True when it worked."""
        try:
            stat = nfo_path.stat()
        except OSError:
            return False
        data = nfo.parse_nfo(nfo_path, kind)
        if not data:
            return False
        db.upsert_movie(str(nfo_path), str(folder), data, stat.st_mtime, stat.st_size,
                        library_id=lib_id)
        return True

    def _library_for(self, path):
        """Which configured library does this path sit in?"""
        target = Path(path)
        best = None
        for lib in db.list_libraries(only_enabled=True):
            root = Path(_row_value(lib, "path") or "/")
            if target == root or root in target.parents:
                # Longest match wins, so nested folders pick the inner library.
                if best is None or len(str(root)) > len(str(_row_value(best, "path") or "")):
                    best = lib
        return best

    # --------------------------------------------------------------- schedule
    def start_scheduler(self):
        if self._scheduler and self._scheduler.is_alive():
            return

        def loop():
            if self._flag(None, "scan_on_start", "1"):
                time.sleep(5)
                try:
                    self.run(trigger="start")
                except Exception as e:                     # noqa: BLE001
                    db.log("error", "Run at startup failed: {}".format(e), "schedule")
            while True:
                try:
                    hours = float(self.get("scan_interval_hours", "12") or 12)
                except (TypeError, ValueError):
                    hours = 12
                if hours <= 0:
                    time.sleep(300)             # schedule switched off
                    continue
                time.sleep(hours * 3600)
                try:
                    self.run(trigger="schedule")
                except Exception as e:                     # noqa: BLE001
                    db.log("error", "Scheduled run failed: {}".format(e), "schedule")

        self._scheduler = threading.Thread(target=loop, daemon=True)
        self._scheduler.start()

        def poller():
            while True:
                try:
                    minutes = float(self.get("emby_poll_minutes", "5") or 0)
                except (TypeError, ValueError):
                    minutes = 5
                if minutes <= 0:
                    time.sleep(60)              # asking switched off
                    continue
                time.sleep(minutes * 60)
                if self.busy:
                    continue                    # a run is already working through it
                try:
                    self.poll_new_items()
                except Exception as e:          # noqa: BLE001
                    db.log("error", "Asking for new items failed: {}".format(e), "emby")

        self._poller = threading.Thread(target=poller, daemon=True)
        self._poller.start()


def _ancestors(folder, root):
    """The folder itself and every parent up to the library root, closest first."""
    current = Path(folder)
    seen = []
    while True:
        seen.append(current)
        if current == root or current.parent == current or root not in current.parents:
            break
        current = current.parent
    return seen


def _dig(data, keys):
    """Fetch a nested value without tripping over missing keys."""
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur
