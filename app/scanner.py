"""Reading the library, automatic runs, schedule and webhook handling."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import db
import nfo
import tmdb


class Scanner:
    def __init__(self, movies_dir, settings_getter):
        self.movies_dir = Path(movies_dir)
        self.get = settings_getter          # callable(key, default) -> str
        self.lock = threading.Lock()
        self.busy = False
        self.state = {"phase": "idle", "done": 0, "total": 0, "current": "",
                      "started": None, "trigger": None}
        self._stop = threading.Event()
        self._scheduler = None

    # ------------------------------------------------------------------ helpers
    def _langs(self):
        raw = self.get("languages", "de")
        return [l.strip() for l in raw.split(",") if l.strip()] or ["de"]

    def _flag(self, key, default="0"):
        return str(self.get(key, default)) in ("1", "true", "True", "on", "yes")

    def _api_key(self):
        return (self.get("tmdb_api_key", "") or "").strip()

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
        """Start reading the library in the background. False when busy."""
        if not self._claim():
            return False
        self._stop.clear()

        def job():
            try:
                self.scan_library()
            except Exception as e:                         # noqa: BLE001
                db.log("error", "Reading the library failed: {}".format(e), "scan")
            finally:
                self.state.update(phase="idle", current="")
                self._release()

        threading.Thread(target=job, daemon=True).start()
        return True

    def scan_library(self, workers=12):
        """Read NFOs and reconcile them with the database. Only changed files are
        parsed again - mtime and size are already in the database."""
        started = time.time()
        self.state.update(phase="scan", done=0, total=0, current="")
        files = nfo.walk_nfo_files(self.movies_dir, self._stop)
        self.state["total"] = len(files)
        known = db.known_files()
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
                futures = {pool.submit(nfo.parse_nfo, p): (p, m, s) for p, m, s in todo}
                for fut in as_completed(futures):
                    if self._stop.is_set():
                        break
                    path, mtime, size = futures[fut]
                    try:
                        data = fut.result()
                    except Exception:                      # noqa: BLE001
                        data = None
                    if data:
                        db.upsert_movie(path, str(Path(path).parent), data, mtime, size)
                        added += 1
                    self.state["done"] += 1
                    self.state["current"] = Path(path).parent.name

        gone = db.delete_missing(present)
        db.log("info", "Library read: {} NFOs, {} new or changed, {} removed, {:.1f}s"
               .format(len(files), added, len(gone), time.time() - started), "scan")
        return {"files": len(files), "changed": added, "removed": len(gone)}

    # ------------------------------------------------------------- single movie
    def process_movie(self, row, force=False):
        """Look a movie up on TMDB and write the NFO.
        Returns (status, message)."""
        api_key = self._api_key()
        langs = self._langs()
        path = row["path"]

        tmdb_id = row["tmdb_id"]
        try:
            if not tmdb_id and row["imdb_id"]:
                tmdb_id = tmdb.lookup_by_imdb(row["imdb_id"], api_key)
            if not tmdb_id:
                db.mark_result(path, "no_id", "No TMDB or IMDb id in the NFO")
                return "no_id", "No TMDB or IMDb id in the NFO"

            videos = tmdb.fetch_videos(tmdb_id, api_key, langs)
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

        fmt = self.get("link_format", "emby")
        if self._flag("keep_format", "1") and row["trailer"]:
            fmt = nfo.detect_format(row["trailer"]) or fmt
        value = nfo.format_link(best["key"], fmt)

        if value == (row["trailer"] or "") and not force:
            db.mark_result(path, "ok", "Already up to date", trailer=value,
                           trailer_lang=best.get("lang"), written=True)
            return "ok", "Already up to date"

        try:
            nfo.write_trailer(Path(path), value,
                              lockdata=self._flag("lockdata"),
                              backup=self._flag("backup", "1"))
        except (nfo.WriteError, OSError) as e:
            msg = str(e).splitlines()[0]
            db.mark_result(path, "error", msg)
            db.log("error", "{}: {}".format(row["title"], msg), "write")
            return "error", msg

        db.mark_result(path, "ok", "Trailer [{}] {}".format(best.get("lang"), best["key"]),
                       trailer=value, trailer_lang=best.get("lang"), written=True)
        db.log("ok", "{}: trailer [{}] {} written".format(
            row["title"], best.get("lang"), best["key"]), "auto")
        return "ok", best["key"]

    def candidates_for(self, row):
        """Every trailer of a movie - for picking one by hand in the interface."""
        api_key = self._api_key()
        tmdb_id = row["tmdb_id"]
        if not tmdb_id and row["imdb_id"]:
            tmdb_id = tmdb.lookup_by_imdb(row["imdb_id"], api_key)
        if not tmdb_id:
            return []
        return tmdb.sort_candidates(tmdb.fetch_videos(tmdb_id, api_key, self._langs()),
                                    self._langs())

    # ----------------------------------------------------------- automatic run
    def run(self, trigger="manual", only_paths=None, force=False):
        """Full run: read the library, then work through the open movies."""
        if not self._claim():
            return {"skipped": True, "reason": "A run is already in progress"}
        self._stop.clear()
        run_id = db.start_run(trigger)
        self.state.update(started=time.time(), trigger=trigger)
        scanned = checked = updated = failed = 0
        try:
            if only_paths is None:
                info = self.scan_library()
                scanned = info["files"]
                recheck = int(self.get("recheck_days", "30") or 30) * 86400
                rows = db.pending_movies(recheck, self._flag("overwrite_existing"))
            else:
                rows = [db.get_movie(p) for p in only_paths]
                rows = [r for r in rows if r]

            self.state.update(phase="check", done=0, total=len(rows), current="")
            db.log("info", "Automatic run ({}): {} movies to check".format(trigger, len(rows)),
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
        result = {"scanned": scanned, "checked": checked, "updated": updated, "failed": failed}
        db.log("info", "Automatic run finished: {}".format(result), "auto")
        return result

    def run_async(self, **kwargs):
        """Start a run in the background. The busy guard lives in run() itself,
        so the look at busy here is only a quick pre-check."""
        if self.busy:
            return False
        threading.Thread(target=self.run, kwargs=kwargs, daemon=True).start()
        return True

    # ---------------------------------------------------------------- webhook
    def handle_event(self, payload):
        """Handle a notification from Emby, Jellyfin or Jellyseerr.

        We look for the file path first, then the TMDB id. If the movie is not
        in the database yet, its folder is read on the spot.
        """
        path = _dig(payload, ["Item", "Path"]) or _dig(payload, ["Path"]) \
            or _dig(payload, ["media", "path"])
        tmdb_id = (_dig(payload, ["Item", "ProviderIds", "Tmdb"])
                   or _dig(payload, ["Item", "ProviderIds", "tmdb"])
                   or _dig(payload, ["ProviderIds", "Tmdb"])
                   or _dig(payload, ["media", "tmdbId"])
                   or _dig(payload, ["tmdbId"]))
        title = (_dig(payload, ["Item", "Name"]) or _dig(payload, ["Name"])
                 or _dig(payload, ["subject"]) or "?")

        rows = []
        if path:
            folder = str(Path(path).parent)
            rows = db.find_by_folder(folder)
            if not rows:
                # Read just this folder (the movie is brand new)
                for nfo_path, mtime, size in nfo.walk_nfo_files(folder):
                    data = nfo.parse_nfo(nfo_path)
                    if data:
                        db.upsert_movie(nfo_path, folder, data, mtime, size)
                rows = db.find_by_folder(folder)
        if not rows and tmdb_id:
            rows = db.find_by_tmdb(tmdb_id)
        if not rows and tmdb_id:
            # Still nothing in the database: read the whole library once
            db.log("info", "Webhook: {} unknown, reading the library".format(title), "webhook")
            self.scan_library()
            rows = db.find_by_tmdb(tmdb_id)

        if not rows:
            db.log("warn", "Webhook: no matching movie found ({})".format(title), "webhook")
            return {"matched": 0, "title": title}

        results = []
        for row in rows:
            status, msg = self.process_movie(row)
            results.append({"title": row["title"], "status": status, "message": msg})
        db.log("info", "Webhook: {} -> {}".format(title, results[0]["status"]), "webhook")
        return {"matched": len(rows), "title": title, "results": results}

    # --------------------------------------------------------------- schedule
    def start_scheduler(self):
        if self._scheduler and self._scheduler.is_alive():
            return

        def loop():
            if self._flag("scan_on_start", "1"):
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
